import type {
  SimNode, Edge, GameEvent, Alert, AgentThought, Metrics, ResponseKind, LootItem, TerminalEntry, Role,
} from '../../shared/protocol';
import { Rng } from './rng';
import { Scenario } from './scenario';
import { TECNICA_POR_ID, faseIndex, ORDEN_FASE } from './techniques';
import { Detector } from './detector';
import { aplicarRespuesta, RESPUESTAS } from './response';

export interface AttackIntent { tecnicaId: string; nodoId: string; }
export interface RespondIntent { respuesta: ResponseKind; nodoId: string; }

const VENTANA = 60; // cuántos eventos/pensamientos recientes se conservan para la UI

export class Engine {
  rng: Rng;
  nodos: SimNode[];
  aristas: Edge[];
  eventos: GameEvent[] = [];
  alertas: Alert[] = [];
  pensamientos: AgentThought[] = [];
  loot: LootItem[] = [];
  terminalLogs: TerminalEntry[] = [];
  tick = 0;
  tickMax: number;
  detector = new Detector();
  // métricas / verdad-terreno
  private firstMaliciousTick: number | null = null;
  private firstTrueAlertTick: number | null = null;
  private containmentTick: number | null = null;
  private penalDisponibilidad = 0;
  private datosExfiltrados = 0;
  private exfiltrados = new Set<string>();
  private metaExfiltracion: number;
  private sumValor: number;
  objetivo: string;

  constructor(private esc: Scenario, seed: number) {
    this.rng = new Rng(seed);
    this.nodos = esc.nodos.map(n => ({
      ...n,
      vulnerabilidades: [...n.vulnerabilidades],
      archivosSensibles: n.archivosSensibles ? [...n.archivosSensibles] : [],
      senales: {},
    }));
    this.aristas = esc.aristas.map(a => ({ ...a }));
    this.tickMax = esc.tickMax;
    this.metaExfiltracion = esc.metaExfiltracion;
    this.objetivo = esc.objetivo;
    this.sumValor = this.nodos.reduce((s, n) => s + n.valor, 0);
    this.log({ tipo: 'sistema', texto: `Escenario ${esc.nombre} cargado. Objetivo del atacante: exfiltrar ${this.nodoNombre(esc.objetivo)}.` });
    this.logTerminal('attacker', 'projectx-c2 --init --stealth-profile', `[+] C2 Console activada. Target network: ${esc.nombre} | Punto de entrada: ${esc.entrada} | Objetivo crítico: ${this.nodoNombre(esc.objetivo)}`, 'cmd');
    this.logTerminal('defender', 'systemctl status ebpf-soc-daemon', `[+] SOC SecOps activo. Monitores eBPF/XDP desplegados. Analizador de grafos TGNN en escucha.`, 'cmd');
  }

  // --------- consultas de ayuda ----------
  nodo(id: string) { return this.nodos.find(n => n.id === id); }
  nodoNombre(id: string) { return this.nodo(id)?.nombre ?? id; }
  adyacentes(id: string): string[] {
    const r: string[] = [];
    for (const a of this.aristas) {
      if (a.tipo !== 'red') continue;
      if (a.from === id) r.push(a.to);
      if (a.to === id) r.push(a.from);
    }
    return r;
  }
  // Un nodo es alcanzable si es la entrada o es adyacente a un nodo comprometido (foothold).
  alcanzable(id: string): boolean {
    if (id === this.esc.entrada) return true;
    return this.adyacentes(id).some(v => {
      const n = this.nodo(v);
      return n && n.compromisoReal && n.estado !== 'aislado';
    });
  }

