// Contrato tipado compartido entre servidor (Node) y web (React).
// Es la única fuente de verdad de la forma de los datos. ADR-0002/0009.

export type Role = 'attacker' | 'defender' | 'spectator';
export type Phase = 'recon' | 'acceso_inicial' | 'escalada' | 'movimiento_lateral' | 'exfiltracion';
export type NodeType = 'workstation' | 'server' | 'router' | 'database' | 'honeypot';
export type NodeState = 'limpio' | 'sondeado' | 'comprometido' | 'aislado' | 'honeypot';
export type MatchState = 'lobby' | 'lista' | 'en_curso' | 'pausada' | 'terminada';
export type PlayMode = 'manual' | 'autoplay';
export type Winner = 'attacker' | 'defender' | 'empate' | null;

export interface Vulnerability {
  id: string;
  nombre?: string;
  cve?: string;
  dificultad: number; // 0..1 (1 = muy difícil de explotar)
  tactica: string;
  descripcion?: string;
}

export interface LootItem {
  id: string;
  tick: number;
  nodoId: string;
  nodoNombre: string;
  item: string;
  tipo: 'env' | 'doc' | 'cred' | 'db';
  secreto: string;
}

export interface TerminalEntry {
  id: string;
  tick: number;
  lado: Role;
  cmd: string;
  salida: string;
  tipo: 'cmd' | 'output' | 'alerta' | 'exito' | 'error';
  nodoId?: string;
}

export interface SimNode {
  id: string;
  nombre: string;
  tipo: NodeType;
  servicios: string[];
  vulnerabilidades: Vulnerability[];
  archivosSensibles?: string[];
  valor: number;              // importancia del nodo (datos / disponibilidad)
  estado: NodeState;
  fase: Phase | null;         // fase de kill chain alcanzada por el atacante en este nodo
  compromisoReal: boolean;    // ¿el atacante realmente lo comprometió? (para penalizar FP)
  posturaDefensiva: number;   // 0..1, sube con honeypot/vigilancia
  score: number;              // score de anomalía del detector 0..1
  senales: Record<string, number>; // desglose explicable del score
  aisladoHasta?: number;      // tick en que el aislamiento expira (el host vuelve online)
}

export interface Edge {
  from: string;
  to: string;
  tipo: 'red' | 'actividad'; // red = topología fija; actividad = dinámica (envejece)
  edad?: number;
}

export interface GameEvent {
  tick: number;
  id: string;
  tipo: 'benigno' | 'ataque' | 'deteccion' | 'respuesta' | 'sistema';
  lado?: Role;
  nodoId?: string;
  texto: string;
  exito?: boolean;
  malicioso?: boolean; // verdad-terreno: ¿este evento fue realmente malicioso? (para MTTD)
}

export interface Alert {
  tick: number;
  nodoId: string;
  score: number;
  senales: Record<string, number>;
  verdadera: boolean; // verdad-terreno: ¿había compromiso real? (TP vs FP)
}

export interface AgentThought {
  tick: number;
  lado: Role;
  observacion: string;
  razonamiento: string;
  accion: string;
}

export interface Metrics {
  mttd: number | null;   // ticks hasta primera alerta verdadera
  mttr: number | null;   // ticks hasta contención tras detección
  disponibilidad: number; // 0..1
  datosExfiltrados: number;
  metaExfiltracion: number;
  alertasTotales: number;
  alertasFalsas: number;
}

export interface PlayerSlot {
  role: Role;
  nombre: string;
  listo: boolean;
  conectado: boolean;
  modo: PlayMode;
}

export interface GameState {
  codigo: string;
  estado: MatchState;
  escenarioId: string;
  tick: number;
  tickMax: number;
  nodos: SimNode[];
  aristas: Edge[];
  eventos: GameEvent[];      // ventana reciente
  alertas: Alert[];
  pensamientos: AgentThought[]; // ventana reciente
  metricas: Metrics;
  jugadores: PlayerSlot[];
  ganador: Winner;
  loot: LootItem[];
  terminalLogs: TerminalEntry[];
}

// ---- Catálogo de técnicas (se envía al cliente para pintar el panel) ----
export interface TechniqueMeta {
  id: string;
  nombre: string;
  tacticaMitre: string;
  faseProduce: Phase;
  faseRequiere: Phase | null;
  ruido: 'bajo' | 'medio' | 'alto';
  facilidadBase: number; // 0..1
  descripcion: string;
  comandoEjemplo?: string;
}

export type ResponseKind =
  | 'aislar'
  | 'terminar_proceso'
  | 'honeypot'
  | 'bloquear_ip'
  | 'parchear_env'
  | 'parchear_vuln'
  | 'yara_memory_scan'
  | 'canary_token'
  | 'rotate_keys';
export interface ResponseMeta {
  id: ResponseKind;
  nombre: string;
  descripcion: string;
  comandoEjemplo?: string;
}

// ============ Mensajes Cliente -> Servidor ============
export type ClientMsg =
  | { t: 'crear'; nombre: string; role: Role; escenarioId: string; semilla?: number }
  | { t: 'unir'; codigo: string; nombre: string; role: Role }
  | { t: 'elegir_modo'; modo: PlayMode }
  | { t: 'listo'; valor: boolean }
  | { t: 'iniciar' }
  | { t: 'pausar'; valor: boolean }
  | { t: 'atacar'; tecnicaId: string; nodoId: string }
  | { t: 'responder'; respuesta: ResponseKind; nodoId: string }
  | { t: 'reconectar'; codigo: string; clientId: string };

// ============ Mensajes Servidor -> Cliente ============
export type ServerMsg =
  | { t: 'bienvenida'; clientId: string; codigo: string; role: Role; tecnicas: TechniqueMeta[]; respuestas: ResponseMeta[] }
  | { t: 'estado'; estado: GameState }
  | { t: 'error'; mensaje: string };

export const TICK_MS = 250;
