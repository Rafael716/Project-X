"""Respuestas del defensor. Port de response.ts."""

from techniques import fase_index, ORDEN_FASE

# El aislamiento es temporal: mantener un host offline no es gratis (doc 06 §6).
DURACION_AISLAMIENTO = 24

RESPUESTAS = [
    {'id': 'aislar', 'nombre': 'Aislar nodo (Cuarentena)',
     'descripcion': 'Corta la conectividad de red del host. Detiene ataques de inmediato pero degrada la disponibilidad si es un FP.',
     'comandoEjemplo': 'tc qdisc add dev eth0 root netem loss 100% # o eBPF xdp drop'},
    {'id': 'terminar_proceso', 'nombre': 'Terminar proceso (SIGKILL)',
     'descripcion': 'Mata el proceso/reverse shell sospechoso y revierte la kill chain al estado previo.',
     'comandoEjemplo': 'ebpf_kill -pid $(pgrep -f "sh|nc|beacon") -9'},
    {'id': 'parchear_env', 'nombre': 'Parchear .env y rotar secretos',
     'descripcion': 'Sanea variables .env, revoca tokens y restringe acceso a documentos confidenciales.',
     'comandoEjemplo': 'vault-rotate --env /app/.env && chmod 600 *.env *.docx'},
    {'id': 'honeypot', 'nombre': 'Desplegar honeypot / señuelo',
     'descripcion': 'Sube la postura defensiva del nodo, atrae sondas enemigas y aumenta la precisión del detector.',
     'comandoEjemplo': 'docker run -d --name decoy-srv -p 8080:80 cowrie/honeypot'},
    {'id': 'bloquear_ip', 'nombre': 'Bloquear origen atacante',
     'descripcion': 'Aplica reglas de firewall eBPF/iptables para descartar paquetes de la IP hostil.',
     'comandoEjemplo': 'iptables -A INPUT -s {attacker_ip} -j DROP'},
    {'id': 'parchear_vuln', 'nombre': 'Parchear CVEs y vulnerabilidades (Hotfix)',
     'descripcion': 'Aplica parches de seguridad de emergencia en el software del nodo, remediando CVEs críticos.',
     'comandoEjemplo': 'apt-get --only-upgrade install log4j openssl -y && systemctl restart app'},
    {'id': 'yara_memory_scan', 'nombre': 'Threat Hunting & Escaneo YARA en memoria',
     'descripcion': 'Escanea procesos y memoria RAM con reglas YARA para detectar web shells y beacons C2 sin tirar el servicio.',
     'comandoEjemplo': 'yara -s -r /etc/yara/c2_beacons.yar /proc/*/mem'},
    {'id': 'canary_token', 'nombre': 'Plantar HoneyToken / Trampa canaria',
     'descripcion': 'Siembra credenciales y tokens señuelo en archivos del host para delatar sondas hostiles.',
     'comandoEjemplo': 'canary-deploy --token aws_key --output /home/user/.aws/credentials'},
    {'id': 'rotate_keys', 'nombre': 'Rotación de llaves SSH y tickets Kerberos',
     'descripcion': 'Invalida claves SSH autorizadas y revoca tickets Kerberos TGT para cortar movimientos laterales.',
     'comandoEjemplo': 'kadmin.local -q "cpw -randkey krbtgt/CORP" && shred -u ~/.ssh/authorized_keys'},
]

RESPUESTA_POR_ID = {r['id']: r for r in RESPUESTAS}


