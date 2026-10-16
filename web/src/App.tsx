import { useGame } from './ws';
import { Lobby } from './Lobby';
import { Battle } from './Battle';
import { Summary } from './Summary';

export function App() {
  const g = useGame();

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">⚡ Project X <span className="sub">Simulador de ciber-combate · académico</span></div>
        <div className="status">
          {g.codigo && <span className="chip">Sala <b>{g.codigo}</b></span>}
          {g.role && <span className={`chip rol-${g.role}`}>{rolLabel(g.role)}</span>}
          <span className={`dot ${g.conectado ? 'on' : 'off'}`} title={g.conectado ? 'conectado' : 'desconectado'} />
        </div>
      </header>

      {g.error && <div className="toast-error" role="alert">{g.error}</div>}

      <main>
        {!g.estado || g.estado.estado === 'lobby' || g.estado.estado === 'lista'
          ? <Lobby g={g} />
          : g.estado.estado === 'terminada'
            ? <Summary g={g} />
            : <Battle g={g} />}
      </main>

      <footer className="foot">Simulación con fines educativos (SW707 · UNI-FIIS). No ejecuta ataques reales.</footer>
    </div>
  );
}

function rolLabel(r: string) { return r === 'attacker' ? '🔴 Atacante' : r === 'defender' ? '🔵 Defensor' : '👁 Espectador'; }
