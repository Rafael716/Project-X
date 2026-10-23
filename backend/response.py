"""Respuestas del defensor. Mismo patrón que techniques.py (Sesión 2):
cada respuesta es una subclase de `Respuesta` que sobreescribe `aplicar()`.

aplicar(e, n) -> Resultado(texto, penalizacion, eco)
  - texto:        lo que ve el defensor en su consola.
  - penalizacion: cuánto baja la disponibilidad (aislar/bloquear tiene costo).
  - eco:          lo que NOTA el atacante en su terminal (o None si no nota nada).

Los textos están en lenguaje sencillo a propósito (fáciles de entender).
"""

from dataclasses import dataclass
from typing import Optional

from techniques import ORDEN_FASE, fase_index

# El aislamiento es temporal: mantener un host offline no es gratis (doc 06 §6).
DURACION_AISLAMIENTO = 24


@dataclass(frozen=True)
class Resultado:
    texto: str
    penalizacion: float = 0.0
    eco: Optional[str] = None


class Respuesta:
    id = ''
    nombre = ''
    descripcion = ''
    comandoEjemplo = ''
    costo = 2
    puntos = 20          # si el nodo era realmente hostil
    puntos_fp = 0        # si el nodo estaba sano (falso positivo)

    def meta(self) -> dict:
        return {k: getattr(self, k) for k in ('id', 'nombre', 'descripcion', 'comandoEjemplo', 'costo', 'puntos')}

    def aplicar(self, e, n) -> Resultado:  # pragma: no cover - siempre se sobreescribe
        raise NotImplementedError


def _subir_postura(n, delta):
    n['posturaDefensiva'] = min(1.0, n['posturaDefensiva'] + delta)


def _atenuar(n, senal, factor):
    if n['senales'].get(senal):
        n['senales'][senal] *= factor


class Aislar(Respuesta):
    id, nombre, costo, puntos, puntos_fp = 'aislar', 'Poner en cuarentena', 4, 40, -25
    descripcion = 'Desconecta la PC de la red por un rato. Frena cualquier ataque, pero la PC deja de dar servicio (cuesta más si estaba sana).'
    comandoEjemplo = 'poner-en-cuarentena {target}'

    def aplicar(self, e, n):
        sano = not n['compromisoReal'] and n['estado'] != 'sondeado'
        n['estado'] = 'aislado'
        n['aisladoHasta'] = e.tick + DURACION_AISLAMIENTO
        costo = n['valor'] * 0.05 + (n['valor'] * 0.15 if sano else 0)
        return Resultado(f"{n['nombre']} quedó en cuarentena (desconectada {DURACION_AISLAMIENTO} turnos)", costo,
                         f"Me cortaron el acceso: {n['nombre']} quedó desconectada por el defensor.")


class TerminarProceso(Respuesta):
    id, nombre, costo, puntos, puntos_fp = 'terminar_proceso', 'Cerrar el programa malicioso', 2, 25, -5
    descripcion = 'Cierra el programa que dejó el atacante y lo hace retroceder un paso. No sirve si dejó una puerta trasera.'
    comandoEjemplo = 'cerrar-programa {target}'

    def aplicar(self, e, n):
        if not (n['fase'] and n['compromisoReal']):
            return Resultado(f"Revisé {n['nombre']}: no había ningún programa malicioso activo", 0.05)
        if n.get('persistente'):
            return Resultado(f"Cerré el programa en {n['nombre']}, pero VOLVIÓ a aparecer (dejó una puerta trasera; usa 'Revisar la memoria')", 0,
                             f"Me cerraron el programa en {n['nombre']}, pero mi puerta trasera lo reinició.")
        i = fase_index(n['fase'])
        n['fase'] = ORDEN_FASE[i - 1] if i > 0 else None
        if fase_index(n['fase']) < fase_index('acceso_inicial'):
            n['compromisoReal'] = False
            e.sincronizar_estado(n)
        return Resultado(f"Cerré el programa malicioso en {n['nombre']}: el atacante perdió terreno", 0,
                         f"Me cerraron el acceso en {n['nombre']}.")


class ParchearEnv(Respuesta):
    id, nombre, costo, puntos = 'parchear_env', 'Cambiar las contraseñas', 2, 15
    descripcion = 'Cambia las contraseñas y limpia los archivos de configuración: la PC se defiende mejor y borra lo que el atacante había investigado.'
    comandoEjemplo = 'cambiar-contraseñas {target}'

    def aplicar(self, e, n):
        _subir_postura(n, 0.35)
        _atenuar(n, 's_recon', 0.3)
        _atenuar(n, 's_tecnica', 0.5)
        if n['fase'] == 'recon':
            n['fase'] = None
            e.sincronizar_estado(n)
        return Resultado(f"Cambié las contraseñas de {n['nombre']} (ahora se defiende mejor)", 0.01,
                         f"Las contraseñas que robé de {n['nombre']} ya no sirven.")