def aplicar_respuesta(nodos: list, kind: str, nodo_id: str, tick: int) -> dict:
    """Devuelve {'evento': ..., 'penalizaDisponibilidad': float}."""
    n = next((x for x in nodos if x['id'] == nodo_id), None)

    def ev(texto):
        return {'tick': tick, 'id': f'r{tick}-{nodo_id}', 'tipo': 'respuesta',
                'lado': 'defender', 'nodoId': nodo_id, 'texto': texto}

    if not n:
        return {'evento': ev('Respuesta a nodo inexistente'), 'penalizaDisponibilidad': 0}

    if kind == 'aislar':
        sano = (not n['compromisoReal']) and n['estado'] != 'sondeado'
        n['estado'] = 'aislado'
        n['aisladoHasta'] = tick + DURACION_AISLAMIENTO
        costo = n['valor'] * 0.05 + (n['valor'] * 0.15 if sano else 0)
        return {'evento': ev(f"Nodo {n['nombre']} AISLADO en cuarentena eBPF por {DURACION_AISLAMIENTO} ticks"),
                'penalizaDisponibilidad': costo}

    if kind == 'terminar_proceso':
        if n['fase'] and n['compromisoReal']:
            i = fase_index(n['fase'])
            n['fase'] = ORDEN_FASE[i - 1] if i > 0 else None
            if not n['fase']:
                n['compromisoReal'] = False
                n['estado'] = 'limpio'
            return {'evento': ev(f"Proceso malicioso terminado en {n['nombre']}: retrocede a {n['fase'] or 'limpio'}"),
                    'penalizaDisponibilidad': 0}
        return {'evento': ev(f"Terminar proceso en {n['nombre']}: sin proceso hostil activo"),
                'penalizaDisponibilidad': 0.05}

    if kind == 'parchear_env':
        n['posturaDefensiva'] = min(1, n['posturaDefensiva'] + 0.35)
        if n['senales'].get('s_recon'):
            n['senales']['s_recon'] *= 0.3
        if n['senales'].get('s_tecnica'):
            n['senales']['s_tecnica'] *= 0.5
        if n['fase'] == 'recon':
            n['fase'] = None
            n['estado'] = 'limpio'
        return {'evento': ev(f"Secretos/.env saneados y credenciales rotadas en {n['nombre']} (postura +35%)"),
                'penalizaDisponibilidad': 0.01}

    if kind == 'honeypot':
        n['posturaDefensiva'] = min(1, n['posturaDefensiva'] + 0.5)
        return {'evento': ev(f"Honeypot desplegado junto a {n['nombre']} (postura defensiva +50%)"),
                'penalizaDisponibilidad': 0}

    if kind == 'bloquear_ip':
        n['senales']['s_reputacion'] = 0
        n['posturaDefensiva'] = min(1, n['posturaDefensiva'] + 0.2)
        return {'evento': ev(f"Origen hostil bloqueado en firewall para {n['nombre']}"),
                'penalizaDisponibilidad': 0.03}

    if kind == 'parchear_vuln':
        for v in n.get('vulnerabilidades', []):
            v['dificultad'] = min(0.95, v.get('dificultad', 0.5) + 0.4)
        n['posturaDefensiva'] = min(1, n['posturaDefensiva'] + 0.35)
        if n['senales'].get('s_tecnica'):
            n['senales']['s_tecnica'] *= 0.3
        return {'evento': ev(f"Parches de seguridad aplicados en {n['nombre']}: CVEs mitigados (postura +35%)"),
                'penalizaDisponibilidad': 0.02}

    if kind == 'yara_memory_scan':
        if n['fase'] == 'escalada' and n['compromisoReal']:
            n['fase'] = 'acceso_inicial'
            if n['senales'].get('s_tecnica'):
                n['senales']['s_tecnica'] *= 0.2
            n['score'] *= 0.5
            return {'evento': ev(f"YARA Memory Hunt en {n['nombre']}: [MATCH] Beacon/Webshell neutralizado. Permisos revertidos."),
                    'penalizaDisponibilidad': 0}
        n['score'] *= 0.7
        return {'evento': ev(f"YARA Memory Hunt en {n['nombre']}: Telemetría limpia, 0 anomalías residentes."),
                'penalizaDisponibilidad': 0}

    if kind == 'canary_token':
        n['posturaDefensiva'] = min(1, n['posturaDefensiva'] + 0.4)
        n['senales']['s_canary'] = 0.8
        return {'evento': ev(f"HoneyToken señuelo desplegado en {n['nombre']} (postura +40%)"),
                'penalizaDisponibilidad': 0}

    if kind == 'rotate_keys':
        n['senales']['s_reputacion'] = 0
        if n['senales'].get('s_recon'):
            n['senales']['s_recon'] *= 0.3
        n['posturaDefensiva'] = min(1, n['posturaDefensiva'] + 0.25)
        return {'evento': ev(f"Llaves SSH y tickets Kerberos revocados en {n['nombre']} (postura +25%)"),
                'penalizaDisponibilidad': 0.01}

    return {'evento': ev('Respuesta desconocida'), 'penalizaDisponibilidad': 0}

