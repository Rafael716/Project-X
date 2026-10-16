from __future__ import annotations
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

Role = Literal['attacker', 'defender', 'spectator']
Phase = Literal['recon', 'acceso_inicial', 'escalada', 'movimiento_lateral', 'exfiltracion']
NodeType = Literal['workstation', 'server', 'router', 'database', 'honeypot']
NodeState = Literal['limpio', 'sondeado', 'comprometido', 'aislado', 'honeypot']
MatchState = Literal['lobby', 'lista', 'en_curso', 'pausada', 'terminada']
PlayMode = Literal['manual', 'autoplay']
Winner = Optional[Literal['attacker', 'defender', 'empate']]
ResponseKind = Literal['aislar', 'terminar_proceso', 'honeypot', 'bloquear_ip', 'parchear_env']

class AttackIntent(BaseModel):
    tecnicaId: str
    nodoId: str

class RespondIntent(BaseModel):
    respuesta: ResponseKind
    nodoId: str

class Vulnerability(BaseModel):
    id: str
    nombre: Optional[str] = None
    cve: Optional[str] = None
    dificultad: float = 0.5
    tactica: str
    descripcion: Optional[str] = None

class LootItem(BaseModel):
    id: str
    tick: int
    nodoId: str
    nodoNombre: str
    item: str
    tipo: Literal['env', 'doc', 'cred', 'db']
    secreto: str

class TerminalEntry(BaseModel):
    id: str
    tick: int
    lado: Role
    cmd: str
    salida: str
    tipo: Literal['cmd', 'output', 'alerta', 'exito', 'error'] = 'output'
    nodoId: Optional[str] = None

class SimNode(BaseModel):
    id: str
    nombre: str
    tipo: NodeType
    servicios: List[str] = Field(default_factory=list)
    vulnerabilidades: List[Vulnerability] = Field(default_factory=list)
    archivosSensibles: List[str] = Field(default_factory=list)
    valor: int = 1
    estado: NodeState = 'limpio'
    fase: Optional[Phase] = None
    compromisoReal: bool = False
    posturaDefensiva: float = 0.0
    score: float = 0.0
    senales: Dict[str, float] = Field(default_factory=dict)
    aisladoHasta: Optional[int] = None

class Edge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(..., alias='from')
    to: str
    tipo: Literal['red', 'actividad'] = 'red'
    edad: Optional[int] = None

class GameEvent(BaseModel):
    tick: int
    id: str
    tipo: Literal['benigno', 'ataque', 'deteccion', 'respuesta', 'sistema']
    lado: Optional[Role] = None
    nodoId: Optional[str] = None
    texto: str
    exito: Optional[bool] = None
    malicioso: Optional[bool] = None

class Alert(BaseModel):
    tick: int
    nodoId: str
    score: float
    senales: Dict[str, float] = Field(default_factory=dict)
    verdadera: bool

class AgentThought(BaseModel):
    tick: int
    lado: Role
    observacion: str
    razonamiento: str
    accion: str

class Metrics(BaseModel):
    mttd: Optional[int] = None
    mttr: Optional[int] = None
    disponibilidad: float = 1.0
    datosExfiltrados: int = 0
    metaExfiltracion: int = 6
    alertasTotales: int = 0
    alertasFalsas: int = 0

class PlayerSlot(BaseModel):
    role: Role
    nombre: str = ''
    listo: bool = False
    conectado: bool = False
    modo: PlayMode = 'manual'

class GameState(BaseModel):
    codigo: str
    estado: MatchState
    escenarioId: str
    tick: int
    tickMax: int
    nodos: List[SimNode]
    aristas: List[Edge]
    eventos: List[GameEvent] = Field(default_factory=list)
    alertas: List[Alert] = Field(default_factory=list)
    pensamientos: List[AgentThought] = Field(default_factory=list)
    metricas: Metrics
    jugadores: List[PlayerSlot] = Field(default_factory=list)
    ganador: Winner = None
    loot: List[LootItem] = Field(default_factory=list)
    terminalLogs: List[TerminalEntry] = Field(default_factory=list)

class TechniqueMeta(BaseModel):
    id: str
    nombre: str
    tacticaMitre: str
    faseProduce: Phase
    faseRequiere: Optional[Phase] = None
    ruido: Literal['bajo', 'medio', 'alto']
    facilidadBase: float
    descripcion: str
    comandoEjemplo: Optional[str] = None

class ResponseMeta(BaseModel):
    id: ResponseKind
    nombre: str
    descripcion: str
    comandoEjemplo: Optional[str] = None

TICK_MS = 250
