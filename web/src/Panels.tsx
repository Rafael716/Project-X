import { useState } from 'react';
import type { Game } from './ws';
import type { SimNode, GameState, Role, Phase, LootItem } from '../../shared/protocol';

const ORDEN: (Phase | null)[] = [null, 'recon', 'acceso_inicial', 'escalada', 'movimiento_lateral', 'exfiltracion'];
const fi = (f: Phase | null) => ORDEN.indexOf(f);

// Nombre amigable de cada fase (lo técnico queda solo en el código).
const FASE_AMIGABLE: Record<string, string> = {
  recon: 'Explorada',
  acceso_inicial: 'Dentro',
  escalada: 'Con control total',
  movimiento_lateral: 'Usada para saltar',
  exfiltracion: 'Datos robados',
};
const faseTexto = (f: Phase | null) => (f ? FASE_AMIGABLE[f] ?? f : 'Sin tocar');

function miModo(st: GameState, role: Role) {
  return st.jugadores.find(j => j.role === role)?.modo ?? 'manual';
}

function ModoSwitch({ g, role }: { g: Game; role: Role }) {
  const modo = miModo(g.estado!, role);
  return (
    <div className="modo-switch">
      <button
        type="button"
        className={`pill ${modo === 'manual' ? 'on' : ''}`}
        onClick={() => g.send({ t: 'elegir_modo', modo: 'manual' })}
      >
        🧑 Manual
      </button>
      <button
        type="button"
        className={`pill ${modo === 'autoplay' ? 'on' : ''}`}
        onClick={() => g.send({ t: 'elegir_modo', modo: 'autoplay' })}
      >
        🤖 Agente IA (ReAct)
      </button>
    </div>
  );
}