  // --------- validación de intents (se usa también para construir la UI) ----------
  // Devuelve null si es válida, o un string con el motivo de rechazo.
  validarAtaque(i: AttackIntent): string | null {
    const n = this.nodo(i.nodoId);
    if (!n) return 'Nodo inexistente';
    if (n.estado === 'aislado') return 'Nodo aislado (contenido)';
    const t = TECNICA_POR_ID.get(i.tecnicaId);
    if (!t) return 'Técnica desconocida';
    const fx = faseIndex(n.fase);
    // Búsqueda profunda de .env, sqli y spray: permitida siempre que el nodo sea alcanzable
    if (t.id === 'scan_docs' || t.id === 'sqli_dump' || t.id === 'phishing_spray') {
      if (!this.alcanzable(i.nodoId)) return 'Nodo no alcanzable (necesitas un foothold adyacente)';
      return null;
    }
    if (t.id === 'dump_lsass') {
      if (fx < faseIndex('escalada')) return 'Requiere privilegios elevados (escalada/root) para volcar memoria de procesos';
      return null;
    }
    if (t.id === 'persist_backdoor') {
      if (fx < faseIndex('acceso_inicial')) return 'Requiere acceso inicial previo en el nodo';
      return null;
    }
    // Pivote lateral: propaga el foothold a un vecino desde un nodo con escalada.
    if (t.id === 'pivot') {
      if (fx >= faseIndex('acceso_inicial')) return 'El nodo ya está comprometido';
      if (!this.tieneSaltoLateral(n.id)) return 'Necesitas un nodo adyacente con privilegios (escalada)';
      return null;
    }
    // Exfiltración: requiere nodo comprometido con datos, una vez por nodo.
    if (t.id === 'exfil') {
      if (fx < faseIndex('acceso_inicial')) return 'Debes comprometer el nodo antes de exfiltrar';
      if (n.valor <= 0) return 'Nodo sin datos de valor';
      if (this.exfiltrados.has(n.id)) return 'Datos ya exfiltrados de este nodo';
      return null;
    }
    // Resto (recon / acceso / escalada): cadena sobre el mismo nodo, debe ser alcanzable.
    if (!this.alcanzable(i.nodoId)) return 'Nodo no alcanzable (necesitas un foothold adyacente)';
    if (fx < faseIndex(t.faseRequiere)) return `Requiere fase previa: ${t.faseRequiere}`;
    if (fx >= faseIndex(t.faseProduce)) return 'Fase ya alcanzada en este nodo';
    return null;
  }

  // Ruta más corta (BFS sobre red) de la entrada al objetivo; la usa el agente para enfocar el ataque.
  private _ruta: string[] | null = null;
  rutaAObjetivo(): string[] {
    if (this._ruta) return this._ruta;
    const prev = new Map<string, string>();
    const q = [this.esc.entrada]; const visto = new Set(q);
    while (q.length) {
      const u = q.shift()!;
      if (u === this.objetivo) break;
      for (const v of this.adyacentes(u)) if (!visto.has(v)) { visto.add(v); prev.set(v, u); q.push(v); }
    }
    const ruta: string[] = []; let c: string | undefined = this.objetivo;
    while (c) { ruta.unshift(c); c = prev.get(c); }
    this._ruta = ruta[0] === this.esc.entrada ? ruta : [this.esc.entrada, this.objetivo];
    return this._ruta;
  }

  // ¿Algún vecino de red está comprometido con privilegios (escalada) para saltar desde él?
  private tieneSaltoLateral(id: string): boolean {
    return this.adyacentes(id).some(v => {
      const n = this.nodo(v);
      return n && n.estado !== 'aislado' && faseIndex(n.fase) >= faseIndex('escalada');
    });
  }

