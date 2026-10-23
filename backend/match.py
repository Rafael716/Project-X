"""Partida: ciclo de vida (lobby -> en_curso -> terminada), roles, bucle de tick.
El bucle temporal lo conduce app.py (asyncio)."""

import estados
from agents import atacante_heuristico, atacante_minimo, defensor_heuristico, defensor_minimo
from engine import Engine
from resiliencia import PoliticaResiliente
from scenario import cargar_escenario

ROLES = ['attacker', 'defender', 'spectator']


def _slot(role):
    return {'role': role, 'nombre': '', 'listo': False, 'conectado': False, 'modo': 'manual', 'clientId': None}


class Match:
    def __init__(self, codigo, escenario_id, semilla):
        self.codigo = codigo
        self.escenario = cargar_escenario(escenario_id)
        self.estado = estados.INICIAL   # máquina de estados table-driven (estados.py)
        self.semilla = semilla
        self.ganador = None
        self.engine = Engine(self.escenario, semilla)
        self.slots = {r: _slot(r) for r in ROLES}
        self.pendingAttack = None
        self.pendingRespond = None
        # Proxy de resiliencia (Sesión 7): reloj = tick del motor para que el
        # circuit breaker también sea determinista (ADR-0004).
        reloj = lambda: self.engine.tick
        self.politica_atacante = PoliticaResiliente(atacante_heuristico, atacante_minimo, 'atacante', reloj=reloj)
        self.politica_defensor = PoliticaResiliente(defensor_heuristico, defensor_minimo, 'defensor', reloj=reloj)

    # ---- lobby ----
    def unir(self, client_id, nombre, role):
        s = self.slots[role]
        if role != 'spectator' and s['clientId'] and s['clientId'] != client_id:
            return 'Ese rol ya está tomado'
        s['clientId'] = client_id
        s['nombre'] = nombre
        s['conectado'] = True
        return None

    def reconectar(self, client_id):
        for r in ROLES:
            if self.slots[r]['clientId'] == client_id:
                self.slots[r]['conectado'] = True
                return r
        return None

    def desconectar(self, client_id):
        for r in ROLES:
            if self.slots[r]['clientId'] == client_id:
                self.slots[r]['conectado'] = False

    def role_de(self, client_id):
        for r in ROLES:
            if self.slots[r]['clientId'] == client_id:
                return r
        return None

    def elegir_modo(self, role, modo):
        self.slots[role]['modo'] = modo

    def listo(self, role, v):
        self.slots[role]['listo'] = v
        ambos = self.slots['attacker']['listo'] and self.slots['defender']['listo']
        if ambos and estados.puede(self.estado, 'ambos_listos'):
            self.estado = estados.transita(self.estado, 'ambos_listos')
        elif not ambos and estados.puede(self.estado, 'no_listo'):
            self.estado = estados.transita(self.estado, 'no_listo')

    def iniciar(self):
        if not self.slots['attacker']['conectado'] or not self.slots['defender']['conectado']:
            return 'Faltan jugadores'
        if not (self.slots['attacker']['listo'] and self.slots['defender']['listo']):
            return 'Ambos deben estar listos'
        if not estados.puede(self.estado, 'iniciar'):
            return 'La partida ya empezó o terminó'
        self.estado = estados.transita(self.estado, 'iniciar')
        return None

    def pausar(self, v):
        evento = 'pausar' if v else 'reanudar'
        if estados.puede(self.estado, evento):
            self.estado = estados.transita(self.estado, evento)

    # ---- intents manuales ----
    def encolar_ataque(self, i):
        if self.estado != 'en_curso':
            return 'La partida no está en curso'
        motivo = self.engine.validar_ataque(i)
        if motivo:
            return motivo
        from techniques import TECNICA_POR_ID
        t = TECNICA_POR_ID.get(i['tecnicaId'])
        if t and self.engine.energia['attacker'] < t.costo:
            return f"Energía insuficiente ({self.engine.energia['attacker']}/{t.costo})"
        self.pendingAttack = i
        return None

    def encolar_respuesta(self, i):
        if self.estado != 'en_curso':
            return 'La partida no está en curso'
        from response import RESPUESTA_POR_ID
        r = RESPUESTA_POR_ID.get(i['respuesta'])
        if r and self.engine.energia['defender'] < r.costo:
            return f"Energía insuficiente ({self.engine.energia['defender']}/{r.costo})"
        self.pendingRespond = i
        return None

    # ---- un tick (lo llama el bucle de app.py) ----
    def tick_once(self):
        if self.estado != 'en_curso':
            return
        ataque = self.pendingAttack
        respuesta = self.pendingRespond
        if self.slots['attacker']['modo'] == 'autoplay':
            ataque = self.politica_atacante.decidir(self.engine)[0]
        if self.slots['defender']['modo'] == 'autoplay':
            respuesta = self.politica_defensor.decidir(self.engine)[0]

        self.engine.avanzar(ataque, respuesta)
        self.pendingAttack = None
        self.pendingRespond = None

        if self.engine.terminada() and estados.puede(self.estado, 'fin'):
            self.estado = estados.transita(self.estado, 'fin')
            self.ganador = self.engine.ganador()

    # ---- proyección a GameState para la UI ----
    def snapshot(self):
        return {
            'codigo': self.codigo,
            'estado': self.estado,
            'escenarioId': self.escenario['id'],
            'tick': self.engine.tick,
            'tickMax': self.engine.tickMax,
            'nodos': self.engine.nodos,
            'aristas': self.engine.aristas,
            'eventos': self.engine.eventos,
            'alertas': self.engine.alertas,
            'pensamientos': self.engine.pensamientos,
            'metricas': self.engine.metricas(),
            'ganador': self.ganador,
            'loot': self.engine.loot,
            'terminalLogs': self.engine.terminalLogs,
            'jugadores': [{k: v for k, v in self.slots[r].items() if k != 'clientId'} for r in ROLES],
        }
