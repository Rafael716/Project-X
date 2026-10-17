import type { SimNode, ResponseKind, ResponseMeta, GameEvent } from '../../shared/protocol';
import { faseIndex, ORDEN_FASE } from './techniques';

// El aislamiento es temporal: mantener un host offline no es gratis (doc 06 §6).
export const DURACION_AISLAMIENTO = 24; // ticks que el nodo queda offline antes de volver

export const RESPUESTAS: ResponseMeta[] = [
  { id: 'aislar', nombre: 'Aislar nodo (Cuarentena)', descripcion: 'Corta la conectividad de red del host. Detiene ataques de inmediato pero degrada la disponibilidad si es un FP.', comandoEjemplo: 'tc qdisc add dev eth0 root netem loss 100% # o eBPF xdp drop' },
  { id: 'terminar_proceso', nombre: 'Terminar proceso (SIGKILL)', descripcion: 'Mata el proceso/reverse shell sospechoso y revierte la kill chain al estado previo.', comandoEjemplo: 'ebpf_kill -pid $(pgrep -f "sh|nc|beacon") -9' },
  { id: 'parchear_env', nombre: 'Parchear .env y rotar secretos', descripcion: 'Sanea variables .env, revoca tokens y restringe acceso a documentos confidenciales.', comandoEjemplo: 'vault-rotate --env /app/.env && chmod 600 *.env *.docx' },
  { id: 'honeypot', nombre: 'Desplegar honeypot / señuelo', descripcion: 'Sube la postura defensiva del nodo, atrae sondas enemigas y aumenta la precisión del detector.', comandoEjemplo: 'docker run -d --name decoy-srv -p 8080:80 cowrie/honeypot' },
  { id: 'bloquear_ip', nombre: 'Bloquear origen atacante', descripcion: 'Aplica reglas de firewall eBPF/iptables para descartar paquetes de la IP hostil.', comandoEjemplo: 'iptables -A INPUT -s {attacker_ip} -j DROP' },
  { id: 'parchear_vuln', nombre: 'Parchear CVEs y vulnerabilidades (Hotfix)', descripcion: 'Aplica parches de seguridad de emergencia en el software del nodo, remediando CVEs críticos.', comandoEjemplo: 'apt-get --only-upgrade install log4j openssl -y && systemctl restart app' },
  { id: 'yara_memory_scan', nombre: 'Threat Hunting & Escaneo YARA en memoria', descripcion: 'Escanea procesos y memoria RAM con reglas YARA para detectar web shells y beacons C2 sin tirar el servicio.', comandoEjemplo: 'yara -s -r /etc/yara/c2_beacons.yar /proc/*/mem' },
  { id: 'canary_token', nombre: 'Plantar HoneyToken / Trampa canaria', descripcion: 'Siembra credenciales y tokens señuelo en archivos del host para delatar sondas hostiles.', comandoEjemplo: 'canary-deploy --token aws_key --output /home/user/.aws/credentials' },
  { id: 'rotate_keys', nombre: 'Rotación de llaves SSH y tickets Kerberos', descripcion: 'Invalida claves SSH autorizadas y revoca tickets Kerberos TGT para cortar movimientos laterales.', comandoEjemplo: 'kadmin.local -q "cpw -randkey krbtgt/CORP" && shred -u ~/.ssh/authorized_keys' },
];

export interface RespResult { evento: GameEvent; penalizaDisponibilidad: number; }