  // --------- aplicar intents dentro del tick ----------
  private resolverAtaque(i: AttackIntent): void {
    const motivo = this.validarAtaque(i);
    const t = TECNICA_POR_ID.get(i.tecnicaId)!;
    const n = this.nodo(i.nodoId);
    const targetLabel = n?.nombre ?? i.nodoId;
    const cmdStr = (t?.comandoEjemplo ?? `${i.tecnicaId} ${i.nodoId}`).replace('{target}', targetLabel);

    if (motivo) {
      this.log({ tipo: 'ataque', lado: 'attacker', nodoId: i.nodoId, malicioso: true, exito: false, texto: `${t?.nombre ?? i.tecnicaId}: rechazado (${motivo})` });
      this.logTerminal('attacker', cmdStr, `[-] EXECUTION REJECTED: ${motivo}`, 'error', i.nodoId);
      return;
    }

    if (this.firstMaliciousTick === null) this.firstMaliciousTick = this.tick;
    const pExito = this.probExito(t.id, n!);
    const exito = this.rng.chance(pExito);
    const ruido = t.ruido;

    this.log({
      tipo: 'ataque', lado: 'attacker', nodoId: n!.id, malicioso: true, exito,
      texto: `${t.nombre} sobre ${n!.nombre} [ruido:${ruido}] (p=${pExito.toFixed(2)}) -> ${exito ? 'ÉXITO' : 'fallo'}`,
    });

    if (!exito) {
      this.logTerminal('attacker', cmdStr, `[-] PROBE FAILED: La sonda/exploit sobre ${n!.nombre} fue bloqueada o no respondió (p=${(pExito * 100).toFixed(0)}%).`, 'error', n!.id);
      this.logTerminal('defender', `ebpf_trace -e net_drop`, `[eBPF ALERT] Intento de conexión sospechosa mitigado en ${n!.nombre} [ruido: ${ruido}]`, 'alerta', n!.id);
      return;
    }

    // Ataque exitoso
    let salidaDetalle = `[+] SUCCESS: Técnica ${t.nombre} exitosa sobre ${n!.nombre}.`;

    if (t.id === 'scan_docs') {
      n!.fase = n!.fase ?? 'recon';
      const sensibles = n!.archivosSensibles ?? [];
      let extraidos = 0;
      for (const archivo of sensibles) {
        if (!this.loot.some(l => l.nodoId === n!.id && l.item === archivo)) {
          let tipo: LootItem['tipo'] = 'doc';
          let sec = 'Documento clasificado interno de la organización.';
          if (archivo.includes('env')) {
            tipo = 'env';
            sec = `DB_USER=admin_${n!.id} | DB_PASS=Secret@2026! | JWT_SECRET=sk_live_948f2a1b_${n!.id}`;
          } else if (archivo.includes('sql') || archivo.includes('dump') || archivo.includes('tar.gz')) {
            tipo = 'db';
            sec = `DUMP_SQL: ${archivo} (${(n!.valor * 2.8).toFixed(1)} MB con registros confidenciales)`;
          } else if (archivo.includes('pass') || archivo.includes('rsa') || archivo.includes('vault') || archivo.includes('key')) {
            tipo = 'cred';
            sec = `CREDENTIALS: Clave privada / hash extraído de ${archivo}`;
          }
          this.loot.push({
            id: `loot-${this.tick}-${this.loot.length}`,
            tick: this.tick,
            nodoId: n!.id,
            nodoNombre: n!.nombre,
            item: archivo,
            tipo,
            secreto: sec,
          });
          extraidos++;
        }
      }
      salidaDetalle = `[+] VULN DISCOVERY: Descubiertos ${extraidos} archivos (.env, configs, documentos) en ${n!.nombre}:\n` +
        sensibles.map(s => `    * [ARCH_EXPUESTO] ${s}`).join('\n');
    } else if (t.id === 'sqli_dump') {
      n!.fase = ORDEN_FASE[Math.max(faseIndex(n!.fase), faseIndex('acceso_inicial'))];
      const itemName = `sqli_dump_${n!.id}.sql`;
      if (!this.loot.some(l => l.nodoId === n!.id && l.item === itemName)) {
        this.loot.push({
          id: `loot-${this.tick}-${this.loot.length}`,
          tick: this.tick,
          nodoId: n!.id,
          nodoNombre: n!.nombre,
          item: itemName,
          tipo: 'db',
          secreto: `SQL TABLE DUMP: Esquemas 'usuarios', 'roles', 'transacciones' extraídos (${(n!.valor * 1.8).toFixed(1)} MB con registros y hashes).`,
        });
      }
      salidaDetalle = `[+] SQLMAP 1.7.2#STABLE - INYECCIÓN SQL EXITOSA en ${n!.nombre}:\n` +
        `    [INFO] DBMS detectado: PostgreSQL/MySQL (Inyección booleana y UNION confirmada)\n` +
        `    [+] Tablas identificadas: ['usuarios_admin', 'cuentas_2026', 'sesiones_activas']\n` +
        `    [+] Registros guardados en C2: ${itemName}`;
    } else if (t.id === 'dump_lsass') {
      n!.fase = 'escalada';
      const itemName = `lsass_hashes_${n!.id}.txt`;
      if (!this.loot.some(l => l.nodoId === n!.id && l.item === itemName)) {
        this.loot.push({
          id: `loot-${this.tick}-${this.loot.length}`,
          tick: this.tick,
          nodoId: n!.id,
          nodoNombre: n!.nombre,
          item: itemName,
          tipo: 'cred',
          secreto: `NTLM_HASHES: Administrator:500:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::`,
        });
      }
      salidaDetalle = `[+] MIMIKATZ 2.2.0 - SEKURLSA::LOGONPASSWORDS en ${n!.nombre}:\n` +
        `    * SeDebugPrivilege: Activado (Handle de proceso LSASS obtenido)\n` +
        `    * Dominio: CORP | Usuario: Administrator (RID 500)\n` +
        `    * Hash NTLM: 31d6cfe0d16ae931b73c59d7e0c089c0\n` +
        `    * Kerberos TGT: Ticket de dominio capturado y guardado en C2.`;
    } else if (t.id === 'persist_backdoor') {
      n!.fase = ORDEN_FASE[Math.max(faseIndex(n!.fase), faseIndex('escalada'))];
      salidaDetalle = `[+] PERSISTENCIA INSTALADA en ${n!.nombre}:\n` +
        `    * Cronjob implantado: /etc/cron.d/sys-telemetry (Ejecuta beacon C2 cada 3 min)\n` +
        `    * WebShell camuflada: /var/www/html/.cache_api.php (SHA-256 verificado)\n` +
        `    * Rootkit eBPF activo: Control persistente que resiste SIGKILL estándar.`;
    } else if (t.id === 'phishing_spray') {
      n!.fase = ORDEN_FASE[Math.max(faseIndex(n!.fase), faseIndex('acceso_inicial'))];
      salidaDetalle = `[*] CRACKMAPEXEC v5.2.2 - PASS-THE-HASH & CREDENTIAL SPRAY sobre ${n!.nombre}:\n` +
        `    [+] SMB 445 / WinRM: Autenticación exitosa con credenciales de dominio.\n` +
        `    [+] CORP\\admin_ws : Secret@2026! (Pwn3d!) -> Shell interactiva establecida.\n` +
        `    [+] Foothold y credenciales activas en ${n!.nombre}.`;
    } else if (t.id === 'exfil') {
      this.exfiltrados.add(n!.id);
      n!.fase = 'exfiltracion';
      this.datosExfiltrados += n!.valor;
      this.loot.push({
        id: `loot-${this.tick}-${this.loot.length}`,
        tick: this.tick,
        nodoId: n!.id,
        nodoNombre: n!.nombre,
        item: `dump_exfiltrado_${n!.id}.db`,
        tipo: 'db',
        secreto: `EXFILTRACIÓN COMPLETADA: Base de datos completa sustraída (${n!.valor} MB). Total robado: ${this.datosExfiltrados}/${this.metaExfiltracion} MB.`,
      });
      salidaDetalle = `[+] EXFILTRATION HARVEST: Extraídos ${n!.valor} MB de ${n!.nombre} hacia C2 (Total: ${this.datosExfiltrados}/${this.metaExfiltracion} MB).`;
      this.log({
        tipo: 'ataque', lado: 'attacker', nodoId: n!.id, malicioso: true, exito: true,
        texto: `Datos exfiltrados de ${n!.nombre} (+${n!.valor}). Total: ${this.datosExfiltrados}/${this.metaExfiltracion}`,
      });
    } else {
      // recon/acceso/escalada/pivot
      n!.fase = ORDEN_FASE[Math.max(faseIndex(n!.fase), faseIndex(t.faseProduce))];
      if (t.id === 'privesc') salidaDetalle = `[+] ROOT ACCESS GRANTED: Elevación de privilegios conseguida en ${n!.nombre}. Control total del nodo.`;
      else if (t.id === 'pivot') salidaDetalle = `[+] PIVOT ESTABLISHED: Túnel lateral abierto hacia ${n!.nombre}. Nuevo salto de red disponible.`;
      else if (t.id === 'exploit') salidaDetalle = `[+] RCE SHELL OPEN: Explotación exitosa. Shell remota establecida en ${n!.nombre}.`;
    }

    if (faseIndex(n!.fase) >= faseIndex('acceso_inicial')) { n!.compromisoReal = true; }
    this.sincEstadoVisual(n!);
    this.aristas.push({ from: 'atacante', to: n!.id, tipo: 'actividad', edad: 0 });

    this.logTerminal('attacker', cmdStr, salidaDetalle, 'exito', n!.id);
    this.logTerminal('defender', `ebpf_probe --event sys_enter_connect --host ${n!.nombre}`, `[eBPF TELEMETRÍA] Tráfico hostil detectado en ${n!.nombre} [técnica: ${t.nombre}, ruido: ${ruido}]`, ruido === 'alto' ? 'alerta' : 'output', n!.id);
  }

