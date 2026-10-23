import type { Game } from './ws';

export function Summary({ g }: { g: Game }) {
  const st = g.estado!;
  const m = st.metricas;
  const win = st.ganador;
  const titulo = win === 'attacker' ? '🔴 Gana el Atacante' : win === 'defender' ? '🔵 Gana el Defensor' : '🤝 Empate';

  const descargar = () => {
    const replay = { codigo: st.codigo, escenarioId: st.escenarioId, ganador: win, metricas: m, eventos: st.eventos };
    const blob = new Blob([JSON.stringify(replay, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `project-x-${st.codigo}.json`;
    a.click();
  };
  const nueva = () => { sessionStorage.removeItem('px'); location.reload(); };

  return (
    <div className="centro">
      <div className="card resumen">
        <h1 className={`win win-${win}`}>{titulo}</h1>
        <div className="marcador-final">
          <div className="mf-side mf-atk"><span>🔴 Red Team</span><b>{m.puntosAtacante}</b></div>
          <span className="mf-vs">VS</span>
          <div className="mf-side mf-def"><span>🔵 Blue Team</span><b>{m.puntosDefensor}</b></div>
        </div>
        <div className="resumen-grid">
          <Res label="Datos exfiltrados" val={`${m.datosExfiltrados} / ${m.metaExfiltracion}`} />
          <Res label="Disponibilidad final" val={`${Math.round(m.disponibilidad * 100)}%`} />
          <Res label="MTTD (detección)" val={m.mttd === null ? 'no detectado' : `${m.mttd} ticks`} />
          <Res label="MTTR (contención)" val={m.mttr === null ? 'no contenido' : `${m.mttr} ticks`} />
          <Res label="Alertas totales" val={`${m.alertasTotales}`} />
          <Res label="Falsos positivos" val={`${m.alertasFalsas}`} />
        </div>
        <p className="muted">Duración: {st.tick} ticks · escenario {st.escenarioId}</p>
        <div className="acciones">
          <button className="ghost" onClick={descargar}>⬇ Descargar replay (JSON)</button>
          <button className="primary" onClick={nueva}>Nueva partida</button>
        </div>
      </div>
    </div>
  );
}
function Res({ label, val }: { label: string; val: string }) {
  return <div className="res"><span className="rl">{label}</span><span className="rv">{val}</span></div>;
}
