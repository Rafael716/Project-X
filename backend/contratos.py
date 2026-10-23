"""Diseño por Contrato (Sesión 3) con aserciones ejecutables.

- requiere(...)  -> PRECONDICIÓN: obligación del cliente (quien llama).
- asegura(...)   -> POSTCONDICIÓN: obligación del proveedor (esta rutina).
- invariantes_del_motor(e) -> INVARIANTE: la "constitución" del motor, se verifica
  antes de devolver el control al final de cada tick.

Contrato vs barricada: los contratos viven ENTRE módulos internos (asumen
confianza: si fallan es un bug -> fail-fast). La validación del input del
jugador vive en barricada.py (asume hostilidad -> se rechaza con elegancia).

Las condiciones son CONSULTAS puras (CQS): evaluarlas no cambia el estado.

Se pueden apagar en producción con PX_CONTRATOS=0 (como `java -ea`), por
rendimiento; por defecto están activos porque esto es un proyecto académico.
"""

import os

from errores import ContratoRoto

ACTIVOS = os.environ.get('PX_CONTRATOS', '1') != '0'


def requiere(condicion: bool, mensaje: str, **contexto) -> None:
    if ACTIVOS and not condicion:
        raise ContratoRoto(f'Precondición violada: {mensaje}', tipo='pre', **contexto)


def asegura(condicion: bool, mensaje: str, **contexto) -> None:
    if ACTIVOS and not condicion:
        raise ContratoRoto(f'Postcondición violada: {mensaje}', tipo='post', **contexto)


def invariantes_del_motor(e) -> None:
    """Reglas que deben ser ciertas tras CUALQUIER tick (doc 06 §9)."""
    if not ACTIVOS:
        return
    for n in e.nodos:
        ctx = {'nodo': n['id'], 'tick': e.tick}
        if not 0.0 <= n['score'] <= 1.0:
            raise ContratoRoto('Invariante: score fuera de [0,1]', tipo='inv', score=n['score'], **ctx)
        if not 0.0 <= n['posturaDefensiva'] <= 1.0:
            raise ContratoRoto('Invariante: postura fuera de [0,1]', tipo='inv', **ctx)
        if n['compromisoReal'] and n['fase'] is None:
            raise ContratoRoto('Invariante: compromiso real sin fase', tipo='inv', **ctx)
    for nid in e.exfiltrados:
        n = e.nodo(nid)
        if n is None or n['valor'] <= 0:
            raise ContratoRoto('Invariante: exfiltración de un nodo inexistente o sin valor', tipo='inv', nodo=nid)
    if not 0 <= e.datos_exfiltrados <= e.suma_valor:
        raise ContratoRoto('Invariante: datos exfiltrados fuera de rango', tipo='inv', datos=e.datos_exfiltrados)
    for lado, energia in e.energia.items():
        if not 0 <= energia <= e.ENERGIA_MAX:
            raise ContratoRoto('Invariante: energía fuera de rango', tipo='inv', lado=lado, energia=energia)
    if not 0.0 <= e.disponibilidad() <= 1.0:
        raise ContratoRoto('Invariante: disponibilidad fuera de [0,1]', tipo='inv')
