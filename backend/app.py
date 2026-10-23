"""Project X — Backend FastAPI. Gateway WebSocket autoritativo (ADR-0003) +
servido del build de la web.

Este archivo es la FRONTERA del sistema (Sesión 4): todo lo que entra es hostil
hasta que la barricada lo valida. Aquí —y solo aquí— se:
  - valida cada mensaje (barricada.parsear),
  - aplica contrapresión por cliente (TokenBucket, Sesión 7),
  - captura TODA excepción y se loguea UNA vez en JSON estructurado (Sesión 5),
  - traduce errores internos a mensajes seguros para el jugador.
El núcleo (match/engine) asume datos limpios y usa contratos.

Dev:  uvicorn app:app --host 0.0.0.0 --port 8787 --ws wsproto --reload
Prod: python app.py   (sirve también web/dist en el mismo puerto -> LAN/ngrok)
"""

import asyncio
import json
import logging
import os
import random
import secrets
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

import config
import i18n
from barricada import parsear
from errores import DemasiadasAcciones, EntradaInvalida, PartidaNoEncontrada, ProjectXError, ReglaDeJuego
from match import Match
from observabilidad import (contadores, correlation_id, evento, nuevo_correlation_id, partida_actual)
from resiliencia import TokenBucket
from response import RESPUESTAS
from scenario import catalogo as catalogo_escenarios
from techniques import TECNICAS

VERSION = '2.0.0'
PORT = config.PORT
TICK_SEG = config.TICK_SEG  # periodo del tick (config.py, ADR-0004)
WEB_DIST = Path(__file__).resolve().parent.parent / 'web' / 'dist'

# Catálogos anunciados al cliente, ya filtrados por feature flags (config.py, U3).
TECNICAS_PUB = config.filtra_catalogo(TECNICAS)
RESPUESTAS_PUB = config.filtra_catalogo(RESPUESTAS)

app = FastAPI(title='Project X')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

partidas: dict[str, Match] = {}
cliente_socket: dict[str, WebSocket] = {}   # clientId -> WebSocket
cliente_partida: dict[str, str] = {}        # clientId -> codigo
cliente_cubeta: dict[str, TokenBucket] = {}  # clientId -> contrapresión
tick_tasks: dict[str, asyncio.Task] = {}    # codigo -> task del bucle

# Un candado POR socket (Sesión 6: seguridad de hilos/concurrencia). El bucle de
# ticks y los handlers pueden escribir al mismo socket a la vez; la librería WS
# revienta si se solapan. El candado es por-socket (no global) para que un
# cliente lento no congele el broadcast a los demás; cada envío lleva timeout.
_locks: dict[int, asyncio.Lock] = {}


def _lock_for(sock: WebSocket) -> asyncio.Lock:
    return _locks.setdefault(id(sock), asyncio.Lock())


async def _send(sock: WebSocket, data: str) -> None:
    try:
        async with _lock_for(sock):
            await asyncio.wait_for(sock.send_text(data), timeout=5)
    except Exception:
        pass  # el socket se limpia en el disconnect; no tiramos el tick por un cliente muerto


def nuevo_codigo() -> str:
    abc = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        c = ''.join(random.choice(abc) for _ in range(6))
        if c not in partidas:
            return c


async def enviar(sock: WebSocket, msg: dict) -> None:
    await _send(sock, json.dumps(msg, ensure_ascii=False, default=str))


async def error(sock: WebSocket, mensaje: str) -> None:
    await enviar(sock, {'t': 'error', 'mensaje': mensaje})


async def broadcast(codigo: str) -> None:
    m = partidas.get(codigo)
    if not m:
        return
    data = json.dumps({'t': 'estado', 'estado': m.snapshot()}, ensure_ascii=False, default=str)
    for cid, cod in list(cliente_partida.items()):
        if cod == codigo:
            sock = cliente_socket.get(cid)
            if sock is not None:
                await _send(sock, data)


async def bienvenida(sock: WebSocket, client_id: str, codigo: str, role: str) -> None:
    await enviar(sock, {'t': 'bienvenida', 'clientId': client_id, 'codigo': codigo,
                        'role': role, 'tecnicas': TECNICAS_PUB, 'respuestas': RESPUESTAS_PUB})
    await broadcast(codigo)


