"""Invariantes del motor y de los módulos de construcción (sesiones 3-7).

Ejecutar: pytest -q   (desde backend/, con el venv activo)
"""

import pytest

from agents import atacante_heuristico, defensor_heuristico
from engine import Engine
from scenario import pymes01


def _corre(seed, auto=True, limite=240):
    e = Engine(pymes01(), seed)
    i = 0
    while i < limite and not e.terminada():
        a = atacante_heuristico.decidir(e)[0] if auto else None
        d = defensor_heuristico.decidir(e)[0] if auto else None
        e.avanzar(a, d)
        i += 1
    return e


# -------- doc 06 §9: invariantes clásicos --------
def test_inv1_no_exfil_sin_compromiso():
    e = Engine(pymes01(), 7)
    assert e.validar_ataque({'tecnicaId': 'exfil', 'nodoId': 'db'}) is not None


def test_inv2_nodo_aislado_no_avanza():
    e = Engine(pymes01(), 3)
    e.nodo('ws1')['estado'] = 'aislado'
    assert e.validar_ataque({'tecnicaId': 'portscan', 'nodoId': 'ws1'}) is not None


def test_inv4_determinismo():
    a, b = _corre(12345), _corre(12345)
    assert a.tick == b.tick
    assert a.ganador() == b.ganador()
    assert a.metricas()['datosExfiltrados'] == b.metricas()['datosExfiltrados']
    assert a.puntos == b.puntos


def test_termina_con_ganador_valido():
    e = _corre(99)
    assert e.terminada()
    assert e.ganador() in ('attacker', 'defender', 'empate')


def test_cadena_completable_vs_pasivo():
    e = Engine(pymes01(), 131)
    i = 0
    while i < 240 and not e.terminada():
        e.avanzar(atacante_heuristico.decidir(e)[0], None)
        i += 1
    assert e.metricas()['datosExfiltrados'] > 0


# -------- Sesión 2: polimorfismo de técnicas/respuestas --------
def test_dump_lsass_requires_escalada():
    e = Engine(pymes01(), 42)
    assert e.validar_ataque({'tecnicaId': 'dump_lsass', 'nodoId': 'ws1'}) is not None
    ws1 = e.nodo('ws1')
    ws1['fase'], ws1['compromisoReal'] = 'escalada', True
    assert e.validar_ataque({'tecnicaId': 'dump_lsass', 'nodoId': 'ws1'}) is None


def test_parchear_vuln_sube_postura_y_dificultad():
    e = Engine(pymes01(), 42)
    web = e.nodo('web')
    antes = web['posturaDefensiva']
    e.avanzar(None, {'respuesta': 'parchear_vuln', 'nodoId': 'web'})
    assert web['posturaDefensiva'] > antes
    assert all(v['dificultad'] >= 0.7 for v in web['vulnerabilidades'])


def test_persistencia_resiste_sigkill_pero_no_yara():
    e = Engine(pymes01(), 42)
    ws1 = e.nodo('ws1')
    ws1.update(fase='escalada', compromisoReal=True, persistente=True)
    e.avanzar(None, {'respuesta': 'terminar_proceso', 'nodoId': 'ws1'})
    assert ws1['persistente'] and ws1['fase'] == 'escalada'  # el cron la revive
    e.avanzar(None, {'respuesta': 'yara_memory_scan', 'nodoId': 'ws1'})
    assert not ws1['persistente'] and ws1['fase'] == 'acceso_inicial'


# -------- Capa de juego: energía, puntos, combos --------
def test_energia_limita_y_regenera():
    e = Engine(pymes01(), 1)
    e.energia['attacker'] = 0            # tras regen será 1, menos que el costo 2 de scan_docs
    e.avanzar({'tecnicaId': 'scan_docs', 'nodoId': 'ws1'}, None)
    assert e.nodo('ws1')['fase'] is None   # no pudo pagar: nada ocurrió
    assert len(e.loot) == 0
    assert e.energia['attacker'] == e.ENERGIA_REGEN  # regeneró 1, sin gastar


def test_combo_premia_acciones_encadenadas():
    e = Engine(pymes01(), 1)
    e._puntuar('attacker', 10)
    e._puntuar('attacker', 10)
    assert e.puntos['attacker'] == 10 + 11  # segundo golpe vale x1.1


# -------- Sesión 3: contratos (DbC) --------
def test_contrato_detecta_score_corrupto():
    from contratos import invariantes_del_motor
    from errores import ContratoRoto
    e = Engine(pymes01(), 1)
    e.nodo('ws1')['score'] = 5.0  # viola invariante [0,1]
    with pytest.raises(ContratoRoto):
        invariantes_del_motor(e)


# -------- Sesión 4: barricada --------
def test_barricada_rechaza_basura():
    from barricada import parsear
    from errores import EntradaInvalida
    with pytest.raises(EntradaInvalida):
        parsear('no es json {')
    with pytest.raises(EntradaInvalida):
        parsear('{"t": "atacar", "tecnicaId": "noexiste", "nodoId": "ws1"}')
    with pytest.raises(EntradaInvalida):
        parsear('{"t": "crear", "nombre": "' + 'x' * 50 + '", "role": "attacker"}')


def test_barricada_acepta_valido():
    from barricada import parsear
    msg = parsear('{"t": "atacar", "tecnicaId": "portscan", "nodoId": "ws1"}')
    assert msg.t == 'atacar' and msg.tecnicaId == 'portscan'


# -------- Sesión 7: circuit breaker + proxy de resiliencia --------
def test_circuit_breaker_abre_y_se_recupera():
    from resiliencia import ABIERTO, CERRADO, CircuitBreaker
    reloj = [0]
    cb = CircuitBreaker(umbral_fallos=2, espera=10, reloj=lambda: reloj[0])
    cb.fallo(); cb.fallo()
    assert cb.estado == ABIERTO and not cb.permite()
    reloj[0] = 11
    assert cb.permite()  # pasa a semi-abierto
    cb.exito()
    assert cb.estado == CERRADO


def test_proxy_degrada_si_la_politica_primaria_revienta():
    from resiliencia import PoliticaResiliente

    class Rota:
        def decidir(self, e):
            raise RuntimeError('boom')

    class Respaldo:
        def decidir(self, e):
            return None, {'tick': e.tick, 'lado': 'attacker', 'observacion': '', 'razonamiento': 'ok', 'accion': 'hold'}

    e = Engine(pymes01(), 1)
    proxy = PoliticaResiliente(Rota(), Respaldo(), 'test', reloj=lambda: e.tick)
    intent, th = proxy.decidir(e)
    assert intent is None and 'degradado' in th['razonamiento']
