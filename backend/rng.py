"""PRNG determinista sembrado (mulberry32). ADR-0004.

Port bit a bit del rng.ts de TypeScript: usa aritmética uint32 para producir
exactamente la misma secuencia que el frontend/servidor original, de modo que
(semilla + intents) reproduce la partida. Todo el azar del motor pasa por aquí.
"""

MASK = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    # Equivalente a Math.imul: low 32 bits del producto.
    return (a * b) & MASK


class Rng:
    def __init__(self, seed: int):
        self.s = seed & MASK

    def next(self) -> float:
        self.s = (self.s + 0x6D2B79F5) & MASK
        t = self.s
        t = _imul(t ^ (t >> 15), 1 | t) & MASK
        t = (((t + _imul(t ^ (t >> 7), 61 | t)) & MASK) ^ t) & MASK
        return ((t ^ (t >> 14)) & MASK) / 4294967296

    def chance(self, p: float) -> bool:
        return self.next() < p

    def pick(self, arr: list):
        return arr[int(self.next() * len(arr))]