  // El host aislado vuelve online ya remediado (se limpió mientras estaba offline).
  private expirarAislamientos(): void {
    for (const n of this.nodos) {
      if (n.estado === 'aislado' && n.aisladoHasta !== undefined && this.tick >= n.aisladoHasta) {
        n.estado = 'limpio'; n.fase = null; n.compromisoReal = false;
        n.posturaDefensiva *= 0.5; n.senales = {}; n.score = 0; n.aisladoHasta = undefined;
        this.log({ tipo: 'sistema', nodoId: n.id, texto: `${n.nombre} vuelve online (remediado)` });
        this.logTerminal('defender', `xdp_filter --restore --host ${n.nombre}`, `[SOC] Aislamiento concluido. Host ${n.nombre} restaurado a la red corporativa tras desinfección.`, 'output', n.id);
      }
    }
  }

  private resistencia(n: SimNode): number {
    if (n.vulnerabilidades.length === 0) return 0.6;
    const avg = n.vulnerabilidades.reduce((s, v) => s + v.dificultad, 0) / n.vulnerabilidades.length;
    return clamp(avg, 0.2, 0.9);
  }

  // Probabilidad de éxito de una técnica sobre un nodo (usada por el agente y por la UI).
  probExito(tecnicaId: string, n: SimNode): number {
    const t = TECNICA_POR_ID.get(tecnicaId);
    if (!t) return 0;
    return clamp(t.facilidadBase * (1 - this.resistencia(n)) * (1 - n.posturaDefensiva), 0.02, 0.98);
  }

