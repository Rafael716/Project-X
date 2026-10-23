import { useState } from 'react';
import type { Game } from './ws';
import type { SimNode, GameState } from '../../shared/protocol';
import { AttackPanel, DefensePanel, Reasoning } from './Panels';
import { TerminalView } from './Terminal';

const COLOR: Record<string, string> = {
  limpio: '#10b981',
  sondeado: '#f59e0b',
  comprometido: '#ef4444',
  aislado: '#64748b',
  honeypot: '#8b5cf6',
};

export function Battle({ g }: { g: Game }) {
  const st = g.estado!;
  const [sel, setSel] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<'split' | 'terminal_only' | 'graph_only'>('split');
  const selNode = st.nodos.find(n => n.id === sel) ?? null;

  return (
    <div className="battle">
      {/* Marcador tipo videojuego: puntos, energía y combos de cada lado */}
      <ScoreHUD st={st} />

      {/* Barra de Métricas y Control Superior */}
      <MetricsBar g={g} st={st} />

      {/* Selector de Modo de Visualización */}
      <div className="view-mode-bar">
        <div className="vmb-left">
          <span className="vmb-title">Modo de Pantalla:</span>
          <button
            type="button"
            className={`vmb-btn ${activeView === 'split' ? 'active' : ''}`}
            onClick={() => setActiveView('split')}
          >
            🖥️ Vista Dividida (Red + Terminal)
          </button>
          <button
            type="button"
            className={`vmb-btn ${activeView === 'terminal_only' ? 'active' : ''}`}
            onClick={() => setActiveView('terminal_only')}
          >
            💻 Terminal en Vivo Maximizado
          </button>
          <button
            type="button"
            className={`vmb-btn ${activeView === 'graph_only' ? 'active' : ''}`}
            onClick={() => setActiveView('graph_only')}
          >
            🌐 Topología & Paneles
          </button>
        </div>

        <div className="vmb-right">
          <span className="live-indicator">
            <span className="live-dot" /> EN VIVO (250ms tick)
          </span>
        </div>
      </div>

      {/* Grid Principal de Simulación */}
      {activeView !== 'terminal_only' && (
        <div className="battle-grid">
          {/* Topología de Red SVG Interactiva */}
          <section className="panel grafo-wrap">
            <div className="panel-header-row">
              <h3>🌐 Topología de Red Simulada</h3>
              <span className="hint-text">Haz clic en un host para investigarlo o atacarlo</span>
            </div>
            <Graph st={st} sel={sel} onSel={setSel} />
            <Leyenda />
          </section>

          {/* Panel Lateral de Rol (Atacante o Defensor) */}
          <aside className="col-lado">
            {g.role === 'attacker' && <AttackPanel g={g} sel={selNode} />}
            {g.role === 'defender' && <DefensePanel g={g} sel={selNode} />}
            {g.role === 'spectator' && (
              <div className="panel spectator-panel">
                <div className="panel-title-wrap">
                  <span className="panel-badge-purple">ESPECTADOR</span>
                  <h3>Observatorio Global</h3>
                </div>
                <p className="muted">Monitoreando el enfrentamiento en tiempo real entre Red Team y Blue Team.</p>
                <div className="spec-role-preview">
                  <AttackPanel g={g} sel={selNode} />
                  <DefensePanel g={g} sel={selNode} />
                </div>
              </div>
            )}
            <Reasoning st={st} lado={g.role === 'defender' ? 'defender' : 'attacker'} />
          </aside>
        </div>
      )}

      {/* Terminal en Vivo Streaming Integrada */}
      {activeView !== 'graph_only' && (
        <section className="live-terminal-section">
          <TerminalView g={g} height={activeView === 'terminal_only' ? 560 : 360} />
        </section>
      )}

      {/* Línea de Eventos Recientes */}
      <Feed st={st} />
    </div>
  );
}

function ScoreHUD({ st }: { st: GameState }) {
  const m = st.metricas;
  const total = Math.max(1, m.puntosAtacante + m.puntosDefensor);
  const atkPct = (m.puntosAtacante / total) * 100;

  return (
    <div className="score-hud">
      <SideScore
        side="atk"
        titulo="🔴 Red Team"
        puntos={m.puntosAtacante}
        meta={m.puntosMeta}
        energia={m.energiaAtacante}
        energiaMax={m.energiaMax}
        combo={m.comboAtacante}
      />
      <div className="score-tug">
        <div className="tug-bar">
          <div className="tug-atk" style={{ width: `${atkPct}%` }} />
          <div className="tug-def" style={{ width: `${100 - atkPct}%` }} />
        </div>
        <span className="tug-label">Dominio de la partida</span>
      </div>
      <SideScore
        side="def"
        titulo="🔵 Blue Team"
        puntos={m.puntosDefensor}
        meta={m.puntosMeta}
        energia={m.energiaDefensor}
        energiaMax={m.energiaMax}
        combo={m.comboDefensor}
      />
    </div>
  );
}

