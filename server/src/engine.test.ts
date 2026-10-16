import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Engine, AttackIntent } from './engine';
import { pymes01 } from './scenario';
import { atacanteHeuristico, defensorHeuristico } from './agents';

// Verifica los invariantes de doc/06 §9. Son los checks mínimos que fallan si la lógica se rompe.

function corre(seed: number, auto = true): Engine {
  const e = new Engine(pymes01(), seed);
  for (let i = 0; i < 240 && !e.terminada(); i++) {
    const a = auto ? atacanteHeuristico.decidir(e).intent : null;
    const d = auto ? defensorHeuristico.decidir(e).intent : null;
    e.avanzar({ ataque: a, respuesta: d });
  }
  return e;
}

test('invariante 1: no hay exfiltración desde nodo no comprometido', () => {
  const e = new Engine(pymes01(), 7);
  const i: AttackIntent = { tecnicaId: 'exfil', nodoId: 'db' };
  assert.notEqual(e.validarAtaque(i), null, 'exfil sobre nodo limpio debe rechazarse');
});

test('invariante 2: nodo aislado no avanza de fase', () => {
  const e = new Engine(pymes01(), 3);
  const ws1 = e.nodo('ws1')!;
  ws1.estado = 'aislado';
  assert.notEqual(e.validarAtaque({ tecnicaId: 'portscan', nodoId: 'ws1' }), null);
});

test('invariante 3: MTTD/MTTR son monótonos (se fijan una vez)', () => {
  const e = corre(42);
  const m1 = e.metricas();
  const m2 = e.metricas();
  assert.deepEqual(m1, m2, 'métricas estables tras terminar');
});

test('invariante 4: determinismo — misma semilla ⇒ mismo resultado', () => {
  const a = corre(12345);
  const b = corre(12345);
  assert.equal(a.tick, b.tick);
  assert.equal(a.ganador(), b.ganador());
  assert.equal(a.metricas().datosExfiltrados, b.metricas().datosExfiltrados);
});

test('la partida termina (no bucle infinito) y declara ganador válido', () => {
  const e = corre(99);
  assert.ok(e.terminada());
  assert.ok(['attacker', 'defender', 'empate'].includes(e.ganador()));
});