  private sincEstadoVisual(n: SimNode): void {
    if (n.estado === 'aislado' || n.estado === 'honeypot') return;
    const fx = faseIndex(n.fase);
    n.estado = fx < 0 ? 'limpio' : fx === 0 ? 'sondeado' : 'comprometido';
  }

  private resolverRespuesta(i: RespondIntent): void {
    const n = this.nodo(i.nodoId);
    const r = aplicarRespuesta(this.nodos, i.respuesta, i.nodoId, this.tick);
    this.eventos.push(r.evento);
    this.penalDisponibilidad += r.penalizaDisponibilidad;

    const rMeta = RESPUESTAS.find(x => x.id === i.respuesta);
    const cmdDef = (rMeta?.comandoEjemplo ?? `${i.respuesta} ${i.nodoId}`).replace('{target}', n?.nombre ?? i.nodoId).replace('{attacker_ip}', '192.168.1.188');
    this.logTerminal('defender', cmdDef, `[+] DEFENSE APPLIED: ${r.evento.texto}`, 'exito', i.nodoId);
    if (i.respuesta === 'aislar') {
      this.logTerminal('attacker', `ping -c 1 ${n?.nombre ?? i.nodoId}`, `[-] CONNECTION DROPPED: Destino inalcanzable. El host ${n?.nombre} ha sido aislado por el defensor.`, 'error', i.nodoId);
    } else if (i.respuesta === 'terminar_proceso') {
      this.logTerminal('attacker', `session_check --host ${n?.nombre ?? i.nodoId}`, `[-] SIGNAL KILLED: Conexión o shell interrumpida por el SOC defensor.`, 'error', i.nodoId);
    } else if (i.respuesta === 'parchear_env') {
      this.logTerminal('attacker', `curl -s http://${n?.nombre}/.env`, `[-] ACCESS DENIED (403): Variables y credenciales rotadas/parcheadas.`, 'error', i.nodoId);
    } else if (i.respuesta === 'parchear_vuln') {
      this.logTerminal('attacker', `check_exploit --target ${n?.nombre ?? i.nodoId}`, `[-] EXPLOIT MITIGATED: El servicio fue parchado por el SOC. CVE no explotable (Hotfix).`, 'error', i.nodoId);
    } else if (i.respuesta === 'yara_memory_scan') {
      this.logTerminal('attacker', `beacon_ping --node ${n?.nombre ?? i.nodoId}`, `[-] BEACON DESTROYED: Proceso hostil en memoria purgado mediante firma YARA.`, 'error', i.nodoId);
    } else if (i.respuesta === 'canary_token') {
      this.logTerminal('defender', `canary_monitor --token-status --node ${n?.nombre ?? i.nodoId}`, `[CANARY ARM] Trampa HoneyToken sembrada en ${n?.nombre}. Telemetría lista.`, 'output', i.nodoId);
      this.logTerminal('attacker', `probe_env --node ${n?.nombre ?? i.nodoId}`, `[!] DECOY SUSPECTED: Detectadas credenciales señuelo en ${n?.nombre}.`, 'alerta', i.nodoId);
    } else if (i.respuesta === 'rotate_keys') {
      this.logTerminal('attacker', `ssh -i id_rsa ${n?.nombre ?? i.nodoId}`, `[-] AUTH REJECTED: Llaves SSH / Kerberos revocadas por el SOC.`, 'error', i.nodoId);
    }
  }