function SideScore({ side, titulo, puntos, meta, energia, energiaMax, combo }:
  { side: 'atk' | 'def'; titulo: string; puntos: number; meta: number; energia: number; energiaMax: number; combo: number }) {
  return (
    <div className={`side-score side-${side}`}>
      <div className="ss-top">
        <span className="ss-title">{titulo}</span>
        {combo >= 2 && <span className="ss-combo">🔥 x{combo} combo</span>}
      </div>
      <div className="ss-points">{puntos}<span className="ss-meta"> / {meta}</span></div>
      <div className="ss-energy" title={`Energía ${energia}/${energiaMax}`}>
        {Array.from({ length: energiaMax }).map((_, i) => (
          <span key={i} className={`epip ${i < energia ? 'on' : ''}`} />
        ))}
      </div>
    </div>
  );
}

function MetricsBar({ g, st }: { g: Game; st: GameState }) {
  const m = st.metricas;
  const pct = Math.round((st.tick / st.tickMax) * 100);

  return (
    <div className="metrics">
      <div className="mprog">
        <div className="bar-labels">
          <span className="ml">Progreso de la partida</span>
          <span className="mv">Tick {st.tick} / {st.tickMax}</span>
        </div>
        <div className="bar">
          <div style={{ width: `${pct}%` }} />
        </div>
      </div>

      <Metric
        label="Máquinas tomadas"
        val={`${m.maquinasTomadas} / ${m.maquinasTotales}`}
        tone={m.maquinasTomadas >= m.maquinasTotales ? 'rojo' : m.maquinasTomadas > 0 ? 'alerta' : 'normal'}
        icon="🖥️"
      />
      <Metric
        label="Datos robados"
        val={`${m.datosExfiltrados} / ${m.metaExfiltracion} MB`}
        tone={m.datosExfiltrados > 0 ? 'rojo' : 'normal'}
        icon="💎"
      />
      <Metric
        label="Red funcionando"
        val={`${Math.round(m.disponibilidad * 100)}%`}
        tone={m.disponibilidad < 0.6 ? 'alerta' : 'azul'}
        icon="🛡️"
      />
      <Metric
        label="Tardó en detectar"
        val={m.mttd === null ? '—' : `${m.mttd} turnos`}
        icon="⏱️"
      />
      <Metric
        label="Tardó en frenar"
        val={m.mttr === null ? '—' : `${m.mttr} turnos`}
        icon="⏳"
      />
      <Metric
        label="Alarmas"
        val={`${m.alertasTotales} (${m.alertasFalsas} falsas)`}
        icon="🚨"
      />

      <div className="controls-group">
        <button
          type="button"
          className="pause-btn"
          onClick={() => g.send({ t: 'pausar', valor: st.estado === 'en_curso' })}
        >
          {st.estado === 'pausada' ? '▶ Reanudar' : '⏸ Pausa'}
        </button>
      </div>
    </div>
  );
}

function Metric({ label, val, tone, icon }: { label: string; val: string; tone?: string; icon?: string }) {
  return (
    <div className={`metric ${tone ?? ''}`}>
      <span className="ml">
        {icon && <span className="mi">{icon} </span>}
        {label}
      </span>
      <span className="mv">{val}</span>
    </div>
  );
}

