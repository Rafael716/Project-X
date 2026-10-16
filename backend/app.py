"""Project X — Backend FastAPI. Gateway WebSocket autoritativo (ADR-0003) +
servido del build de la web. Port de server.ts.

Dev:  uvicorn app:app --host 0.0.0.0 --port 8787 --ws wsproto --reload
Prod: python app.py   (sirve también web/dist en el mismo puerto -> ideal ngrok/LAN)
"""

import os
import json
import random
import asyncio
import secrets
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from techniques import TECNICAS
from response import RESPUESTAS
from match import Match

PORT = int(os.environ.get('PORT', '8787'))
TICK_SEG = 0.25  # 250 ms, igual que TICK_MS del protocolo
WEB_DIST = Path(__file__).resolve().parent.parent / 'web' / 'dist'

app = FastAPI(title='Project X')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

partidas: dict[str, Match] = {}
cliente_socket: dict[str, WebSocket] = {}   # clientId -> WebSocket
cliente_partida: dict[str, str] = {}        # clientId -> codigo
tick_tasks: dict[str, asyncio.Task] = {}    # codigo -> task del bucle

# Un candado POR socket: el bucle de ticks y los handlers pueden escribir al mismo
# socket a la vez (la librería WS revienta si se solapan). El candado es por-socket,
# no global, para que un cliente lento no congele el broadcast a los demás; y cada
# envío lleva timeout para no bloquear su propio candado para siempre.
_locks: dict[int, asyncio.Lock] = {}


def _lock_for(sock: WebSocket) -> asyncio.Lock:
    k = id(sock)
    lk = _locks.get(k)
    if lk is None:
        lk = asyncio.Lock()
        _locks[k] = lk
    return lk


async def _send(sock: WebSocket, data: str) -> None:
    try:
        async with _lock_for(sock):
            await asyncio.wait_for(sock.send_text(data), timeout=5)
    except Exception:
        pass


def nuevo_codigo() -> str:
    abc = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        c = ''.join(random.choice(abc) for _ in range(6))
        if c not in partidas:
            return c


def nuevo_client_id() -> str:
    return secrets.token_hex(4)


async def enviar(sock: WebSocket, msg: dict) -> None:
    await _send(sock, json.dumps(msg, ensure_ascii=False))


async def error(sock: WebSocket, mensaje: str) -> None:
    await enviar(sock, {'t': 'error', 'mensaje': mensaje})


async def broadcast(codigo: str) -> None:
    m = partidas.get(codigo)
    if not m:
        return
    data = json.dumps({'t': 'estado', 'estado': m.snapshot()}, ensure_ascii=False)
    for cid, cod in list(cliente_partida.items()):
        if cod != codigo:
            continue
        sock = cliente_socket.get(cid)
        if sock is not None:
            await _send(sock, data)


async def bienvenida(sock: WebSocket, client_id: str, codigo: str, role: str) -> None:
    await enviar(sock, {'t': 'bienvenida', 'clientId': client_id, 'codigo': codigo,
                        'role': role, 'tecnicas': TECNICAS, 'respuestas': RESPUESTAS})
    await broadcast(codigo)


async def run_match(codigo: str) -> None:
    """Bucle de ticks de una partida (equivale al setInterval de match.ts)."""
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
            m.tick_once()
            await broadcast(codigo)
            if m.estado == 'terminada':
                break
    finally:
        tick_tasks.pop(codigo, None)


@app.websocket('/ws')
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    cid = nuevo_client_id()
    cliente_socket[cid] = ws
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await error(ws, 'JSON inválido')
                continue
            cid = await manejar(ws, cid, msg)
    except WebSocketDisconnect:
        cod = cliente_partida.get(cid)
        if cod:
            m = partidas.get(cod)
            if m:
                m.desconectar(cid)
                await broadcast(cod)
        cliente_socket.pop(cid, None)
        _locks.pop(id(ws), None)


async def manejar(ws: WebSocket, cid: str, msg: dict) -> str:
    """Procesa un mensaje; devuelve el clientId activo (puede cambiar al reconectar)."""
    t = msg.get('t')

    if t == 'crear':
        codigo = nuevo_codigo()
        semilla = msg.get('semilla')
        if semilla is None:
            semilla = random.randint(0, 2_000_000_000)
        m = Match(codigo, msg['escenarioId'], semilla)
        partidas[codigo] = m
        m.unir(cid, msg['nombre'], msg['role'])
        cliente_partida[cid] = codigo
        await bienvenida(ws, cid, codigo, msg['role'])
        return cid

    if t == 'unir':
        m = partidas.get(msg['codigo'])
        if not m:
            await error(ws, 'Código inexistente')
            return cid
        motivo = m.unir(cid, msg['nombre'], msg['role'])
        if motivo:
            await error(ws, motivo)
            return cid
        cliente_partida[cid] = msg['codigo']
        await bienvenida(ws, cid, msg['codigo'], msg['role'])
        return cid

    if t == 'reconectar':
        m = partidas.get(msg['codigo'])
        if not m:
            await error(ws, 'Código inexistente')
            return cid
        prev = msg['clientId']
        # reasignar este socket al clientId previo
        cliente_socket.pop(cid, None)
        cliente_socket[prev] = ws
        role = m.reconectar(prev)
        if not role:
            await error(ws, 'No estabas en esta partida')
            return prev
        cliente_partida[prev] = msg['codigo']
        await bienvenida(ws, prev, msg['codigo'], role)
        return prev

    # acciones que requieren partida + rol
    codigo = cliente_partida.get(cid)
    m = partidas.get(codigo) if codigo else None
    if not m or not codigo:
        await error(ws, 'No estás en una partida')
        return cid
    role = m.role_de(cid)
    if not role:
        await error(ws, 'Sin rol asignado')
        return cid

    if t == 'elegir_modo':
        m.elegir_modo(role, msg['modo'])
    elif t == 'listo':
        m.listo(role, msg['valor'])
    elif t == 'iniciar':
        e = m.iniciar()
        if e:
            await error(ws, e)
            return cid
        if codigo not in tick_tasks:
            tick_tasks[codigo] = asyncio.create_task(run_match(codigo))
    elif t == 'pausar':
        m.pausar(msg['valor'])
    elif t == 'atacar':
        if role != 'attacker':
            await error(ws, 'Solo el atacante puede atacar')
            return cid
        e = m.encolar_ataque({'tecnicaId': msg['tecnicaId'], 'nodoId': msg['nodoId']})
        if e:
            await error(ws, e)
            return cid
    elif t == 'responder':
        if role != 'defender':
            await error(ws, 'Solo el defensor puede responder')
            return cid
        e = m.encolar_respuesta({'respuesta': msg['respuesta'], 'nodoId': msg['nodoId']})
        if e:
            await error(ws, e)
            return cid

    await broadcast(codigo)
    return cid


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
