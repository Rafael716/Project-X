"""Patrones de tolerancia a fallas (Sesión 7).

- CircuitBreaker: CERRADO -> ABIERTO -> SEMI_ABIERTO -> CERRADO.
- TokenBucket: contrapresión ("no aceptes más de lo que puedes procesar").
- PoliticaResiliente: el "Proxy de Resiliencia" (decorador) de la diapositiva
  "Arquitectura de una PC2 exitosa": envuelve la política de un agente IA con
  circuit breaker + timeout suave + degradación elegante a una política de
  respaldo. Si mañana la política primaria es un LLM por red (ADR-0006) y se
  cae, la partida sigue: el agente baja a la heurística en vez de congelar el tick.

El reloj se inyecta (por defecto time.monotonic). Para los agentes se usa el
tick del motor como reloj, así el breaker también es determinista (ADR-0004).
"""

import time

from observabilidad import evento, contadores
import logging

CERRADO, ABIERTO, SEMI_ABIERTO = 'cerrado', 'abierto', 'semi_abierto'


class CircuitBreaker:
    def __init__(self, umbral_fallos: int = 3, espera: float = 20, reloj=time.monotonic, nombre: str = 'cb'):
        self.umbral_fallos = umbral_fallos
        self.espera = espera          # cuánto queda ABIERTO antes de dejar pasar una sonda
        self.reloj = reloj
        self.nombre = nombre
        self.estado = CERRADO
        self.fallos = 0
        self._abierto_desde = 0.0

    def permite(self) -> bool:
        """Consulta (CQS) + transición temporal ABIERTO -> SEMI_ABIERTO."""
        if self.estado == ABIERTO and self.reloj() - self._abierto_desde >= self.espera:
            self._pasar(SEMI_ABIERTO)
        return self.estado != ABIERTO

    def exito(self) -> None:
        self.fallos = 0
        if self.estado != CERRADO:
            self._pasar(CERRADO)

    def fallo(self) -> None:
        self.fallos += 1
        if self.estado == SEMI_ABIERTO or self.fallos >= self.umbral_fallos:
            self._abierto_desde = self.reloj()
            self._pasar(ABIERTO)

    def _pasar(self, nuevo: str) -> None:
        evento(logging.WARNING, 'circuit_breaker_transicion', breaker=self.nombre, de=self.estado, a=nuevo)
        contadores[f'cb.{self.nombre}.{nuevo}'] += 1
        self.estado = nuevo


class TokenBucket:
    """Hasta `capacidad` acciones de golpe; se recarga `por_segundo` fichas/s."""

    def __init__(self, capacidad: float = 12, por_segundo: float = 8, reloj=time.monotonic):
        self.capacidad = capacidad
        self.por_segundo = por_segundo
        self.reloj = reloj
        self.fichas = capacidad
        self._ultimo = reloj()

    def tomar(self) -> bool:
        ahora = self.reloj()
        self.fichas = min(self.capacidad, self.fichas + (ahora - self._ultimo) * self.por_segundo)
        self._ultimo = ahora
        if self.fichas >= 1:
            self.fichas -= 1
            return True
        return False


class PoliticaResiliente:
    """Proxy de resiliencia alrededor de una política de agente.

    decidir(e) -> (intent | None, pensamiento)
    """

    def __init__(self, primaria, respaldo, nombre: str, presupuesto_ms: float = 50, reloj=None):
        self.primaria = primaria
        self.respaldo = respaldo
        self.nombre = nombre
        self.presupuesto_ms = presupuesto_ms  # timeout suave: tardar más cuenta como fallo
        self.breaker = CircuitBreaker(umbral_fallos=3, espera=40, reloj=reloj or time.monotonic, nombre=nombre)

    def decidir(self, e):
        if not self.breaker.permite():
            return self._degradado(e, 'circuito ABIERTO: usando política de respaldo')
        t0 = time.perf_counter()
        try:
            resultado = self.primaria.decidir(e)
        except Exception as ex:  # cualquier falla de la política primaria se contiene aquí (bulkhead)
            self.breaker.fallo()
            evento(logging.ERROR, 'agente_fallo', agente=self.nombre, error=repr(ex), breaker=self.breaker.estado)
            return self._degradado(e, f'la política primaria falló ({type(ex).__name__})')
        if (time.perf_counter() - t0) * 1000 > self.presupuesto_ms:
            self.breaker.fallo()
            evento(logging.WARNING, 'agente_lento', agente=self.nombre, presupuesto_ms=self.presupuesto_ms)
        else:
            self.breaker.exito()
        return resultado

    def _degradado(self, e, motivo: str):
        contadores[f'agente.{self.nombre}.degradado'] += 1
        intent, th = self.respaldo.decidir(e)
        th = {**th, 'razonamiento': f"[modo degradado: {motivo}] {th['razonamiento']}"}
        return intent, th
