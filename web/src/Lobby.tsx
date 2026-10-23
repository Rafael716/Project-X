import { useState } from 'react';
import type { Game } from './ws';
import type { Role, PlayMode } from '../../shared/protocol';

export function Lobby({ g }: { g: Game }) {
  // Ya estamos en una sala -> sala de espera.
  if (g.codigo) return <SalaEspera g={g} />;
  return <Entrada g={g} />;
}

const NIVELES = [
  { id: 'pymes01', nombre: 'PYMES-01', desc: 'Red pequeña · 5 hosts · Normal', dif: 'Normal' },
  { id: 'datacenter02', nombre: 'DATACENTER-02', desc: 'Datacenter endurecido · 6 hosts · Difícil', dif: 'Difícil' },
];

function Entrada({ g }: { g: Game }) {
  const [tab, setTab] = useState<'crear' | 'unir'>('crear');
  const [nombre, setNombre] = useState('');
  const [role, setRole] = useState<Role>('attacker');
  const [codigo, setCodigo] = useState('');
  const [escenarioId, setEscenarioId] = useState('pymes01');

  return (
    <div className="centro">
      <div className="card hero">
        <h1>Enfréntate en el ciber-rango</h1>
        <p>Dos jugadores, dos PCs. Uno <b className="rojo">ataca</b>, otro <b className="azul">defiende</b> una red simulada. Cada lado puede jugarlo una persona o su agente de IA.</p>

        <div className="tabs">
          <button className={tab === 'crear' ? 'on' : ''} onClick={() => setTab('crear')}>Crear partida</button>
          <button className={tab === 'unir' ? 'on' : ''} onClick={() => setTab('unir')}>Unirse</button>
        </div>

        <label>Tu nombre
          <input value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Ej: Leonardo" maxLength={20} />
        </label>

        <fieldset className="roles">
          <legend>Elige tu lado</legend>
          <RoleBtn r="attacker" cur={role} set={setRole} label="🔴 Atacante" desc="Red Team" />
          <RoleBtn r="defender" cur={role} set={setRole} label="🔵 Defensor" desc="Blue Team" />
          <RoleBtn r="spectator" cur={role} set={setRole} label="👁 Espectador" desc="Solo mirar" />
        </fieldset>

        {tab === 'crear' && (
          <fieldset className="roles niveles">
            <legend>Elige el nivel</legend>
            {NIVELES.map(n => (
              <button type="button" key={n.id} className={`rolecard ${escenarioId === n.id ? 'on' : ''}`} onClick={() => setEscenarioId(n.id)}>
                <span className="rl">{n.nombre} <span className={`dif-tag dif-${n.dif.toLowerCase()}`}>{n.dif}</span></span>
                <span className="rd">{n.desc}</span>
              </button>
            ))}
          </fieldset>
        )}

        {tab === 'unir' && (
          <label>Código de la sala
            <input value={codigo} onChange={e => setCodigo(e.target.value.toUpperCase())} placeholder="ABC123" maxLength={6} className="cod" />
          </label>
        )}

        <button className="primary big" disabled={!g.conectado || !nombre || (tab === 'unir' && codigo.length !== 6)}
          onClick={() => tab === 'crear'
            ? g.send({ t: 'crear', nombre, role, escenarioId })
            : g.send({ t: 'unir', codigo, nombre, role })}>
          {tab === 'crear' ? 'Crear y entrar' : 'Entrar a la sala'}
        </button>
        {!g.conectado && <p className="muted">Conectando al servidor…</p>}
      </div>
    </div>
  );
}

function RoleBtn({ r, cur, set, label, desc }: { r: Role; cur: Role; set: (r: Role) => void; label: string; desc: string }) {
  return (
    <button type="button" className={`rolecard ${cur === r ? 'on' : ''} rol-${r}`} onClick={() => set(r)}>
      <span className="rl">{label}</span><span className="rd">{desc}</span>
    </button>
  );
}

function SalaEspera({ g }: { g: Game }) {
  const st = g.estado;
  const yo = st?.jugadores.find(j => j.role === g.role);
  const otros = st?.jugadores.filter(j => j.role !== 'spectator') ?? [];
  const ambosListos = otros.length === 2 && otros.every(j => j.conectado && (j.role === 'spectator' || j.listo));

  return (
    <div className="centro">
      <div className="card">
        <h2>Sala <span className="cod">{g.codigo}</span></h2>
        <p className="muted">Comparte este código con el otro jugador. En la otra PC: abre la misma dirección y pulsa «Unirse».</p>

        <div className="slots">
          {(['attacker', 'defender'] as Role[]).map(r => {
            const j = st?.jugadores.find(x => x.role === r);
            return (
              <div key={r} className={`slot rol-${r} ${j?.conectado ? '' : 'vacio'}`}>
                <div className="slot-rol">{r === 'attacker' ? '🔴 Atacante' : '🔵 Defensor'}</div>
                <div className="slot-nom">{j?.conectado ? j.nombre : 'esperando…'}</div>
                {j?.conectado && <div className="slot-estado">{j.modo === 'autoplay' ? '🤖 IA' : '🧑 manual'} · {j.listo ? '✅ listo' : '⏳'}</div>}
              </div>
            );
          })}
        </div>

        {g.role !== 'spectator' && (
          <div className="controles">
            <div className="modo">
              <span>¿Quién juega tu lado?</span>
              <ModoBtn g={g} modo="manual" cur={yo?.modo} label="🧑 Yo (manual)" />
              <ModoBtn g={g} modo="autoplay" cur={yo?.modo} label="🤖 Agente IA" />
            </div>
            <button className={yo?.listo ? 'ghost' : 'primary'} onClick={() => g.send({ t: 'listo', valor: !yo?.listo })}>
              {yo?.listo ? 'Cancelar listo' : 'Estoy listo'}
            </button>
            <button className="primary big" disabled={!ambosListos} onClick={() => g.send({ t: 'iniciar' })}>
              ▶ Iniciar partida
            </button>
          </div>
        )}
        {!ambosListos && <p className="muted">La partida inicia cuando atacante y defensor estén conectados y listos.</p>}
      </div>
    </div>
  );
}

function ModoBtn({ g, modo, cur, label }: { g: Game; modo: PlayMode; cur?: PlayMode; label: string }) {
  return <button className={`pill ${cur === modo ? 'on' : ''}`} onClick={() => g.send({ t: 'elegir_modo', modo })}>{label}</button>;
}
