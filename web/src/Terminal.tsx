import { useState, useEffect, useRef } from 'react';
import type { Game } from './ws';
import type { TerminalEntry, Role } from '../../shared/protocol';

interface TerminalProps {
  g: Game;
  ladoForzado?: Role;
  height?: number | string;
}

export function TerminalView({ g, ladoForzado, height = 340 }: TerminalProps) {
  const st = g.estado;
  const role = ladoForzado ?? g.role ?? 'attacker';
  const effectiveRole: Role = role === 'spectator' ? 'attacker' : role;

  const [activeTab, setActiveTab] = useState<Role>(effectiveRole);
  const [filter, setFilter] = useState<'all' | 'cmd' | 'alerta' | 'exito'>('all');
  const [autoScroll, setAutoScroll] = useState(true);
  const [cliInput, setCliInput] = useState('');
  const [customHistory, setCustomHistory] = useState<Array<{ cmd: string; out: string; tipo: TerminalEntry['tipo'] }>>([]);

  const bodyRef = useRef<HTMLDivElement>(null);
  const terminalLogs = st?.terminalLogs ?? [];

  // Filtrar logs del lado activo
  const displayedLogs = terminalLogs.filter(l => l.lado === activeTab || l.lado === 'spectator');
  const filtered = filter === 'all' ? displayedLogs : displayedLogs.filter(l => {
    if (filter === 'cmd') return l.tipo === 'cmd';
    if (filter === 'alerta') return l.tipo === 'alerta' || l.tipo === 'error';
    if (filter === 'exito') return l.tipo === 'exito';
    return true;
  });

  useEffect(() => {
    // Scroll SOLO del contenedor del terminal (nunca scrollIntoView: arrastra
    // toda la página cada tick). Y solo si el usuario ya está cerca del fondo,
    // para no pelear con quien subió a leer el historial.
    const el = bodyRef.current;
    if (!autoScroll || !el) return;
    const cercaDelFondo = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (cercaDelFondo) el.scrollTop = el.scrollHeight;
  }, [filtered.length, customHistory.length, autoScroll]);

  // Si cambia el rol de jugador, sincronizar tab inicial
  useEffect(() => {
    if (g.role && g.role !== 'spectator') {
      setActiveTab(g.role);
    }
  }, [g.role]);

  const handleCliSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cmd = cliInput.trim();
    if (!cmd) return;
    setCliInput('');

    if (cmd.toLowerCase() === 'clear' || cmd.toLowerCase() === 'cls') {
      setCustomHistory([]);
      return;
    }

    if (cmd.toLowerCase() === 'help') {
      const isRed = activeTab === 'attacker';
      const helpText = isRed
        ? `[AYUDA C2 OFFENSIVE CLI - MITRE ATT&CK]
  - scan <nodo>        : Escaneo y descubrimiento de puertos
  - env / docs <nodo>  : Búsqueda profunda de .env y documentos confidenciales
  - sqli / sql <nodo>  : Inyección SQL y volcado de tablas / esquemas
  - exploit <nodo>     : Explotación RCE / Initial Access
  - lsass / mimi <nodo>: Volcado de memoria LSASS (Mimikatz hashes)
  - privesc <nodo>     : Elevación de privilegios a ROOT / SYSTEM
  - backdoor <nodo>    : Instalar persistencia (WebShell + Cron)
  - spray <nodo>       : Credential Spraying & Pass-the-Hash
  - pivot <nodo>       : Salto lateral a nodo adyacente
  - exfil <nodo>       : Exfiltrar base de datos hacia servidor C2
  - status             : Telemetría de partida y botín
  - clear              : Limpiar pantalla local`
        : `[AYUDA SOC DEFENDER CLI - eBPF SECOPS]
  - isolate <nodo>     : Aislar nodo en cuarentena eBPF (drop de tráfico)
  - kill <nodo>        : Terminar proceso malicioso / SIGKILL
  - patch_cve <nodo>   : Parchear CVEs y vulnerabilidades (Hotfix preventivo)
  - yara <nodo>        : Escaneo YARA en memoria (Threat Hunting sin downtime)
  - patch / env <nodo> : Parchear variables .env y rotar secretos expuestos
  - canary <nodo>      : Sembrar HoneyToken / trampa canaria
  - keys <nodo>        : Rotar llaves SSH y tickets Kerberos
  - honeypot <nodo>    : Desplegar contenedor señuelo
  - block <nodo>       : Bloquear origen hostil en firewall XDP
  - status             : Telemetría de red, métricas MTTD/MTTR y disponibilidad
  - clear              : Limpiar pantalla local`;

      setCustomHistory(prev => [...prev, { cmd, out: helpText, tipo: 'cmd' }]);
      return;
    }

    if (cmd.toLowerCase() === 'status') {
      const m = st?.metricas;
      const statusText = `[ESTADO DEL SISTEMA]
  Tick: ${st?.tick}/${st?.tickMax} | Disponibilidad: ${Math.round((m?.disponibilidad ?? 1) * 100)}%
  Datos Exfiltrados: ${m?.datosExfiltrados}/${m?.metaExfiltracion} MB | Alertas: ${m?.alertasTotales} (${m?.alertasFalsas} FP)
  Archivos Comprometidos (.env/docs): ${st?.loot?.length ?? 0}`;
      setCustomHistory(prev => [...prev, { cmd, out: statusText, tipo: 'cmd' }]);
      return;
    }

    // Interpretar comando rápido hacia el servidor
    const parts = cmd.split(' ');
    const action = parts[0].toLowerCase();
    const target = parts[1]?.toLowerCase() ?? 'ws1';

    const nodoObj = st?.nodos.find(n => n.id.toLowerCase() === target || n.nombre.toLowerCase().includes(target));
    const nodoId = nodoObj ? nodoObj.id : target;

    if (activeTab === 'attacker') {
      if (['scan', 'portscan'].includes(action)) {
        g.send({ t: 'atacar', tecnicaId: 'portscan', nodoId });
      } else if (['env', 'docs', 'scan_docs', 'cat'].includes(action)) {
        g.send({ t: 'atacar', tecnicaId: 'scan_docs', nodoId });
      } else if (['sqli', 'sql', 'sqlmap', 'sqli_dump'].includes(action)) {
        g.send({ t: 'atacar', tecnicaId: 'sqli_dump', nodoId });
      } else if (['lsass', 'mimi', 'mimikatz', 'dump_lsass', 'hashes'].includes(action)) {
        g.send({ t: 'atacar', tecnicaId: 'dump_lsass', nodoId });
      } else if (['backdoor', 'persist', 'cron', 'webshell', 'persist_backdoor'].includes(action)) {
        g.send({ t: 'atacar', tecnicaId: 'persist_backdoor', nodoId });
      } else if (['spray', 'spray_creds', 'phishing', 'phishing_spray', 'cme'].includes(action)) {
        g.send({ t: 'atacar', tecnicaId: 'phishing_spray', nodoId });
      } else if (['exploit', 'rce'].includes(action)) {
        g.send({ t: 'atacar', tecnicaId: 'exploit', nodoId });
      } else if (['privesc', 'root', 'sudo'].includes(action)) {
        g.send({ t: 'atacar', tecnicaId: 'privesc', nodoId });
      } else if (['pivot', 'lateral'].includes(action)) {
        g.send({ t: 'atacar', tecnicaId: 'pivot', nodoId });
      } else if (['exfil', 'dump'].includes(action)) {
        g.send({ t: 'atacar', tecnicaId: 'exfil', nodoId });
      } else {
        setCustomHistory(prev => [...prev, { cmd, out: `Comando '${action}' no reconocido. Escribe 'help' para comandos disponibles.`, tipo: 'error' }]);
        return;
      }
    } else {
      if (['isolate', 'aislar'].includes(action)) {
        g.send({ t: 'responder', respuesta: 'aislar', nodoId });
      } else if (['kill', 'terminar'].includes(action)) {
        g.send({ t: 'responder', respuesta: 'terminar_proceso', nodoId });
      } else if (['patch_cve', 'hotfix', 'cve', 'parchear_vuln'].includes(action)) {
        g.send({ t: 'responder', respuesta: 'parchear_vuln', nodoId });
      } else if (['yara', 'hunt', 'memory', 'yara_memory_scan'].includes(action)) {
        g.send({ t: 'responder', respuesta: 'yara_memory_scan', nodoId });
      } else if (['canary', 'token', 'honeytoken', 'canary_token'].includes(action)) {
        g.send({ t: 'responder', respuesta: 'canary_token', nodoId });
      } else if (['keys', 'rotate', 'rotate_keys', 'kerberos'].includes(action)) {
        g.send({ t: 'responder', respuesta: 'rotate_keys', nodoId });
      } else if (['patch', 'parchear', 'vault', 'parchear_env'].includes(action)) {
        g.send({ t: 'responder', respuesta: 'parchear_env', nodoId });
      } else if (['honeypot', 'decoy'].includes(action)) {
        g.send({ t: 'responder', respuesta: 'honeypot', nodoId });
      } else if (['block', 'bloquear', 'iptables'].includes(action)) {
        g.send({ t: 'responder', respuesta: 'bloquear_ip', nodoId });
      } else {
        setCustomHistory(prev => [...prev, { cmd, out: `Comando '${action}' no reconocido. Escribe 'help' para comandos disponibles.`, tipo: 'error' }]);
        return;
      }
    }

    setCustomHistory(prev => [...prev, { cmd, out: `[QUEUE] Enviado intent a nodo: ${nodoId}`, tipo: 'cmd' }]);
  };

  const isRed = activeTab === 'attacker';
  const promptUser = isRed ? 'c2-operator@kali-red' : 'secops-analyst@blue-soc';
  const promptSign = isRed ? '$' : '#';

  return (
    <div className={`term-container ${isRed ? 'term-theme-red' : 'term-theme-blue'}`} style={{ minHeight: height }}>
      {/* Top Terminal Bar */}
      <div className="term-header">
        <div className="term-dots">
          <span className="dot dot-close" />
          <span className="dot dot-min" />
          <span className="dot dot-max" />
        </div>

        <div className="term-tabs">
          <button
            type="button"
            className={`term-tab ${activeTab === 'attacker' ? 'active-red' : ''}`}
            onClick={() => setActiveTab('attacker')}
          >
            🔴 C2 Terminal (Atacante)
          </button>
          <button
            type="button"
            className={`term-tab ${activeTab === 'defender' ? 'active-blue' : ''}`}
            onClick={() => setActiveTab('defender')}
          >
            🔵 SOC Console (Defensor)
          </button>
        </div>

        <div className="term-actions">
          <div className="term-filters">
            <button type="button" className={`fbtn ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>Todo</button>
            <button type="button" className={`fbtn ${filter === 'cmd' ? 'active' : ''}`} onClick={() => setFilter('cmd')}>Cmds</button>
            <button type="button" className={`fbtn ${filter === 'alerta' ? 'active' : ''}`} onClick={() => setFilter('alerta')}>Alertas</button>
            <button type="button" className={`fbtn ${filter === 'exito' ? 'active' : ''}`} onClick={() => setFilter('exito')}>Loot/Éxitos</button>
          </div>

          <button
            type="button"
            className={`term-toggle-btn ${autoScroll ? 'on' : ''}`}
            title="Auto-desplazamiento con nuevos eventos"
            onClick={() => setAutoScroll(!autoScroll)}
          >
            {autoScroll ? '▼ Auto-scroll' : '⏸ Pausa scroll'}
          </button>
        </div>
      </div>

      {/* Terminal Body */}
      <div className="term-body" ref={bodyRef}>
        <div className="term-banner">
          {isRed ? (
            <pre className="banner-text red">
{`╔══════════════════════════════════════════════════════════════════════╗
║  ⚡ PROJECT-X C2 CONSOLE · RED TEAM EXPLOITATION & LOOT HARVESTER   ║
║  Objetivo: Filtración de .env, credenciales, docs y base de datos   ║
╚══════════════════════════════════════════════════════════════════════╝`}
            </pre>
          ) : (
            <pre className="banner-text blue">
{`╔══════════════════════════════════════════════════════════════════════╗
║  🛡️ PROJECT-X SOC INCIDENT RESPONSE · eBPF TELEMETRY & TGNN ENGINE  ║
║  Objetivo: Detección explicable, parcheo de .env y contención activa  ║
╚══════════════════════════════════════════════════════════════════════╝`}
            </pre>
          )}
        </div>

        {/* Server Terminal Logs */}
        {filtered.map(l => (
          <div key={l.id} className={`term-entry entry-${l.tipo}`}>
            <div className="entry-cmd-line">
              <span className="entry-prompt">{promptUser}:{promptSign}</span>
              <span className="entry-cmd">{l.cmd}</span>
              <span className="entry-tick">t{l.tick}</span>
            </div>
            {l.salida && <pre className="entry-output">{l.salida}</pre>}
          </div>
        ))}

        {/* Local user custom commands */}
        {customHistory.map((h, i) => (
          <div key={`cust-${i}`} className={`term-entry entry-${h.tipo}`}>
            <div className="entry-cmd-line">
              <span className="entry-prompt">{promptUser}:{promptSign}</span>
              <span className="entry-cmd">{h.cmd}</span>
              <span className="entry-tick">local</span>
            </div>
            <pre className="entry-output">{h.out}</pre>
          </div>
        ))}

      </div>

      {/* Terminal Input Prompt */}
      <form className="term-footer" onSubmit={handleCliSubmit}>
        <span className="term-cli-prompt">{promptUser}:{promptSign}</span>
        <input
          type="text"
          className="term-input"
          value={cliInput}
          onChange={e => setCliInput(e.target.value)}
          placeholder={isRed ? "Escribe comandos: 'scan ws1', 'env ws1', 'exploit web', 'help', 'clear'..." : "Escribe comandos: 'isolate ws1', 'patch web', 'kill ws2', 'help', 'clear'..."}
        />
        <button type="submit" className="term-send-btn">Ejecutar</button>
      </form>
    </div>
  );
}
