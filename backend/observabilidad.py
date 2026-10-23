"""Observabilidad (Sesión 5): logs estructurados en JSON + contexto mapeado (MDC).

- Cada línea de log es un objeto JSON (consultable por máquinas, no solo humanos).
- `correlation_id` y `partida` viajan en un ContextVar: es el equivalente
  async del MDC/ThreadLocal de Java. Cada mensaje WS abre su propio contexto,
  así las líneas de dos jugadores que escriben a la vez no se mezclan.
- Niveles: DEBUG (detalle de desarrollo), INFO (hitos de negocio: partida
  creada, iniciada, terminada), WARNING (anomalía recuperable: jugada
  rechazada, cliente lento), ERROR (falló una operación), CRITICAL (bug).
- Se loguea UNA sola vez, en la frontera (gateway). Nada de log-and-throw.
"""

import json
import logging
import os
import secrets
import sys
import time
from collections import Counter
from contextvars import ContextVar

correlation_id: ContextVar[str] = ContextVar('correlation_id', default='-')
partida_actual: ContextVar[str] = ContextVar('partida', default='-')

# Contadores simples expuestos en /metrics (sin dependencias externas).
contadores: Counter = Counter()


def nuevo_correlation_id() -> str:
    return secrets.token_hex(4)


class FormatoJSON(logging.Formatter):
    def format(self, r: logging.LogRecord) -> str:
        data = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(r.created)) + f'.{int(r.msecs):03d}Z',
            'level': r.levelname,
            'event': r.getMessage(),
            'correlation_id': correlation_id.get(),
            'partida': partida_actual.get(),
        }
        data.update(getattr(r, 'ctx', {}))
        if r.exc_info:
            data['exception'] = self.formatException(r.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def _crear_logger() -> logging.Logger:
    lg = logging.getLogger('projectx')
    if not lg.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(FormatoJSON())
        lg.addHandler(h)
        lg.setLevel(os.environ.get('PX_LOG_LEVEL', 'INFO').upper())
        lg.propagate = False
    return lg


log = _crear_logger()


def evento(nivel: int, nombre: str, **ctx) -> None:
    """log.info('x', extra=...) con los campos de contexto en la raíz del JSON."""
    contadores[f'log.{logging.getLevelName(nivel).lower()}'] += 1
    log.log(nivel, nombre, extra={'ctx': ctx})
