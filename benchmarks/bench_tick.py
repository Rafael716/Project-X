"""Benchmark del bucle de simulación (Unidad 3 — Rendimiento).

Mide el throughput del motor (ticks/seg) y, con --profile, saca el top de
funciones por tiempo acumulado (cProfile) para ubicar el cuello de botella.

El RNF-02 exige < 50 ms por tick en el servidor. Este bench establece el
*baseline* contra el que se compara cualquier optimización (antes/después).

Uso:
    python benchmarks/bench_tick.py                  # throughput
    python benchmarks/bench_tick.py --profile        # top 15 por tiempo
    python benchmarks/bench_tick.py --ticks 20000

ponytail: time.perf_counter + cProfile de la stdlib, nada de pytest-benchmark.
"""

import argparse
import cProfile
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

from engine import Engine          # noqa: E402
from scenario import cargar_escenario  # noqa: E402
import agents                      # noqa: E402


def una_partida(ticks: int, escenario_id: str = 'datacenter02', semilla: int = 1):
    """Corre `ticks` del motor en autoplay (atacante+defensor). Reinicia al terminar."""
    e = Engine(cargar_escenario(escenario_id), semilla)
    for i in range(ticks):
        ataque, _ = agents.atacante_decidir(e)
        respuesta, _ = agents.defensor_decidir(e)
        e.avanzar(ataque, respuesta)
        if e.terminada():
            e = Engine(cargar_escenario(escenario_id), semilla + i)
    return e


def throughput(ticks: int):
    t0 = time.perf_counter()
    una_partida(ticks)
    dt = time.perf_counter() - t0
    tps = ticks / dt
    ms = dt / ticks * 1000
    print(f'{ticks} ticks en {dt:.3f}s  ->  {tps:,.0f} ticks/s  |  {ms:.3f} ms/tick')
    presupuesto = 50.0  # RNF-02
    print(f'RNF-02 (<{presupuesto} ms/tick): {"OK" if ms < presupuesto else "FALLA"}  '
          f'(margen x{presupuesto / ms:.0f})')
    return ms


def profile(ticks: int):
    pr = cProfile.Profile()
    pr.enable()
    una_partida(ticks)
    pr.disable()
    pstats.Stats(pr).sort_stats('cumulative').print_stats(15)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--ticks', type=int, default=10000)
    ap.add_argument('--profile', action='store_true')
    args = ap.parse_args()
    if args.profile:
        profile(args.ticks)
    else:
        throughput(args.ticks)
