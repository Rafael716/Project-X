"""Characterization tests (Unidad 4 — Legacy).

A diferencia de los tests de `test_engine.py` (que afirman QUÉ *debería* pasar
según el contrato), estos fijan QUÉ pasa HOY, tal cual, aunque nadie haya
escrito nunca una especificación de ello. Son la red de seguridad para
refactorizar/modernizar el motor: si un cambio altera el curso determinista de
una partida, estos golden reventarán y obligan a decidir si el cambio fue
intencional.

Cómo se obtuvo el golden: se ejecutó la partida y se copió el resultado. No se
"calcula" el valor esperado; se *fotografía* el comportamiento observado.
Para re-generar tras un cambio intencional: correr `golden()` e imprimir.
"""

from engine import Engine
from scenario import cargar_escenario
import agents


def _jugar(escenario_id: str, semilla: int, cap: int = 600):
    """Autoplay determinista del atacante (defensor pasivo) hasta que termina.
    Devuelve la foto final."""
    e = Engine(cargar_escenario(escenario_id), semilla)
    for _ in range(cap):
        intent, _ = agents.atacante_decidir(e)
        e.avanzar(intent, None)
        if e.terminada():
            break
    return {
        'tick': e.tick,
        'exfil': e.datos_exfiltrados,
        'puntosA': e.puntos['attacker'],
        'ganador': e.ganador(),
        'alertas': len(e.alertas),
    }


# Golden fotografiado el 2026-10-23 tras el reajuste de balance (ver docstring).
GOLDEN = {
    ('pymes01', 777): {'tick': 61, 'exfil': 0, 'puntosA': 191, 'ganador': 'attacker', 'alertas': 49},
    ('datacenter02', 42): {'tick': 122, 'exfil': 0, 'puntosA': 225, 'ganador': 'attacker', 'alertas': 60},
}


def test_caracterizacion_pymes01():
    assert _jugar('pymes01', 777) == GOLDEN[('pymes01', 777)]


def test_caracterizacion_datacenter02():
    assert _jugar('datacenter02', 42) == GOLDEN[('datacenter02', 42)]


def test_caracterizacion_es_reproducible():
    """La misma entrada dos veces da la misma foto (base del replay, ADR-0008)."""
    assert _jugar('pymes01', 777) == _jugar('pymes01', 777)


if __name__ == '__main__':
    # re-generar golden tras un cambio intencional
    for (sid, seed) in GOLDEN:
        print(sid, seed, _jugar(sid, seed))