export function KillChainTracker({ faseActual }: { faseActual: Phase | null }) {
  const fases: Array<{ key: Phase; label: string; icon: string }> = [
    { key: 'recon', label: '1. Explorar', icon: '🔍' },
    { key: 'acceso_inicial', label: '2. Entrar', icon: '🚪' },
    { key: 'escalada', label: '3. Hacerse admin', icon: '⚡' },
    { key: 'movimiento_lateral', label: '4. Saltar de PC', icon: '🔀' },
    { key: 'exfiltracion', label: '5. Robar datos', icon: '💎' },
  ];

  const currentIdx = fi(faseActual);

  return (
    <div className="killchain-tracker">
      <div className="kc-title">Pasos del ataque <span style={{ opacity: 0.6, fontWeight: 400 }}>(estilo MITRE ATT&CK)</span></div>
      <div className="kc-steps">
        {fases.map((f, i) => {
          const reached = currentIdx >= i + 1;
          const isCurrent = currentIdx === i + 1;
          return (
            <div key={f.key} className={`kc-step ${reached ? 'reached' : ''} ${isCurrent ? 'current' : ''}`}>
              <span className="kc-icon">{f.icon}</span>
              <span className="kc-label">{f.label}</span>
              {i < fases.length - 1 && <span className="kc-arrow">→</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function LootViewer({ loot }: { loot: LootItem[] }) {
  const [selectedItem, setSelectedItem] = useState<LootItem | null>(null);

  if (!loot || loot.length === 0) {
    return (
      <div className="loot-empty">
        <p className="muted">🔍 Sin secretos sustraídos aún. Ejecuta <b>Búsqueda de .env y documentos</b> o compromete nodos para saquear credenciales.</p>
      </div>
    );
  }

  return (
    <div className="loot-panel">
      <div className="loot-header">
        <h4>📂 Secretos & Archivos Confidenciales ({loot.length})</h4>
        <span className="badge-count">{loot.length} archivos</span>
      </div>

      <div className="loot-list">
        {loot.map(item => (
          <div
            key={item.id}
            className={`loot-card loot-type-${item.tipo} ${selectedItem?.id === item.id ? 'selected' : ''}`}
            onClick={() => setSelectedItem(selectedItem?.id === item.id ? null : item)}
          >
            <div className="loot-card-top">
              <span className="loot-icon">
                {item.tipo === 'env' ? '⚙️' : item.tipo === 'db' ? '🗄️' : item.tipo === 'cred' ? '🔑' : '📄'}
              </span>
              <span className="loot-name">{item.item}</span>
              <span className={`loot-tag tag-${item.tipo}`}>{item.tipo.toUpperCase()}</span>
            </div>
            <div className="loot-meta">
              <small>Host: <b>{item.nodoNombre}</b> · t{item.tick}</small>
            </div>
            {selectedItem?.id === item.id && (
              <div className="loot-details">
                <pre>{item.secreto}</pre>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function AttackPanel({ g, sel }: { g: Game; sel: SimNode | null }) {
  const st = g.estado!;
  const auto = miModo(st, 'attacker') === 'autoplay';
  const loot = st.loot ?? [];
  const energia = st.metricas.energiaAtacante;

  return (
    <div className="panel lado-atacante">
      <div className="panel-head">
        <div className="panel-title-wrap">
          <span className="panel-badge-red">C2 RED TEAM</span>
          <h3>Consola Ofensiva</h3>
        </div>
        <ModoSwitch g={g} role="attacker" />
      </div>

      {auto && (
        <div className="agent-active-notice red">
          <span className="pulse-dot" />
          <span><b>Agente automático jugando:</b> está explorando, entrando y robando datos solo. Cambia a 🧑 Manual para jugar tú.</span>
        </div>
      )}

      {/* Kill Chain Global Progress */}
      <KillChainTracker faseActual={sel?.fase ?? null} />

      {!sel ? (
        <div className="select-prompt">
          <span className="prompt-icon">🎯</span>
          <p><b>¿Qué hago?</b> Haz clic en una PC del mapa y elige una acción abajo. Tu meta: <b>tomar TODAS las máquinas de la red</b> (ganas solo cuando las tienes todas). Avanza PC por PC.</p>
        </div>
      ) : (
        <div className="target-section">
          <div className="target-card">
            <div className="target-header">
              <div>
                <span className="target-type">{sel.tipo.toUpperCase()}</span>
                <h4>{sel.nombre}</h4>
              </div>
              <span className={`target-state state-${sel.estado}`}>{sel.estado.toUpperCase()}</span>
            </div>

            <div className="target-pills">
              <span><b>Estado:</b> {faseTexto(sel.fase)}</span>
              <span><b>Programas:</b> {sel.servicios.join(', ')}</span>
              <span><b>Datos que guarda:</b> {sel.valor} MB</span>
            </div>

            {/* Archivos sensibles en el nodo */}
            {sel.archivosSensibles && sel.archivosSensibles.length > 0 && (
              <div className="target-files">
                <div className="tf-label">Archivos confidenciales en este host:</div>
                <div className="tf-list">
                  {sel.archivosSensibles.map(file => {
                    const isLooted = loot.some(l => l.nodoId === sel.id && l.item === file);
                    return (
                      <span key={file} className={`file-badge ${isLooted ? 'looted' : 'pending'}`}>
                        {isLooted ? '✅ ' : '🔒 '}
                        {file}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Vulnerabilidades conocidas */}
            {sel.vulnerabilidades && sel.vulnerabilidades.length > 0 && (
              <div className="target-vulns">
                <div className="tf-label">Fallas encontradas:</div>
                {sel.vulnerabilidades.map(v => (
                  <div key={v.id} className="vuln-item">
                    <span className="vuln-cve">{v.cve ?? 'CVE-PENDIENTE'}</span>
                    <span className="vuln-name">{v.nombre ?? v.id}</span>
                    <span className="vuln-tactica">({v.tactica})</span>
                    {v.descripcion && <p className="vuln-desc">{v.descripcion}</p>}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="tecnicas-section">
            <h4>¿Qué quieres hacer? Elige una acción 👇</h4>
            <div className="tecnicas-grid">
              {g.tecnicas.map(t => {
                let aplicable = false;
                if (sel.estado !== 'aislado') {
                  if (t.id === 'scan_docs' || t.id === 'sqli_dump' || t.id === 'phishing_spray') {
                    aplicable = true;
                  } else if (t.id === 'dump_lsass') {
                    aplicable = fi(sel.fase) >= fi('escalada');
                  } else if (t.id === 'persist_backdoor') {
                    aplicable = fi(sel.fase) >= fi('acceso_inicial');
                  } else if (t.id === 'pivot') {
                    aplicable = fi(sel.fase) < fi('acceso_inicial');
                  } else if (t.id === 'exfil') {
                    aplicable = fi(sel.fase) >= fi('acceso_inicial') && sel.valor > 0;
                  } else {
                    aplicable = fi(sel.fase) >= fi(t.faseRequiere) && fi(sel.fase) < fi(t.faseProduce);
                  }
                }

                const ruidoColor = t.ruido === 'alto' ? '#f43f5e' : t.ruido === 'medio' ? '#f59e0b' : '#10b981';
                const iconMap: Record<string, string> = {
                  scan_docs: '🔍',
                  sqli_dump: '💉',
                  dump_lsass: '🧬',
                  persist_backdoor: '🚪',
                  phishing_spray: '🎯',
                  exploit: '💥',
                  privesc: '⚡',
                  pivot: '🔀',
                  exfil: '💎',
                  portscan: '📡',
                  enum: '📋',
                  bruteforce: '🔨',
                };
                const tIcon = iconMap[t.id] ?? '⚔️';
                const sinEnergia = t.costo > energia;

                return (
                  <button
                    key={t.id}
                    type="button"
                    className={`tecnica-btn ${aplicable && !sinEnergia ? 'ready' : 'locked'}`}
                    disabled={auto || !aplicable || sinEnergia}
                    title={sinEnergia ? `Necesitas ${t.costo} de energía (tienes ${energia})` : t.descripcion}
                    onClick={() => g.send({ t: 'atacar', tecnicaId: t.id, nodoId: sel.id })}
                  >
                    <div className="tb-top">
                      <span className="tb-name">{tIcon} {t.nombre}</span>
                      <span className="tb-ruido" style={{ color: ruidoColor }}>Ruido {t.ruido}</span>
                    </div>
                    <span className="tb-desc">{t.descripcion}</span>
                    <div className="tb-costs">
                      <span className={`cost-chip ${sinEnergia ? 'cant' : ''}`}>⚡ {t.costo}</span>
                      {t.puntos > 0 && <span className="cost-chip pts">★ {t.puntos}</span>}
                    </div>
                    {t.comandoEjemplo && <code className="tb-cmd">{t.comandoEjemplo.replace('{target}', sel.id)}</code>}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Botín actual */}
      <LootViewer loot={loot} />
    </div>
  );
}

export function DefensePanel({ g, sel }: { g: Game; sel: SimNode | null }) {
  const st = g.estado!;
  const auto = miModo(st, 'defender') === 'autoplay';
  const alertas = [...st.alertas].reverse().slice(0, 6);
  const loot = st.loot ?? [];
  const energia = st.metricas.energiaDefensor;

  return (
    <div className="panel lado-defensor">
      <div className="panel-head">
        <div className="panel-title-wrap">
          <span className="panel-badge-blue">BLUE TEAM SOC</span>
          <h3>Centro de Operaciones (SecOps)</h3>
        </div>
        <ModoSwitch g={g} role="defender" />
      </div>

      {auto && (
        <div className="agent-active-notice blue">
          <span className="pulse-dot blue" />
          <span><b>Agente automático jugando:</b> está vigilando la red y defendiendo solo. Cambia a 🧑 Manual para jugar tú.</span>
        </div>
      )}

      {/* Alerta de Fuga de Información */}
      {loot.length > 0 && (
        <div className="data-leak-alert">
          <span className="dla-icon">🚨</span>
          <div>
            <b>¡Cuidado, te están robando archivos!</b>
            <p>El atacante ya husmeó o se llevó {loot.length} archivos importantes. Defiende las PCs en alarma.</p>
          </div>
        </div>
      )}

      {/* Telemetría y Alertas TGNN */}
      <div className="alertas-section">
        <h4>🚨 Alarmas recientes</h4>
        {alertas.length === 0 ? (
          <p className="muted">Todo tranquilo por ahora. Nada raro en la red.</p>
        ) : (
          <div className="alertas-list">
            {alertas.map((a, i) => (
              <div key={i} className={`alerta-card ${a.verdadera ? 'real' : 'fp'}`}>
                <div className="ac-top">
                  <b>{st.nodos.find(n => n.id === a.nodoId)?.nombre ?? a.nodoId}</b>
                  <span className="ac-score">Sospecha {(a.score * 100).toFixed(0)}%</span>
                  <span className={`ac-type ${a.verdadera ? 'tag-tp' : 'tag-fp'}`}>
                    {a.verdadera ? 'Amenaza real' : 'Quizá falsa alarma'}
                  </span>
                </div>
                <div className="ac-signals">
                  {Object.entries(a.senales)
                    .filter(([, v]) => v > 0.05)
                    .map(([k, v]) => (
                      <span key={k} className="sig-chip">
                        {k.replace('s_', '')}: {v.toFixed(2)}
                      </span>
                    ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Control del Nodo Seleccionado */}
      {!sel ? (
        <div className="select-prompt">
          <span className="prompt-icon">🛡️</span>
          <p><b>¿Qué hago?</b> Vigila las alarmas y haz clic en la PC sospechosa para defenderla. Tu meta: <b>aguantar hasta que se acabe el tiempo</b> — si el atacante no toma TODAS las máquinas, ganas tú. Ojo: defender una PC sana molesta a los usuarios y te baja puntos.</p>
        </div>
      ) : (
        <div className="target-section">
          <div className="target-card defense">
            <div className="target-header">
              <div>
                <span className="target-type">{sel.tipo.toUpperCase()}</span>
                <h4>{sel.nombre}</h4>
              </div>
              <span className={`target-state state-${sel.estado}`}>{sel.estado.toUpperCase()}</span>
            </div>

            <div className="score-meter">
              <div className="sm-label">
                <span>Nivel de sospecha:</span>
                <b>{(sel.score * 100).toFixed(0)}%</b>
              </div>
              <div className="sm-bar">
                <div
                  className="sm-fill"
                  style={{
                    width: `${Math.min(100, sel.score * 100)}%`,
                    background: sel.score > 0.7 ? '#f43f5e' : sel.score > 0.4 ? '#f59e0b' : '#10b981',
                  }}
                />
              </div>
            </div>

            <div className="target-pills">
              <span><b>Qué tan protegida está:</b> {(sel.posturaDefensiva * 100).toFixed(0)}%</span>
              <span><b>Datos que guarda:</b> {sel.valor} MB</span>
            </div>
          </div>

          <div className="respuestas-section">
            <h4>¿Cómo la defiendes? Elige una acción 👇</h4>
            <div className="respuestas-grid">
              {g.respuestas.map(r => {
                const rIconMap: Record<string, { icon: string; badge: string; badgeCls: string }> = {
                  aislar: { icon: '🛑', badge: 'Desconectar', badgeCls: 'tag-aislar' },
                  terminar_proceso: { icon: '⚡', badge: 'Cerrar programa', badgeCls: 'tag-kill' },
                  parchear_env: { icon: '🔒', badge: 'Contraseñas', badgeCls: 'tag-patch' },
                  parchear_vuln: { icon: '🛡️', badge: 'Reparar', badgeCls: 'tag-hotfix' },
                  yara_memory_scan: { icon: '🔍', badge: 'Revisar memoria', badgeCls: 'tag-yara' },
                  canary_token: { icon: '🐤', badge: 'Cebo', badgeCls: 'tag-canary' },
                  rotate_keys: { icon: '🔑', badge: 'Cambiar llaves', badgeCls: 'tag-keys' },
                  honeypot: { icon: '🍯', badge: 'Trampa', badgeCls: 'tag-honeypot' },
                  bloquear_ip: { icon: '🚫', badge: 'Bloquear', badgeCls: 'tag-block' },
                };
                const meta = rIconMap[r.id] ?? { icon: '🛡️', badge: 'SecOps', badgeCls: 'tag-patch' };
                const sinEnergia = r.costo > energia;

                return (
                  <button
                    key={r.id}
                    type="button"
                    className={`respuesta-btn ${r.id} ${sinEnergia ? 'locked' : ''}`}
                    disabled={auto || sinEnergia}
                    title={sinEnergia ? `Necesitas ${r.costo} de energía (tienes ${energia})` : r.descripcion}
                    onClick={() => g.send({ t: 'responder', respuesta: r.id, nodoId: sel.id })}
                  >
                    <div className="rb-top">
                      <span className="rb-name">{meta.icon} {r.nombre}</span>
                      <span className={`rb-tag ${meta.badgeCls}`}>{meta.badge}</span>
                    </div>
                    <span className="rb-desc">{r.descripcion}</span>
                    <div className="tb-costs">
                      <span className={`cost-chip ${sinEnergia ? 'cant' : ''}`}>⚡ {r.costo}</span>
                      <span className="cost-chip pts">★ {r.puntos}</span>
                    </div>
                    {r.comandoEjemplo && <code className="rb-cmd">{r.comandoEjemplo.replace('{target}', sel.id)}</code>}
                  </button>
                );
              })}
            </div>
            <p className="aviso">
              ⚠️ <b>Atención SecOps:</b> Aislar un nodo sin actividad hostil real genera penalización de disponibilidad (Falso Positivo).
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export function Reasoning({ st, lado }: { st: GameState; lado: Role }) {
  const ps = st.pensamientos.filter(p => p.lado === lado).slice(-6).reverse();

  return (
    <div className="panel razonamiento">
      <div className="panel-head">
        <h3>🧠 Bucle ReAct del Agente ({lado === 'attacker' ? '🔴 Red Team' : '🔵 Blue Team'})</h3>
        <span className="badge-agent">Trazable</span>
      </div>

      {ps.length === 0 ? (
        <p className="muted">El agente aún no ha emitido pensamientos. Activa el modo IA para observar el ciclo Observar → Razonar → Actuar.</p>
      ) : (
        <div className="thought-stream">
          {ps.map((p, i) => (
            <div key={i} className={`thought-card thought-${p.lado}`}>
              <div className="th-header">
                <span className="th-tick">Tick {p.tick}</span>
                <span className="th-action-badge">{p.accion}</span>
              </div>
              <div className="th-body">
                <div className="th-row">
                  <span className="th-lbl">Observa:</span>
                  <span className="th-val">{p.observacion}</span>
                </div>
                <div className="th-row">
                  <span className="th-lbl">Razona:</span>
                  <span className="th-val">{p.razonamiento}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
