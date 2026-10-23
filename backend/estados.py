"""Máquina de estados de la partida — construcción *table-driven* (Unidad 3).

El ciclo de vida de una partida dejaba de ser un puñado de `if estado == ...`
dispersos: ahora es UNA tabla de transiciones. Añadir o cambiar una transición
es editar un dict, no lógica. Un evento inválido para el estado actual no "no
hace nada en silencio": se rechaza explícito (fail-fast, Sesión 3).

    lobby --ambos_listos--> lista --iniciar--> en_curso --pausar--> pausada
      ^                        |                   |  ^                 |
      +------no_listo----------+                   |  +---reanudar------+
                                                   +--------fin---------> terminada
                                     (también: pausada --fin--> terminada)
"""

from errores import ReglaDeJuego

INICIAL = 'lobby'

# (estado_actual, evento) -> estado_siguiente
TRANSICIONES: dict[tuple[str, str], str] = {
    ('lobby', 'ambos_listos'): 'lista',
    ('lista', 'no_listo'): 'lobby',
    ('lista', 'iniciar'): 'en_curso',
    ('lobby', 'iniciar'): 'en_curso',      # permitido si ya están ambos listos (match revalida)
    ('en_curso', 'pausar'): 'pausada',
    ('pausada', 'reanudar'): 'en_curso',
    ('en_curso', 'fin'): 'terminada',
    ('pausada', 'fin'): 'terminada',
}

ESTADOS = {INICIAL, 'lista', 'en_curso', 'pausada', 'terminada'}
TERMINALES = {'terminada'}


def transita(estado: str, evento: str) -> str:
    """Devuelve el estado siguiente, o lanza ReglaDeJuego si la transición no existe."""
    nuevo = TRANSICIONES.get((estado, evento))
    if nuevo is None:
        raise ReglaDeJuego(f'Transición inválida: {estado} --{evento}-->',
                           estado=estado, evento=evento)
    return nuevo


def puede(estado: str, evento: str) -> bool:
    return (estado, evento) in TRANSICIONES


if __name__ == '__main__':
    # check: el camino feliz llega a terminada; una transición ilegal se rechaza.
    e = INICIAL
    for ev in ('ambos_listos', 'iniciar', 'pausar', 'reanudar', 'fin'):
        e = transita(e, ev)
    assert e == 'terminada', e
    try:
        transita('terminada', 'iniciar')
        raise SystemExit('debió rechazar iniciar desde terminada')
    except ReglaDeJuego:
        pass
    assert not puede('lobby', 'pausar')
    print('estados OK')