// Aplica una respuesta. Devuelve el evento y cuánta disponibilidad penaliza (FP, RF-33).
export function aplicarRespuesta(
  nodos: SimNode[], kind: ResponseKind, nodoId: string, tick: number,
): RespResult {
  const n = nodos.find(x => x.id === nodoId);
  const ev = (texto: string): GameEvent => ({ tick, id: `r${tick}-${nodoId}`, tipo: 'respuesta', lado: 'defender', nodoId, texto });
  if (!n) return { evento: ev('Respuesta a nodo inexistente'), penalizaDisponibilidad: 0 };

  switch (kind) {
    case 'aislar': {
      const sano = !n.compromisoReal && n.estado !== 'sondeado';
      n.estado = 'aislado';
      n.aisladoHasta = tick + DURACION_AISLAMIENTO;
      // Costo base por disrupción del servicio (todo host offline molesta) + extra si era sano (FP).
      const costo = n.valor * 0.05 + (sano ? n.valor * 0.15 : 0);
      return { evento: ev(`Nodo ${n.nombre} AISLADO en cuarentena eBPF por ${DURACION_AISLAMIENTO} ticks`), penalizaDisponibilidad: costo };
    }
    case 'terminar_proceso': {
      if (n.fase && n.compromisoReal) {
        const i = faseIndex(n.fase);
        n.fase = i > 0 ? ORDEN_FASE[i - 1] : null;
        if (!n.fase) { n.compromisoReal = false; n.estado = 'limpio'; }
        return { evento: ev(`Proceso malicioso terminado en ${n.nombre}: retrocede a ${n.fase ?? 'limpio'}`), penalizaDisponibilidad: 0 };
      }
      return { evento: ev(`Terminar proceso en ${n.nombre}: sin proceso hostil activo`), penalizaDisponibilidad: 0.05 };
    }
    case 'parchear_env': {
      n.posturaDefensiva = Math.min(1, n.posturaDefensiva + 0.35);
      if (n.senales['s_recon']) n.senales['s_recon'] *= 0.3;
      if (n.senales['s_tecnica']) n.senales['s_tecnica'] *= 0.5;
      if (n.fase === 'recon') {
        n.fase = null;
        n.estado = 'limpio';
      }
      return { evento: ev(`Secretos/.env saneados y credenciales rotadas en ${n.nombre} (postura +35%)`), penalizaDisponibilidad: 0.01 };
    }
    case 'honeypot': {
      n.posturaDefensiva = Math.min(1, n.posturaDefensiva + 0.5);
      return { evento: ev(`Honeypot desplegado junto a ${n.nombre} (postura defensiva +50%)`), penalizaDisponibilidad: 0 };
    }
    case 'bloquear_ip': {
      n.senales['s_reputacion'] = 0;
      n.posturaDefensiva = Math.min(1, n.posturaDefensiva + 0.2);
      return { evento: ev(`Origen hostil bloqueado en firewall para ${n.nombre}`), penalizaDisponibilidad: 0.03 };
    }
    case 'parchear_vuln': {
      for (const v of n.vulnerabilidades) {
        v.dificultad = Math.min(0.95, v.dificultad + 0.4);
      }
      n.posturaDefensiva = Math.min(1, n.posturaDefensiva + 0.35);
      if (n.senales['s_tecnica']) n.senales['s_tecnica'] *= 0.3;
      return { evento: ev(`Parches de seguridad aplicados en ${n.nombre}: CVEs mitigados (postura +35%)`), penalizaDisponibilidad: 0.02 };
    }
    case 'yara_memory_scan': {
      if (n.fase === 'escalada' && n.compromisoReal) {
        n.fase = 'acceso_inicial';
        if (n.senales['s_tecnica']) n.senales['s_tecnica'] *= 0.2;
        n.score *= 0.5;
        return { evento: ev(`YARA Memory Hunt en ${n.nombre}: [MATCH] Beacon/Webshell neutralizado. Permisos revertidos.`), penalizaDisponibilidad: 0 };
      }
      n.score *= 0.7;
      return { evento: ev(`YARA Memory Hunt en ${n.nombre}: Telemetría limpia, 0 anomalías residentes.`), penalizaDisponibilidad: 0 };
    }
    case 'canary_token': {
      n.posturaDefensiva = Math.min(1, n.posturaDefensiva + 0.4);
      n.senales['s_canary'] = 0.8;
      return { evento: ev(`HoneyToken señuelo desplegado en ${n.nombre} (postura +40%)`), penalizaDisponibilidad: 0 };
    }
    case 'rotate_keys': {
      n.senales['s_reputacion'] = 0;
      if (n.senales['s_recon']) n.senales['s_recon'] *= 0.3;
      n.posturaDefensiva = Math.min(1, n.posturaDefensiva + 0.25);
      return { evento: ev(`Llaves SSH y tickets Kerberos revocados en ${n.nombre} (postura +25%)`), penalizaDisponibilidad: 0.01 };
    }
  }
}