function Graph({ st, sel, onSel }: { st: GameState; sel: string | null; onSel: (id: string) => void }) {
  const W = 580, H = 420, cx = W / 2, cy = H / 2, R = 150;
  const vis = st.nodos;
  const pos = new Map<string, { x: number; y: number }>();

  // Si el escenario trae posiciones (pos en 0..1), se respeta el mapa diseñado;
  // si no, se cae a un layout en círculo.
  const M = 56;
  vis.forEach((n, i) => {
    if (n.pos) {
      pos.set(n.id, { x: M + n.pos[0] * (W - 2 * M), y: M + n.pos[1] * (H - 2 * M) });
    } else {
      const a = (i / vis.length) * Math.PI * 2 - Math.PI / 2;
      pos.set(n.id, { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) });
    }
  });

  return (
    <svg className="grafo" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Topología de la red simulada">
      <defs>
        <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ef4444" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Aristas de Red Fijas */}
      {st.aristas.filter(a => a.tipo === 'red').map((a, i) => {
        const p = pos.get(a.from), q = pos.get(a.to);
        if (!p || !q) return null;
        return <line key={`net-${i}`} x1={p.x} y1={p.y} x2={q.x} y2={q.y} className="arista-red" />;
      })}

      {/* Aristas de Actividad Dinámica */}
      {st.aristas.filter(a => a.tipo === 'actividad').map((a, i) => {
        const q = pos.get(a.to);
        if (!q) return null;
        return (
          <circle
            key={`act-${i}`}
            cx={q.x}
            cy={q.y}
            r={32}
            fill="none"
            stroke="#ef4444"
            strokeWidth={2}
            strokeDasharray="3 3"
            className="actividad-pulse"
          />
        );
      })}

      {/* Nodos */}
      {vis.map(n => {
        const p = pos.get(n.id)!;
        const r = 22 + n.valor * 2.5;
        const isSelected = sel === n.id;
        const hasAnomaly = n.score > 0.4;

        return (
          <g
            key={n.id}
            transform={`translate(${p.x},${p.y})`}
            className={`nodo ${isSelected ? 'sel' : ''}`}
            onClick={() => onSel(n.id)}
            tabIndex={0}
            role="button"
            aria-label={`${n.nombre}, estado: ${n.estado}`}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') onSel(n.id);
            }}
          >
            {hasAnomaly && (
              <circle r={r + 14} fill="url(#nodeGlow)" className="anomaly-pulse" />
            )}

            <circle
              r={r}
              fill={COLOR[n.estado] ?? '#10b981'}
              stroke={isSelected ? '#38bdf8' : '#1e293b'}
              strokeWidth={isSelected ? 4 : 2}
            />

            {n.score > 0.3 && (
              <circle
                r={r + 6}
                fill="none"
                stroke="#ef4444"
                strokeOpacity={n.score}
                strokeWidth={3}
                strokeDasharray="4 3"
              />
            )}

            <text className="nicon" y={6}>{icono(n)}</text>
            {n.persistente && <text className="npersist" x={r - 4} y={-r + 10}>🚪</text>}
            <text className="nlabel" y={r + 16}>{n.nombre}</text>
            <text className="nsub" y={r + 28}>{n.servicios.slice(0, 2).join(',')}</text>
          </g>
        );
      })}
    </svg>
  );
}

function icono(n: SimNode) {
  return (
    {
      router: '🌐',
      workstation: '💻',
      server: '🖥️',
      database: '🗄️',
      honeypot: '🍯',
    } as const
  )[n.tipo] ?? '💻';
}

function Leyenda() {
  const items: [string, string][] = [
    ['limpio', 'Limpio / Sano'],
    ['sondeado', 'Sondeado / Recon'],
    ['comprometido', 'Comprometido (RCE/Foothold)'],
    ['aislado', 'Aislado (Cuarentena)'],
    ['honeypot', 'Honeypot / Señuelo'],
  ];

  return (
    <div className="leyenda">
      {items.map(([k, l]) => (
        <span key={k}>
          <i style={{ background: COLOR[k] }} />
          {l}
        </span>
      ))}
    </div>
  );
}

function Feed({ st }: { st: GameState }) {
  const evs = [...st.eventos].reverse().slice(0, 16);

  return (
    <section className="panel feed">
      <div className="feed-header">
        <h3>📋 Registro Auditor de Eventos en Kernel/Red</h3>
        <span className="badge-count">{st.eventos.length} eventos</span>
      </div>
      <ul className="feed-list">
        {evs.map(e => (
          <li key={e.id} className={`ev ev-${e.tipo}`}>
            <span className="et">t{e.tick}</span>
            <span className="eb">{badge(e.tipo)}</span>
            <span className="ex">{e.texto}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function badge(t: string) {
  return (
    {
      benigno: '🟢 benigno',
      ataque: '🔴 ataque',
      deteccion: '🚨 detección',
      respuesta: '🔵 respuesta',
      sistema: 'ℹ️ sistema',
    } as Record<string, string>
  )[t] ?? '·';
}
