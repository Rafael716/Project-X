import type { SimNode, GameEvent, Alert } from '../../shared/protocol';

// Detector de anomalía explicable (surrogate de TGNN). ADR-0005, doc 06 §5.
// Mantiene señales con decaimiento EWMA por nodo y produce un score 0..1.

const DECAY = 0.82; // memoria temporal (la "ventana" del TGNN)
const PESOS: Record<string, number> = {
  s_recon: 1.4, s_fanout: 1.0, s_rareza: 1.6, s_tecnica: 1.8, s_reputacion: 1.2,
};
const SESGO = 2.4;

function sigmoid(x: number): number { return 1 / (1 + Math.exp(-x)); }

export class Detector {
  umbral: number;
  // pesos/sesgo expuestos como perillas por escenario (doc 06 §5, ponytail: calibración)
  constructor(umbral = 0.6) { this.umbral = umbral; }

  // Decaimiento al inicio de cada tick.
  decae(nodos: SimNode[]): void {
    for (const n of nodos) {
      for (const k of Object.keys(n.senales)) n.senales[k] *= DECAY;
    }
  }

  // Suma el aporte de un evento a las señales de su nodo.
  observa(nodos: SimNode[], ev: GameEvent): void {
    if (!ev.nodoId) return;
    const n = nodos.find(x => x.id === ev.nodoId);
    if (!n) return;
    const s = n.senales;
    const add = (k: string, v: number) => { s[k] = (s[k] ?? 0) + v; };
    if (ev.tipo === 'ataque') {
      // El sigilo importa: una técnica de bajo ruido casi no mueve las señales.
      const ruido = ev.texto.includes('[ruido:alto]') ? 0.9 : ev.texto.includes('[ruido:medio]') ? 0.55 : 0.25;
      if (/recon|barrido|enumer/i.test(ev.texto)) add('s_recon', ruido);
      add('s_tecnica', ruido);
      add('s_rareza', 0.5 * ruido);    // aristas raras, proporcional al ruido
      add('s_reputacion', 0.4 * ruido); // origen sospechoso, proporcional al ruido
    } else if (ev.tipo === 'benigno') {
      // El ruido benigno también mueve señales -> habilita falsos positivos (RF-31).
      add('s_fanout', 0.18);
    }
  }

  // Recalcula score por nodo y emite alertas nuevas.
  califica(nodos: SimNode[], tick: number): Alert[] {
    const alertas: Alert[] = [];
    for (const n of nodos) {
      if (n.estado === 'aislado') { n.score = 0; continue; }
      const s = n.senales;
      let lineal = -SESGO + n.posturaDefensiva * 0.8; // honeypot/vigilancia sube sensibilidad
      for (const k of Object.keys(PESOS)) lineal += PESOS[k] * (s[k] ?? 0);
      n.score = sigmoid(lineal);
      if (n.score > this.umbral) {
        alertas.push({
          tick, nodoId: n.id, score: Number(n.score.toFixed(3)),
          senales: redondea(s),
          verdadera: n.compromisoReal || n.estado === 'sondeado',
        });
      }
    }
    return alertas;
  }
}

function redondea(s: Record<string, number>): Record<string, number> {
  const o: Record<string, number> = {};
  for (const k of Object.keys(s)) o[k] = Number(s[k].toFixed(2));
  return o;
}