async def run_match(codigo: str) -> None:
    """Bucle de ticks de una partida."""
    try:
        while True:
            await asyncio.sleep(TICK_SEG)
            m = partidas.get(codigo)
            if not m or m.estado == 'terminada':
                if m:
                    await broadcast(codigo)
                break
            if m.estado != 'en_curso':
                continue  # pausada: el bucle sigue vivo pero no avanza
            try:
                m.tick_once()
            except ProjectXError as ex:
                # Un contrato roto es un bug nuestro: se loguea con causa y se
                # pausa la partida en vez de reventar el bucle (degradación).
                evento(logging.ERROR, 'tick_error', codigo=codigo, error=ex.mensaje, **ex.contexto)
                m.estado = 'pausada'
            await broadcast(codigo)
            if m.estado == 'terminada':
                evento(logging.INFO, 'partida_terminada', codigo=codigo, ganador=m.ganador, tick=m.engine.tick)
                break
    finally:
        tick_tasks.pop(codigo, None)


@app.websocket('/ws')
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    cid = secrets.token_hex(4)
    cliente_socket[cid] = ws
    cliente_cubeta[cid] = TokenBucket(capacidad=config.BACKPRESSURE_CAP, por_segundo=config.BACKPRESSURE_RPS)
    try:
        while True:
            raw = await ws.receive_text()
            token = correlation_id.set(nuevo_correlation_id())
            try:
                cid = await manejar(ws, cid, raw)
            finally:
                correlation_id.reset(token)
    except WebSocketDisconnect:
        cod = cliente_partida.get(cid)
        if cod and (m := partidas.get(cod)):
            m.desconectar(cid)
            await broadcast(cod)
        cliente_socket.pop(cid, None)
        cliente_cubeta.pop(cid, None)
        _locks.pop(id(ws), None)


async def manejar(ws: WebSocket, cid: str, raw: str) -> str:
    """Procesa un mensaje crudo. Devuelve el clientId activo (cambia al reconectar).

    Toda excepción se captura aquí (la frontera). El jugador recibe un mensaje
    seguro; el detalle técnico queda en el log estructurado con su causa raíz.
    """
    # Contrapresión (Sesión 7): rechazo temprano si el cliente inunda.
    cubeta = cliente_cubeta.get(cid)
    if cubeta and not cubeta.tomar():
        contadores['backpressure.rechazos'] += 1
        await error(ws, i18n.t('rate_limit'))
        return cid
    try:
        msg = parsear(raw)                 # barricada: valida tipo/tamaño/rango/semántica
        return await _despachar(ws, cid, msg)
    except EntradaInvalida as ex:
        evento(logging.WARNING, 'entrada_invalida', error=ex.mensaje, **ex.contexto)
        await error(ws, ex.para_usuario())
    except ReglaDeJuego as ex:
        await error(ws, ex.para_usuario())  # jugada ilegal: esperado, ni se loguea como error
    except PartidaNoEncontrada as ex:
        await error(ws, ex.para_usuario())
    except ProjectXError as ex:
        evento(logging.ERROR, 'error_dominio', error=ex.mensaje, **ex.contexto)
        await error(ws, ex.para_usuario())
    except Exception as ex:                # red de seguridad final: nunca cae el socket
        evento(logging.CRITICAL, 'error_no_manejado', error=repr(ex))
        await error(ws, i18n.t('error_interno'))
    return cid


