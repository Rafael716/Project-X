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


def _jugar(escenario_id: str, semilla: int, ticks: int):
    """Autoplay determinista del atacante (defensor pasivo). Devuelve la foto final."""
    e = Engine(cargar_escenario(escenario_id), semilla)
    for _ in range(ticks):
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


# Golden fotografiado el 2026-10-23 (ver docstring para re-generar).
GOLDEN = {
    ('pymes01', 777): {'tick': 240, 'exfil': 0, 'puntosA': 300, 'ganador': 'attacker', 'alertas': 40},
    ('datacenter02', 42): {'tick': 240, 'exfil': 0, 'puntosA': 300, 'ganador': 'attacker', 'alertas': 60},
}


def test_caracterizacion_pymes01():
    assert _jugar('pymes01', 777, 240) == GOLDEN[('pymes01', 777)]


def test_caracterizacion_datacenter02():
    assert _jugar('datacenter02', 42, 300) == GOLDEN[('datacenter02', 42)]


def test_caracterizacion_es_reproducible():
    """La misma entrada dos veces da la misma foto (base del replay, ADR-0008)."""
    assert _jugar('pymes01', 777, 240) == _jugar('pymes01', 777, 240)


if __name__ == '__main__':
    # re-generar golden tras un cambio intencional
    for (sid, seed) in GOLDEN:
        print(sid, seed, _jugar(sid, seed, 300))
