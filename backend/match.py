"""Partida: ciclo de vida (lobby -> en_curso -> terminada), roles, bucle de tick.
Port de match.ts. El bucle temporal lo conduce app.py (asyncio)."""

from scenario import cargar_escenario
from engine import Engine
from agents import atacante_heuristico, defensor_heuristico

ROLES = ['attacker', 'defender', 'spectator']


def _slot(role):
    return {'role': role, 'nombre': '', 'listo': False, 'conectado': False, 'modo': 'manual', 'clientId': None}


class Match:
    def __init__(self, codigo, escenario_id, semilla):
        self.codigo = codigo
        self.escenario = cargar_escenario(escenario_id)
        self.estado = 'lobby'
        self.semilla = semilla
        self.ganador = None
        self.engine = Engine(self.escenario, semilla)
        self.slots = {r: _slot(r) for r in ROLES}
        self.pendingAttack = None
        self.pendingRespond = None

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
        if self.slots['attacker']['listo'] and self.slots['defender']['listo'] and self.estado == 'lobby':
            self.estado = 'lista'

    def iniciar(self):
        if not self.slots['attacker']['conectado'] or not self.slots['defender']['conectado']:
            return 'Faltan jugadores'
        if not (self.slots['attacker']['listo'] and self.slots['defender']['listo']):
            return 'Ambos deben estar listos'
        self.estado = 'en_curso'
        return None

    def pausar(self, v):
        if v and self.estado == 'en_curso':
            self.estado = 'pausada'
        elif not v and self.estado == 'pausada':
            self.estado = 'en_curso'

    # ---- intents manuales ----
    def encolar_ataque(self, i):
        if self.estado != 'en_curso':
            return 'La partida no está en curso'
        motivo = self.engine.validar_ataque(i)
        if motivo:
            return motivo
        self.pendingAttack = i
        return None

    def encolar_respuesta(self, i):
        if self.estado != 'en_curso':
            return 'La partida no está en curso'
        self.pendingRespond = i
        return None

    # ---- un tick (lo llama el bucle de app.py) ----
    def tick_once(self):
        if self.estado != 'en_curso':
            return
        ataque = self.pendingAttack
        respuesta = self.pendingRespond
        if self.slots['attacker']['modo'] == 'autoplay':
            ataque = atacante_heuristico.decidir(self.engine).intent
        if self.slots['defender']['modo'] == 'autoplay':
            respuesta = defensor_heuristico.decidir(self.engine).intent

        self.engine.avanzar(ataque, respuesta)
        self.pendingAttack = None
        self.pendingRespond = None

        if self.engine.terminada():
            self.estado = 'terminada'
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