async def _despachar(ws: WebSocket, cid: str, msg) -> str:
    t = msg.t

    if t == 'crear':
        codigo = nuevo_codigo()
        semilla = msg.semilla if msg.semilla is not None else random.randint(0, 2**32 - 1)
        m = Match(codigo, msg.escenarioId, semilla)
        partidas[codigo] = m
        m.unir(cid, msg.nombre, msg.role)
        cliente_partida[cid] = codigo
        partida_actual.set(codigo)
        evento(logging.INFO, 'partida_creada', codigo=codigo, escenario=msg.escenarioId, rol=msg.role)
        await bienvenida(ws, cid, codigo, msg.role)
        return cid

    if t == 'unir':
        m = partidas.get(msg.codigo)
        if not m:
            raise PartidaNoEncontrada('Código inexistente', codigo=msg.codigo)
        motivo = m.unir(cid, msg.nombre, msg.role)
        if motivo:
            raise ReglaDeJuego(motivo, codigo=msg.codigo)
        cliente_partida[cid] = msg.codigo
        partida_actual.set(msg.codigo)
        evento(logging.INFO, 'jugador_unido', codigo=msg.codigo, rol=msg.role)
        await bienvenida(ws, cid, msg.codigo, msg.role)
        return cid

    if t == 'reconectar':
        m = partidas.get(msg.codigo)
        if not m:
            raise PartidaNoEncontrada('Código inexistente', codigo=msg.codigo)
        prev = msg.clientId
        cliente_socket.pop(cid, None)
        cliente_socket[prev] = ws
        cliente_cubeta[prev] = cliente_cubeta.pop(cid, TokenBucket())
        role = m.reconectar(prev)
        if not role:
            raise ReglaDeJuego('No estabas en esta partida', codigo=msg.codigo)
        cliente_partida[prev] = msg.codigo
        partida_actual.set(msg.codigo)
        await bienvenida(ws, prev, msg.codigo, role)
        return prev

    # acciones que requieren partida + rol
    codigo = cliente_partida.get(cid)
    m = partidas.get(codigo) if codigo else None
    if not m or not codigo:
        raise ReglaDeJuego(i18n.t('sin_partida'))
    partida_actual.set(codigo)
    role = m.role_de(cid)
    if not role:
        raise ReglaDeJuego(i18n.t('sin_rol'))

    if t == 'elegir_modo':
        m.elegir_modo(role, msg.modo)
    elif t == 'listo':
        m.listo(role, msg.valor)
    elif t == 'iniciar':
        motivo = m.iniciar()
        if motivo:
            raise ReglaDeJuego(motivo, codigo=codigo)
        if codigo not in tick_tasks:
            tick_tasks[codigo] = asyncio.create_task(run_match(codigo))
        evento(logging.INFO, 'partida_iniciada', codigo=codigo)
    elif t == 'pausar':
        m.pausar(msg.valor)
    elif t == 'atacar':
        if role != 'attacker':
            raise ReglaDeJuego('Solo el atacante puede atacar')
        if not config.feature_activa(msg.tecnicaId):
            raise ReglaDeJuego('Técnica deshabilitada por configuración', tecnica=msg.tecnicaId)
        motivo = m.encolar_ataque({'tecnicaId': msg.tecnicaId, 'nodoId': msg.nodoId})
        if motivo:
            raise ReglaDeJuego(motivo, tecnica=msg.tecnicaId, nodo=msg.nodoId)
    elif t == 'responder':
        if role != 'defender':
            raise ReglaDeJuego('Solo el defensor puede responder')
        if not config.feature_activa(msg.respuesta):
            raise ReglaDeJuego('Respuesta deshabilitada por configuración', respuesta=msg.respuesta)
        motivo = m.encolar_respuesta({'respuesta': msg.respuesta, 'nodoId': msg.nodoId})
        if motivo:
            raise ReglaDeJuego(motivo, respuesta=msg.respuesta, nodo=msg.nodoId)

    await broadcast(codigo)
    return cid


@app.get('/health')
async def health():
    return {'ok': True, 'partidas': len(partidas), 'clientes': len(cliente_socket)}


@app.get('/metrics')
async def metrics():
    """Observabilidad (Sesión 5): contadores del servidor en JSON."""
    return JSONResponse({'partidas_vivas': len(partidas), 'clientes': len(cliente_socket), **contadores})


# ---- API REST de lectura (Unidad 3: distribución/integración) ----
# El WebSocket es el canal autoritativo del juego (ADR-0003); REST expone lo que
# un cliente externo o un tablero necesita consultar sin jugar: versión, config,
# catálogos y estado de partidas. Solo lectura — ninguna muta el juego.

@app.get('/api/version')
async def api_version():
    return {'producto': 'Project X', 'version': VERSION, 'tickSeg': TICK_SEG}


@app.get('/api/config')
async def api_config():
    """Config efectiva y feature flags activos (sin secretos)."""
    return config.publico()


@app.get('/api/escenarios')
async def api_escenarios():
    """Niveles disponibles, filtrados por feature flag de dificultad."""
    niveles = catalogo_escenarios()
    if not config.FEATURES.get('nivel_dificil', True):
        niveles = [n for n in niveles if n['id'] != 'datacenter02']
    return {'escenarios': niveles}


@app.get('/api/tecnicas')
async def api_tecnicas():
    return {'tecnicas': TECNICAS_PUB, 'respuestas': RESPUESTAS_PUB}


@app.get('/api/partidas')
async def api_partidas():
    """Listado de partidas vivas (para espectadores/tablero)."""
    return {'partidas': [{'codigo': c, 'estado': m.estado, 'escenario': m.escenario['id'],
                          'tick': m.engine.tick, 'ganador': m.ganador} for c, m in partidas.items()]}


# ---- servir el frontend construido (si existe) ----
if WEB_DIST.exists():
    app.mount('/', StaticFiles(directory=str(WEB_DIST), html=True), name='web')
else:
    @app.get('/')
    async def sin_build():
        return PlainTextResponse('Project X backend OK. Build web no encontrado (modo dev: usa Vite en :5174).')


if __name__ == '__main__':
    import uvicorn
    print(f'Project X (FastAPI) escuchando en http://0.0.0.0:{PORT}')
    print(f'Desde otra PC en la LAN: http://<IP-DE-ESTA-PC>:{PORT}')
    uvicorn.run(app, host='0.0.0.0', port=PORT, ws='wsproto')