class Honeypot(Respuesta):
    id, nombre, costo, puntos = 'honeypot', 'Poner una trampa', 3, 15
    descripcion = 'Pone una PC falsa como señuelo al lado: hace que los ataques fallen más seguido.'
    comandoEjemplo = 'poner-trampa {target}'

    def aplicar(self, e, n):
        _subir_postura(n, 0.5)
        return Resultado(f"Puse una trampa junto a {n['nombre']} (ahora se defiende mejor)")


class BloquearIp(Respuesta):
    id, nombre, costo, puntos = 'bloquear_ip', 'Bloquear al atacante', 1, 10
    descripcion = 'Bloquea la conexión del atacante hacia esta PC y la ayuda a defenderse un poco mejor.'
    comandoEjemplo = 'bloquear-atacante {target}'

    def aplicar(self, e, n):
        n['senales']['s_reputacion'] = 0
        _subir_postura(n, 0.2)
        return Resultado(f"Bloqueé al atacante en {n['nombre']}", 0.03)


class ParchearVuln(Respuesta):
    id, nombre, costo, puntos = 'parchear_vuln', 'Reparar las fallas', 3, 15
    descripcion = 'Repara las fallas de la PC para que sean mucho más difíciles de aprovechar. También se defiende mejor.'
    comandoEjemplo = 'reparar-fallas {target}'

    def aplicar(self, e, n):
        for v in n['vulnerabilidades']:
            v['dificultad'] = min(0.95, v['dificultad'] + 0.4)
        _subir_postura(n, 0.35)
        _atenuar(n, 's_tecnica', 0.3)
        return Resultado(f"Reparé las fallas de {n['nombre']} (ahora se defiende mejor)", 0.02,
                         f"La falla que usaba en {n['nombre']} ya fue reparada.")


class YaraScan(Respuesta):
    id, nombre, costo, puntos = 'yara_memory_scan', 'Revisar la memoria', 2, 30
    descripcion = 'Busca puertas traseras y programas ocultos en la memoria sin apagar la PC: los quita y hace retroceder al atacante.'
    comandoEjemplo = 'revisar-memoria {target}'

    def aplicar(self, e, n):
        if n['compromisoReal'] and (n.get('persistente') or n['fase'] == 'escalada'):
            n['persistente'] = False
            if fase_index(n['fase']) >= fase_index('escalada'):
                n['fase'] = 'acceso_inicial'
            _atenuar(n, 's_tecnica', 0.2)
            n['score'] *= 0.5
            return Resultado(f"Revisé la memoria de {n['nombre']}: encontré y quité la puerta trasera del atacante", 0,
                             f"Me encontraron y borraron la puerta trasera en {n['nombre']}.")
        n['score'] *= 0.7
        return Resultado(f"Revisé la memoria de {n['nombre']}: todo limpio")


class CanaryToken(Respuesta):
    id, nombre, costo, puntos = 'canary_token', 'Poner un cebo', 2, 15
    descripcion = 'Deja contraseñas falsas como cebo: si el atacante las usa, salta la alarma. La PC se defiende mejor.'
    comandoEjemplo = 'poner-cebo {target}'

    def aplicar(self, e, n):
        _subir_postura(n, 0.4)
        n['senales']['s_canary'] = 0.8
        return Resultado(f"Puse un cebo en {n['nombre']} (ahora se defiende mejor)", 0,
                         f"Encontré contraseñas sospechosas en {n['nombre']}... puede ser una trampa.")


class RotarLlaves(Respuesta):
    id, nombre, costo, puntos = 'rotate_keys', 'Cambiar las llaves de acceso', 2, 20
    descripcion = 'Invalida las llaves de acceso robadas: corta los saltos del atacante entre PCs y la PC se defiende mejor.'
    comandoEjemplo = 'cambiar-llaves {target}'

    def aplicar(self, e, n):
        n['senales']['s_reputacion'] = 0
        _atenuar(n, 's_recon', 0.3)
        _subir_postura(n, 0.25)
        return Resultado(f"Cambié las llaves de acceso de {n['nombre']} (ahora se defiende mejor)", 0.01,
                         f"Las llaves que usaba en {n['nombre']} ya no sirven.")


RESPUESTA_POR_ID = {r.id: r for r in (
    Aislar(), TerminarProceso(), YaraScan(), ParchearEnv(), ParchearVuln(),
    RotarLlaves(), CanaryToken(), Honeypot(), BloquearIp(),
)}
RESPUESTAS = [r.meta() for r in RESPUESTA_POR_ID.values()]
