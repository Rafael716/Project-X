import type { Game } from './ws';

export function Summary({ g }: { g: Game }) {
  const st = g.estado!;
  const m = st.metricas;
  const win = st.ganador;
  const titulo = win === 'attacker' ? '🔴 Gana el Atacante' : win === 'defender' ? '🔵 Gana el Defensor' : '🤝 Empate';
  const motivo = win === 'attacker'
    ? '¡Tomó TODAS las máquinas de la red!'
    : 'El defensor aguantó: el atacante no logró tomar todas las máquinas antes de que se acabara el tiempo.';

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
        <p className="muted" style={{ marginTop: -6 }}>{motivo}</p>
        <div className="marcador-final">
          <div className="mf-side mf-atk"><span>🔴 Red Team</span><b>{m.puntosAtacante}</b></div>
          <span className="mf-vs">VS</span>
          <div className="mf-side mf-def"><span>🔵 Blue Team</span><b>{m.puntosDefensor}</b></div>
        </div>
        <div className="resumen-grid">
          <Res label="Máquinas tomadas" val={`${m.maquinasTomadas} / ${m.maquinasTotales}`} />
          <Res label="Datos robados" val={`${m.datosExfiltrados} / ${m.metaExfiltracion} MB`} />
          <Res label="Red funcionando" val={`${Math.round(m.disponibilidad * 100)}%`} />
          <Res label="Tardó en detectar" val={m.mttd === null ? 'no lo detectó' : `${m.mttd} turnos`} />
          <Res label="Tardó en frenar" val={m.mttr === null ? 'no lo frenó' : `${m.mttr} turnos`} />
          <Res label="Alarmas totales" val={`${m.alertasTotales}`} />
          <Res label="Falsas alarmas" val={`${m.alertasFalsas}`} />
        </div>
        <p className="muted">Duración: {st.tick} turnos · nivel {st.escenarioId}</p>
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
