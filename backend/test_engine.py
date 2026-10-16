"""Invariantes del motor (doc/06 §9). Port de engine.test.ts. Ejecutar: pytest -q"""

from engine import Engine
from scenario import pymes01
from agents import atacante_heuristico, defensor_heuristico


def _corre(seed, auto=True):
    e = Engine(pymes01(), seed)
    i = 0
    while i < 240 and not e.terminada():
        a = atacante_heuristico.decidir(e).intent if auto else None
        d = defensor_heuristico.decidir(e).intent if auto else None
        e.avanzar(a, d)
        i += 1
    return e


def test_inv1_no_exfil_sin_compromiso():
    e = Engine(pymes01(), 7)
    assert e.validar_ataque({'tecnicaId': 'exfil', 'nodoId': 'db'}) is not None


def test_inv2_nodo_aislado_no_avanza():
    e = Engine(pymes01(), 3)
    e.nodo('ws1')['estado'] = 'aislado'
    assert e.validar_ataque({'tecnicaId': 'portscan', 'nodoId': 'ws1'}) is not None


def test_inv3_metricas_estables_tras_terminar():
    e = _corre(42)
    assert e.metricas() == e.metricas()


def test_inv4_determinismo():
    a = _corre(12345)
    b = _corre(12345)
    assert a.tick == b.tick
    assert a.ganador() == b.ganador()
    assert a.metricas()['datosExfiltrados'] == b.metricas()['datosExfiltrados']


def test_termina_con_ganador_valido():
    e = _corre(99)
    assert e.terminada()
    assert e.ganador() in ('attacker', 'defender', 'empate')


def test_cadena_completable_vs_pasivo():
    # Atacante autoplay vs defensor que no hace nada -> debe poder exfiltrar.
    e = Engine(pymes01(), 131)
    i = 0
    while i < 240 and not e.terminada():
        e.avanzar(atacante_heuristico.decidir(e).intent, None)
        i += 1
    assert e.metricas()['datosExfiltrados'] > 0
