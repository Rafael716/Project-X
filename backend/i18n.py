"""Internacionalización (i18n/l10n) — Unidad 3.

El dominio es un juego pensado para la UNI (español primero), así que el peso
de i18n es deliberadamente acotado: se externalizan los **mensajes que ve el
jugador** a un catálogo por idioma, seleccionable con `PX_LANG`. Esto prueba la
competencia (separar texto de código, fallback a la clave, locale configurable)
sin arrastrar gettext/Babel ni archivos .po, que serían sobre-ingeniería para
dos idiomas y ~15 cadenas.

ponytail: dict por locale + fallback. Migrar a gettext solo si entran idiomas
con pluralización/entidades de traducción reales.
"""

import config

CATALOGO: dict[str, dict[str, str]] = {
    'es': {
        'rate_limit': 'Vas demasiado rápido, espera un momento (429)',
        'error_interno': 'Error interno del servidor',
        'sin_partida': 'No estás en una partida',
        'sin_rol': 'Sin rol asignado',
        'rol_tomado': 'Ese rol ya está tomado',
        'codigo_inexistente': 'Código inexistente',
        'faltan_jugadores': 'Faltan jugadores',
        'ambos_listos': 'Ambos deben estar listos',
    },
    'en': {
        'rate_limit': "You're going too fast, slow down (429)",
        'error_interno': 'Internal server error',
        'sin_partida': 'You are not in a match',
        'sin_rol': 'No role assigned',
        'rol_tomado': 'That role is already taken',
        'codigo_inexistente': 'Unknown code',
        'faltan_jugadores': 'Missing players',
        'ambos_listos': 'Both players must be ready',
    },
}


def t(clave: str, lang: str | None = None) -> str:
    """Traduce una clave al idioma activo; si falta, cae al español y luego a la clave."""
    lang = (lang or config.LANG)
    return (CATALOGO.get(lang, {}).get(clave)
            or CATALOGO['es'].get(clave)
            or clave)


if __name__ == '__main__':
    assert t('rate_limit', 'en').startswith("You're")
    assert t('rate_limit', 'es').startswith('Vas')
    assert t('clave_que_no_existe') == 'clave_que_no_existe'   # fallback a la clave
    assert t('sin_rol', 'fr') == CATALOGO['es']['sin_rol']      # locale desconocido -> es
    print('i18n OK')
