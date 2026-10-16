import type {
  GameState, PlayerSlot, Role, PlayMode, MatchState, Winner,
} from '../../shared/protocol';
import { TICK_MS } from '../../shared/protocol';
import { Engine, AttackIntent, RespondIntent } from './engine';
import { Scenario, ESCENARIOS } from './scenario';
import { atacanteHeuristico, defensorHeuristico } from './agents';

interface Slot extends PlayerSlot { clientId: string | null; }

export class Match {
  engine: Engine;
  escenario: Scenario;
  estado: MatchState = 'lobby';
  semilla: number;
  ganador: Winner = null;
  private slots: Record<Role, Slot> = {
    attacker: slot('attacker'), defender: slot('defender'), spectator: slot('spectator'),
  };
  private pendingAttack: AttackIntent | null = null;
  private pendingRespond: RespondIntent | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(public codigo: string, escenarioId: string, semilla: number,
              private onBroadcast: (s: GameState) => void) {
    const factory = ESCENARIOS[escenarioId] ?? ESCENARIOS.pymes01;
    this.escenario = factory();
    this.semilla = semilla;
    this.engine = new Engine(this.escenario, semilla);
  }

  // ---- lobby ----
  unir(clientId: string, nombre: string, role: Role): string | null {
    const s = this.slots[role];
    if (role !== 'spectator' && s.clientId && s.clientId !== clientId) return 'Ese rol ya está tomado';
    s.clientId = clientId; s.nombre = nombre; s.conectado = true;
    return null;
  }
  reconectar(clientId: string): Role | null {
    for (const r of Object.keys(this.slots) as Role[]) {
      if (this.slots[r].clientId === clientId) { this.slots[r].conectado = true; return r; }
    }
    return null;
  }
  desconectar(clientId: string): void {
    for (const r of Object.keys(this.slots) as Role[]) if (this.slots[r].clientId === clientId) this.slots[r].conectado = false;
  }
  roleDe(clientId: string): Role | null {
    for (const r of Object.keys(this.slots) as Role[]) if (this.slots[r].clientId === clientId) return r;
    return null;
  }

  elegirModo(role: Role, modo: PlayMode): void { this.slots[role].modo = modo; }
  listo(role: Role, v: boolean): void {
    this.slots[role].listo = v;
    if (this.slots.attacker.listo && this.slots.defender.listo && this.estado === 'lobby') this.estado = 'lista';
  }
  iniciar(): string | null {
    if (!this.slots.attacker.conectado || !this.slots.defender.conectado) return 'Faltan jugadores';
    if (!(this.slots.attacker.listo && this.slots.defender.listo)) return 'Ambos deben estar listos';
    this.estado = 'en_curso';
    this.timer = setInterval(() => this.loop(), TICK_MS);
    return null;
  }
  pausar(v: boolean): void {
    if (v && this.estado === 'en_curso') this.estado = 'pausada';
    else if (!v && this.estado === 'pausada') this.estado = 'en_curso';
  }

  // ---- intents de jugadores (modo manual) ----
  encolarAtaque(i: AttackIntent): string | null {
    if (this.estado !== 'en_curso') return 'La partida no está en curso';
    const motivo = this.engine.validarAtaque(i);
    if (motivo) return motivo;
    this.pendingAttack = i; return null;
  }
  encolarRespuesta(i: RespondIntent): string | null {
    if (this.estado !== 'en_curso') return 'La partida no está en curso';
    this.pendingRespond = i; return null;
  }

  // ---- bucle de tick (doc 05 §2) ----
  private loop(): void {
    if (this.estado !== 'en_curso') return;
    // Decidir intents: autoplay -> agente; manual -> lo encolado por el jugador.
    let ataque = this.pendingAttack;
    let respuesta = this.pendingRespond;
    if (this.slots.attacker.modo === 'autoplay') ataque = atacanteHeuristico.decidir(this.engine).intent;
    if (this.slots.defender.modo === 'autoplay') respuesta = defensorHeuristico.decidir(this.engine).intent;

    this.engine.avanzar({ ataque, respuesta });
    this.pendingAttack = null; this.pendingRespond = null;

    if (this.engine.terminada()) {
      this.estado = 'terminada';
      this.ganador = this.engine.ganador();
      if (this.timer) { clearInterval(this.timer); this.timer = null; }
    }
    this.onBroadcast(this.snapshot());
  }

  detener(): void { if (this.timer) clearInterval(this.timer); this.timer = null; }

  // ---- proyección a GameState para la UI ----
  snapshot(): GameState {
    return {
      codigo: this.codigo,
      estado: this.estado,
      escenarioId: this.escenario.id,
      tick: this.engine.tick,
      tickMax: this.engine.tickMax,
      nodos: this.engine.nodos,
      aristas: this.engine.aristas,
      eventos: this.engine.eventos,
      alertas: this.engine.alertas,
      pensamientos: this.engine.pensamientos,
      metricas: this.engine.metricas(),
      ganador: this.ganador,
      loot: this.engine.loot,
      terminalLogs: this.engine.terminalLogs,
      jugadores: (Object.keys(this.slots) as Role[]).map(r => {
        const { clientId, ...pub } = this.slots[r]; return pub;
      }),
    };
  }

  replay() {
    return { semilla: this.semilla, escenarioId: this.escenario.id, eventos: this.engine.eventos, metricas: this.engine.metricas() };
  }
}

function slot(role: Role): Slot {
  return { role, nombre: '', listo: false, conectado: false, modo: 'manual', clientId: null };
}