  // --------- generación de ruido benigno ----------
  private ruidoBenigno(): void {
    const n = this.rng.pick(this.nodos.filter(x => x.estado !== 'aislado'));
    if (!n) return;
    if (this.rng.chance(0.5)) {
      const acciones = ['navegación web', 'tarea cron', 'actualización', 'sincronización de archivos', 'consulta DNS'];
      this.log({ tipo: 'benigno', nodoId: n.id, malicioso: false, texto: `${n.nombre}: ${this.rng.pick(acciones)}` });
      if (this.rng.chance(0.18)) {
        this.logTerminal('defender', `auditd -k benign_telemetry`, `[AUDIT INFO] Actividad normal en ${n.nombre}: sincronización de rutina verificada.`, 'output', n.id);
      }
    }
  }

  // --------- un tick completo (doc 05 §2) ----------
  avanzar(intents: {
    ataque?: AttackIntent | null; respuesta?: RespondIntent | null;
  }): void {
    this.tick++;
    this.expirarAislamientos();
    this.detector.decae(this.nodos);
    this.ruidoBenigno();
    // alimentar detector con eventos benignos de este tick
    for (const ev of this.eventos.filter(e => e.tick === this.tick && e.tipo === 'benigno')) this.detector.observa(this.nodos, ev);
    // atacante
    if (intents.ataque) {
      this.resolverAtaque(intents.ataque);
      for (const ev of this.eventos.filter(e => e.tick === this.tick && e.tipo === 'ataque')) this.detector.observa(this.nodos, ev);
    }
    // defensor
    if (intents.respuesta) this.resolverRespuesta(intents.respuesta);
    // envejecer aristas de actividad
    this.aristas = this.aristas.filter(a => a.tipo === 'red' || (a.edad = (a.edad ?? 0) + 1) < 12);
    // detección
    const nuevas = this.detector.califica(this.nodos, this.tick);
    for (const al of nuevas) {
      this.alertas.push(al);
      this.log({ tipo: 'deteccion', lado: 'defender', nodoId: al.nodoId, texto: `ALERTA en ${this.nodoNombre(al.nodoId)} score=${al.score} ${al.verdadera ? '' : '(posible falso positivo)'}` });
      this.logTerminal('defender', `tgnn_anomaly_eval --node ${al.nodoId}`, `🚨 ALERTA TGNN: Anomalía ${(al.score * 100).toFixed(1)}% en ${this.nodoNombre(al.nodoId)} | Vectores: ${JSON.stringify(al.senales)}`, 'alerta', al.nodoId);
      if (al.verdadera && this.firstTrueAlertTick === null) this.firstTrueAlertTick = this.tick;
    }
    // contención: ¿ya no hay nodos comprometidos activos?
    if (this.firstTrueAlertTick !== null && this.containmentTick === null) {
      const quedaCompromiso = this.nodos.some(n => n.compromisoReal && n.estado !== 'aislado');
      if (!quedaCompromiso) this.containmentTick = this.tick;
    }
    this.recortar();
  }

