"""Respuestas del defensor. Mismo patrón que techniques.py (Sesión 2):
cada respuesta es una subclase de `Respuesta` que sobreescribe `aplicar()`.

aplicar(e, n) -> Resultado(texto, penalizacion, eco)
  - texto:        lo que ve el defensor en su consola.
  - penalizacion: cuánto baja la disponibilidad (aislar/bloquear tiene costo).
  - eco:          lo que NOTA el atacante en su terminal (o None si no nota nada).
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
    id, nombre, costo, puntos, puntos_fp = 'aislar', 'Aislar nodo (cuarentena)', 4, 40, -25
    descripcion = 'Corta la red del host por 24 ticks. Frena todo ataque, pero cuesta disponibilidad (más si era sano).'
    comandoEjemplo = 'xdp-filter load eth0 --mode drop  # cuarentena'

    def aplicar(self, e, n):
        sano = not n['compromisoReal'] and n['estado'] != 'sondeado'
        n['estado'] = 'aislado'
        n['aisladoHasta'] = e.tick + DURACION_AISLAMIENTO
        costo = n['valor'] * 0.05 + (n['valor'] * 0.15 if sano else 0)
        return Resultado(f"{n['nombre']} AISLADO en cuarentena por {DURACION_AISLAMIENTO} ticks", costo,
                         f"[-] CONNECTION DROPPED: {n['nombre']} inalcanzable (aislado por el defensor).")


class TerminarProceso(Respuesta):
    id, nombre, costo, puntos, puntos_fp = 'terminar_proceso', 'Terminar proceso (SIGKILL)', 2, 25, -5
    descripcion = 'Mata la shell hostil y hace retroceder una fase. No sirve si hay persistencia instalada.'
    comandoEjemplo = 'kill -9 $(pgrep -f beacon)'

    def aplicar(self, e, n):
        if not (n['fase'] and n['compromisoReal']):
            return Resultado(f"SIGKILL en {n['nombre']}: sin proceso hostil activo", 0.05)
        if n.get('persistente'):
            return Resultado(f"SIGKILL en {n['nombre']}: el proceso REAPARECE (hay persistencia; usa YARA)", 0,
                             f"[!] Shell reiniciada por el cron de persistencia en {n['nombre']}.")
        i = fase_index(n['fase'])
        n['fase'] = ORDEN_FASE[i - 1] if i > 0 else None
        if fase_index(n['fase']) < fase_index('acceso_inicial'):
            n['compromisoReal'] = False
            e.sincronizar_estado(n)
        return Resultado(f"Proceso hostil terminado en {n['nombre']}: retrocede a {n['fase'] or 'limpio'}", 0,
                         f"[-] SIGNAL KILLED: tu shell en {n['nombre']} fue terminada.")


class ParchearEnv(Respuesta):
    id, nombre, costo, puntos = 'parchear_env', 'Rotar secretos (.env)', 2, 15
    descripcion = 'Sanea .env y rota credenciales: +35% postura, borra el reconocimiento del atacante.'
    comandoEjemplo = 'vault-rotate --env /app/.env && chmod 600 *.env'

    def aplicar(self, e, n):
        _subir_postura(n, 0.35)
        _atenuar(n, 's_recon', 0.3)
        _atenuar(n, 's_tecnica', 0.5)
        if n['fase'] == 'recon':
            n['fase'] = None
            e.sincronizar_estado(n)
        return Resultado(f"Secretos rotados en {n['nombre']} (postura +35%)", 0.01,
                         f"[-] ACCESS DENIED (403): credenciales de {n['nombre']} rotadas.")


class Honeypot(Respuesta):
    id, nombre, costo, puntos = 'honeypot', 'Desplegar honeypot', 3, 15
    descripcion = 'Señuelo junto al host: +50% postura defensiva (los ataques fallan más).'
    comandoEjemplo = 'docker run -d -p 8080:80 cowrie/cowrie'

    def aplicar(self, e, n):
        _subir_postura(n, 0.5)
        return Resultado(f"Honeypot desplegado junto a {n['nombre']} (postura +50%)")


class BloquearIp(Respuesta):
    id, nombre, costo, puntos = 'bloquear_ip', 'Bloquear origen', 1, 10
    descripcion = 'Firewall contra la IP hostil: borra la señal de reputación, +20% postura.'
    comandoEjemplo = 'iptables -A INPUT -s 10.66.6.6 -j DROP'

    def aplicar(self, e, n):
        n['senales']['s_reputacion'] = 0
        _subir_postura(n, 0.2)
        return Resultado(f"Origen hostil bloqueado para {n['nombre']}", 0.03)


class ParchearVuln(Respuesta):
    id, nombre, costo, puntos = 'parchear_vuln', 'Parchear CVEs (hotfix)', 3, 15
    descripcion = 'Sube la dificultad de todas las vulnerabilidades del host y +35% postura.'
    comandoEjemplo = 'apt-get --only-upgrade install openssl -y'

    def aplicar(self, e, n):
        for v in n['vulnerabilidades']:
            v['dificultad'] = min(0.95, v['dificultad'] + 0.4)
        _subir_postura(n, 0.35)
        _atenuar(n, 's_tecnica', 0.3)
        return Resultado(f"CVEs parchados en {n['nombre']} (postura +35%)", 0.02,
                         f"[-] EXPLOIT MITIGATED: el servicio de {n['nombre']} fue parchado.")


class YaraScan(Respuesta):
    id, nombre, costo, puntos = 'yara_memory_scan', 'Escaneo YARA en memoria', 2, 30
    descripcion = 'Caza beacons y persistencia en RAM sin apagar el servicio: quita la persistencia y baja de escalada.'
    comandoEjemplo = 'yara -s -r c2_beacons.yar /proc/*/mem'

    def aplicar(self, e, n):
        if n['compromisoReal'] and (n.get('persistente') or n['fase'] == 'escalada'):
            n['persistente'] = False
            if fase_index(n['fase']) >= fase_index('escalada'):
                n['fase'] = 'acceso_inicial'
            _atenuar(n, 's_tecnica', 0.2)
            n['score'] *= 0.5
            return Resultado(f"YARA en {n['nombre']}: [MATCH] beacon/persistencia neutralizados", 0,
                             f"[-] BEACON DESTROYED: tu implante en {n['nombre']} fue purgado.")
        n['score'] *= 0.7
        return Resultado(f"YARA en {n['nombre']}: memoria limpia")


class CanaryToken(Respuesta):
    id, nombre, costo, puntos = 'canary_token', 'Plantar HoneyToken', 2, 15
    descripcion = 'Credenciales señuelo en el host: +40% postura y el detector queda más sensible ahí.'
    comandoEjemplo = 'canary-deploy --token aws_key --output ~/.aws/credentials'

    def aplicar(self, e, n):
        _subir_postura(n, 0.4)
        n['senales']['s_canary'] = 0.8
        return Resultado(f"HoneyToken sembrado en {n['nombre']} (postura +40%)", 0,
                         f"[!] DECOY SUSPECTED: credenciales sospechosas en {n['nombre']}.")


class RotarLlaves(Respuesta):
    id, nombre, costo, puntos = 'rotate_keys', 'Rotar llaves SSH / Kerberos', 2, 20
    descripcion = 'Revoca llaves y tickets: corta movimientos laterales, +25% postura.'
    comandoEjemplo = 'kadmin.local -q "cpw -randkey krbtgt/CORP"'

    def aplicar(self, e, n):
        n['senales']['s_reputacion'] = 0
        _atenuar(n, 's_recon', 0.3)
        _subir_postura(n, 0.25)
        return Resultado(f"Llaves y tickets revocados en {n['nombre']} (postura +25%)", 0.01,
                         f"[-] AUTH REJECTED: llaves de {n['nombre']} revocadas.")


RESPUESTA_POR_ID = {r.id: r for r in (
    Aislar(), TerminarProceso(), YaraScan(), ParchearEnv(), ParchearVuln(),
    RotarLlaves(), CanaryToken(), Honeypot(), BloquearIp(),
)}
RESPUESTAS = [r.meta() for r in RESPUESTA_POR_ID.values()]
