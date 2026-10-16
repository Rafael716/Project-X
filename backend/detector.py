"""Detector de anomalía explicable (surrogate de TGNN). ADR-0005, doc 06 §5.
Port de detector.ts: señales con decaimiento EWMA por nodo -> score 0..1."""

import math
import re

DECAY = 0.82  # memoria temporal (la "ventana" del TGNN)
PESOS = {'s_recon': 1.4, 's_fanout': 1.0, 's_rareza': 1.6, 's_tecnica': 1.8, 's_reputacion': 1.2}
SESGO = 2.4

_RE_RECON = re.compile(r'recon|barrido|enumer', re.IGNORECASE)


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class Detector:
    def __init__(self, umbral: float = 0.6):
        self.umbral = umbral

    def decae(self, nodos: list) -> None:
        for n in nodos:
            for k in list(n['senales'].keys()):
                n['senales'][k] *= DECAY

    def observa(self, nodos: list, ev: dict) -> None:
        nodo_id = ev.get('nodoId')
        if not nodo_id:
            return
        n = next((x for x in nodos if x['id'] == nodo_id), None)
        if not n:
            return
        s = n['senales']

        def add(k, v):
            s[k] = s.get(k, 0) + v

        if ev['tipo'] == 'ataque':
            texto = ev['texto']
            ruido = 0.9 if '[ruido:alto]' in texto else 0.55 if '[ruido:medio]' in texto else 0.25
            if _RE_RECON.search(texto):
                add('s_recon', ruido)
            add('s_tecnica', ruido)
            add('s_rareza', 0.5 * ruido)
            add('s_reputacion', 0.4 * ruido)
        elif ev['tipo'] == 'benigno':
            add('s_fanout', 0.18)

    def califica(self, nodos: list, tick: int) -> list:
        alertas = []
        for n in nodos:
            if n['estado'] == 'aislado':
                n['score'] = 0
                continue
            s = n['senales']
            lineal = -SESGO + n['posturaDefensiva'] * 0.8
            for k, w in PESOS.items():
                lineal += w * s.get(k, 0)
            n['score'] = _sigmoid(lineal)
            if n['score'] > self.umbral:
                alertas.append({
                    'tick': tick, 'nodoId': n['id'], 'score': round(n['score'], 3),
                    'senales': {k: round(v, 2) for k, v in s.items()},
                    'verdadera': n['compromisoReal'] or n['estado'] == 'sondeado',
                })
        return alertas
