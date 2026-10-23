"""Configuración externalizada + feature flags (Unidad 3, Etapa II).

Toda la configuración vive aquí y se lee de variables de entorno UNA vez al
importar. Ningún módulo del núcleo lee `os.environ` por su cuenta: piden a este
módulo. Así la configuración es:
  - externalizada: se cambia sin tocar código (`.env`, variables de entorno),
  - descubrible: `/api/config` la expone en caliente,
  - testeable: el test fija el entorno y reimporta.

Feature flags (`FEATURES`): activan/desactivan capacidades sin recompilar. El
servidor solo anuncia al cliente las técnicas/respuestas cuya feature está
encendida, y la barricada rechaza las apagadas (defensa en profundidad).

ponytail: os.environ + un dict, no pydantic-settings ni un framework de flags.
Subir a algo con recarga en caliente solo si de verdad se necesita togglear en
producción sin reiniciar.
"""

import os
from pathlib import Path


def _carga_dotenv() -> None:
    """Carga un .env del repo si existe (sin dependencia). Las variables ya
    presentes en el entorno mandan — el .env solo rellena lo que falta.
    ponytail: parser de 5 líneas, no python-dotenv."""
    for base in (Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent):
        f = base / '.env'
        if not f.exists():
            continue
        for linea in f.read_text(encoding='utf-8').splitlines():
            linea = linea.strip()
            if not linea or linea.startswith('#') or '=' not in linea:
                continue
            k, _, v = linea.partition('=')
            os.environ.setdefault(k.strip(), v.strip())
        break


_carga_dotenv()


def _flag(nombre: str, default: bool) -> bool:
    v = os.environ.get(nombre)
    if v is None:
        return default
    return v.strip().lower() in ('1', 'true', 'on', 'si', 'sí', 'yes')


def _num(nombre: str, default, tipo=int):
    v = os.environ.get(nombre)
    if v is None:
        return default
    try:
        return tipo(v)
    except ValueError:
        return default


# ---- red / runtime ----
PORT = _num('PORT', 8787)
TICK_SEG = _num('PX_TICK_SEG', 0.25, float)   # periodo del tick (ADR-0004)
LOG_LEVEL = os.environ.get('PX_LOG_LEVEL', 'INFO').upper()
LANG = os.environ.get('PX_LANG', 'es').lower()[:2]   # idioma de los mensajes al usuario (i18n)

# ---- Diseño por Contrato (Sesión 3) ----
CONTRATOS_ON = _flag('PX_CONTRATOS', True)    # verificación de invariantes en ejecución

# ---- perillas de balance (calibración del "mundo", doc 06 §5) ----
ENERGIA_MAX = _num('PX_ENERGIA_MAX', 10)
ENERGIA_REGEN = _num('PX_ENERGIA_REGEN', 1)
PUNTOS_META = _num('PX_PUNTOS_META', 300)
DETECTOR_UMBRAL = _num('PX_DETECTOR_UMBRAL', 0.6, float)

# ---- contrapresión (Sesión 7) ----
BACKPRESSURE_CAP = _num('PX_BP_CAP', 12)
BACKPRESSURE_RPS = _num('PX_BP_RPS', 8, float)

# ---- feature flags: capacidades activables sin recompilar ----
# clave -> (encendida_por_defecto, ids del catálogo que gobierna)
FEATURES: dict[str, bool] = {
    'honeypot': _flag('PX_FEATURE_HONEYPOT', True),      # respuesta "honeypot"
    'canary': _flag('PX_FEATURE_CANARY', True),          # respuesta "canary_token"
    'phishing': _flag('PX_FEATURE_PHISHING', True),      # técnica "phishing_spray"
    'nivel_dificil': _flag('PX_FEATURE_NIVEL_DIFICIL', True),  # escenario datacenter02
}

# qué id del catálogo depende de qué flag (lo que no aparece está siempre activo)
_GOBIERNA = {
    'honeypot': {'honeypot'},
    'canary_token': {'canary'},
    'phishing_spray': {'phishing'},
}


def feature_activa(catalogo_id: str) -> bool:
    """¿Está habilitado este id de técnica/respuesta según los feature flags?"""
    flag = next((f for f, ids in _GOBIERNA.items() if catalogo_id in ids), None)
    return True if flag is None else FEATURES.get(flag, True)


def filtra_catalogo(metas: list[dict]) -> list[dict]:
    """Devuelve solo las entradas del catálogo cuya feature está activa."""
    return [m for m in metas if feature_activa(m['id'])]


def publico() -> dict:
    """Vista segura de la config (para /api/config). Sin secretos — aquí no hay."""
    return {
        'port': PORT, 'tickSeg': TICK_SEG, 'lang': LANG, 'logLevel': LOG_LEVEL,
        'contratos': CONTRATOS_ON, 'features': dict(FEATURES),
        'balance': {'energiaMax': ENERGIA_MAX, 'energiaRegen': ENERGIA_REGEN,
                    'puntosMeta': PUNTOS_META, 'detectorUmbral': DETECTOR_UMBRAL},
    }


if __name__ == '__main__':
    # check: un flag apagado por entorno desactiva su id; el resto sigue activo.
    os.environ['PX_FEATURE_HONEYPOT'] = 'off'
    import importlib, config
    importlib.reload(config)
    assert config.feature_activa('honeypot') is False, 'el flag apagado debió desactivar honeypot'
    assert config.feature_activa('aislar') is True, 'un id sin flag debe seguir activo'
    assert config.feature_activa('canary_token') is True
    print('config OK:', config.publico())
