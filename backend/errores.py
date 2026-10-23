"""Jerarquía de excepciones de dominio (Sesión 5: "Diseño de jerarquías de dominio").

    ProjectXError                 <- capa media: base de TODA la app (captura global)
    ├─ EntradaInvalida            <- la barricada rechazó un mensaje (culpa del cliente)
    ├─ ReglaDeJuego               <- condición de error ESPERADA: jugada ilegal
    │   └─ SinEnergia             <- jugada válida pero sin energía suficiente
    ├─ PartidaNoEncontrada        <- código inexistente
    ├─ DemasiadasAcciones         <- contrapresión (429): el cliente envía muy rápido
    └─ ContratoRoto               <- BUG interno (pre/post/invariante). Fail-fast.

Las excepciones del lenguaje (KeyError, ValueError...) son la capa base: nunca
llegan a la UI. El gateway las envuelve (exception chaining, `raise X from e`)
para no perder la causa raíz en el log.

Cada excepción lleva `contexto` (dict) para que el log estructurado diga
qué partida, qué nodo, qué técnica... ("mensajes informativos", Sesión 5).
"""


class ProjectXError(Exception):
    # Mensaje apto para mostrar al jugador. El detalle técnico va en `contexto`.
    mensaje_usuario = 'Error interno del servidor'

    def __init__(self, mensaje: str, **contexto):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.contexto = contexto

    def para_usuario(self) -> str:
        return self.mensaje


class EntradaInvalida(ProjectXError):
    """Barricada (Sesión 4): el mensaje no cumple tipo/tamaño/rango."""


class ReglaDeJuego(ProjectXError):
    """Jugada ilegal según la kill chain (no es un bug: se informa y se sigue)."""


class SinEnergia(ReglaDeJuego):
    """La jugada es legal pero no alcanza la energía."""


class PartidaNoEncontrada(ProjectXError):
    pass


class DemasiadasAcciones(ProjectXError):
    """Contrapresión (Sesión 7): rechazo temporal en lugar de encolar sin límite."""


class ContratoRoto(ProjectXError):
    """Un contrato DbC falló: hay un bug en el servidor. Nunca culpa del jugador."""

    def para_usuario(self) -> str:
        return 'Error interno del servidor (contrato roto). Quedó registrado en el log.'