  // --------- fin de partida ----------
  terminada(): boolean {
    return this.datosExfiltrados >= this.metaExfiltracion || this.tick >= this.tickMax;
  }
  ganador(): 'attacker' | 'defender' | 'empate' {
    if (this.datosExfiltrados >= this.metaExfiltracion) return 'attacker';
    const disp = this.disponibilidad();
    return disp >= 0.5 ? 'defender' : 'empate';
  }

  private disponibilidad(): number { return clamp(1 - this.penalDisponibilidad / this.sumValor, 0, 1); }

  metricas(): Metrics {
    return {
      mttd: this.firstMaliciousTick !== null && this.firstTrueAlertTick !== null ? this.firstTrueAlertTick - this.firstMaliciousTick : null,
      mttr: this.firstTrueAlertTick !== null && this.containmentTick !== null ? this.containmentTick - this.firstTrueAlertTick : null,
      disponibilidad: Number(this.disponibilidad().toFixed(3)),
      datosExfiltrados: this.datosExfiltrados,
      metaExfiltracion: this.metaExfiltracion,
      alertasTotales: this.alertas.length,
      alertasFalsas: this.alertas.filter(a => !a.verdadera).length,
    };
  }

  // --------- utilidades ----------
  private log(e: Omit<GameEvent, 'tick' | 'id'>): void {
    this.eventos.push({ tick: this.tick, id: `e${this.tick}-${this.eventos.length}`, ...e });
  }
  logTerminal(lado: Role, cmd: string, salida: string, tipo: TerminalEntry['tipo'] = 'output', nodoId?: string): void {
    this.terminalLogs.push({
      id: `tlog-${this.tick}-${this.terminalLogs.length}`,
      tick: this.tick,
      lado,
      cmd,
      salida,
      tipo,
      nodoId,
    });
    if (this.terminalLogs.length > 90) this.terminalLogs = this.terminalLogs.slice(-90);
  }
  pensar(p: AgentThought): void { this.pensamientos.push(p); this.recortar(); }
  private recortar(): void {
    if (this.eventos.length > VENTANA) this.eventos = this.eventos.slice(-VENTANA);
    if (this.pensamientos.length > 24) this.pensamientos = this.pensamientos.slice(-24);
    if (this.alertas.length > VENTANA) this.alertas = this.alertas.slice(-VENTANA);
    if (this.loot.length > 50) this.loot = this.loot.slice(-50);
  }
}

export function clamp(x: number, lo: number, hi: number): number { return Math.max(lo, Math.min(hi, x)); }
