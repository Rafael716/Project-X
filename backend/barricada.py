"""Barricada (Sesión 4: Programación Defensiva).

Todo lo que llega del navegador es NO CONFIABLE. Este módulo es la única puerta
entre el mundo hostil (WebSocket) y el núcleo confiable (match/engine):

  Capa 1 — tipo y tamaño:   ¿es JSON? ¿pesa menos de 4 KB? ¿cada campo es del tipo correcto?
  Capa 2 — rango y límites: nombre de 1..20 chars, código de 6 chars del alfabeto, enums cerrados.
  Capa 3 — semántica:       ¿la técnica/escenario existe? (contra los catálogos del servidor)

Si algo falla -> EntradaInvalida (ruta "Alarma": se avisa al cliente y se sigue).
Detrás de la barricada el motor asume datos limpios y usa contratos (contratos.py).

No hay eval, ni getattr con strings del cliente, ni carga dinámica de módulos:
los nombres que manda el cliente solo se usan como CLAVES de diccionarios
cerrados (lección Log4Shell de la Sesión 2).
"""

import json
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError

from errores import EntradaInvalida
from response import RESPUESTA_POR_ID
from scenario import ESCENARIOS
from techniques import TECNICA_POR_ID

MAX_BYTES = 4096

Role = Literal['attacker', 'defender', 'spectator']
Codigo = Annotated[str, StringConstraints(pattern=r'^[A-HJ-NP-Z2-9]{6}$')]
Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
IdCorto = Annotated[str, StringConstraints(pattern=r'^[a-z0-9_]{1,32}$')]
IntentId = Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_-]{1,40}$')]


class _Msg(BaseModel):
    model_config = ConfigDict(extra='forbid')  # campos desconocidos = mensaje inválido


class Crear(_Msg):
    t: Literal['crear']
    nombre: Nombre
    role: Role
    escenarioId: IdCorto = 'pymes01'
    semilla: Optional[Annotated[int, Field(ge=0, le=2**32 - 1)]] = None


class Unir(_Msg):
    t: Literal['unir']
    codigo: Codigo
    nombre: Nombre
    role: Role


class Reconectar(_Msg):
    t: Literal['reconectar']
    codigo: Codigo
    clientId: Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{8}$')]


class ElegirModo(_Msg):
    t: Literal['elegir_modo']
    modo: Literal['manual', 'autoplay']


class Listo(_Msg):
    t: Literal['listo']
    valor: bool


class Iniciar(_Msg):
    t: Literal['iniciar']


class Pausar(_Msg):
    t: Literal['pausar']
    valor: bool


class Atacar(_Msg):
    t: Literal['atacar']
    tecnicaId: IdCorto
    nodoId: IdCorto
    intentId: Optional[IntentId] = None


class Responder(_Msg):
    t: Literal['responder']
    respuesta: IdCorto
    nodoId: IdCorto
    intentId: Optional[IntentId] = None


MensajeCliente = Annotated[
    Union[Crear, Unir, Reconectar, ElegirModo, Listo, Iniciar, Pausar, Atacar, Responder],
    Field(discriminator='t'),
]
_adaptador = TypeAdapter(MensajeCliente)


def parsear(raw: str):
    """str crudo del socket -> mensaje tipado y validado, o EntradaInvalida."""
    # Capa 1: tamaño antes de parsear (evita gastar CPU en payloads gigantes).
    if len(raw.encode('utf-8', errors='ignore')) > MAX_BYTES:
        raise EntradaInvalida('Mensaje demasiado grande', bytes=len(raw))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise EntradaInvalida('JSON inválido') from e  # chaining: se conserva la causa
    # Capa 1 y 2: tipos, tamaños, rangos, enums.
    try:
        msg = _adaptador.validate_python(data)
    except ValidationError as e:
        primero = e.errors()[0]
        campo = '.'.join(str(x) for x in primero['loc']) or 'mensaje'
        raise EntradaInvalida(f'Campo inválido: {campo}', detalle=primero['msg']) from e
    # Capa 3: semántica contra los catálogos del servidor.
    if isinstance(msg, Crear) and msg.escenarioId not in ESCENARIOS:
        raise EntradaInvalida('Escenario desconocido', escenario=msg.escenarioId)
    if isinstance(msg, Atacar) and msg.tecnicaId not in TECNICA_POR_ID:
        raise EntradaInvalida('Técnica desconocida', tecnica=msg.tecnicaId)
    if isinstance(msg, Responder) and msg.respuesta not in RESPUESTA_POR_ID:
        raise EntradaInvalida('Respuesta desconocida', respuesta=msg.respuesta)
    return msg
