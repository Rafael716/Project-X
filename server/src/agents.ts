import type { AgentThought } from '../../shared/protocol';
import { Engine, AttackIntent, RespondIntent } from './engine';
import { TECNICAS, faseIndex } from './techniques';

// Bucle ReAct: observar -> razonar -> actuar. ADR-0006.
// Política por defecto HEURÍSTICA y determinista (usa engine.rng para desempates).
// Para "subir de nivel" a un LLM, implementar esta misma firma y enchufarla en match.ts.
export interface AttackerPolicy { decidir(e: Engine): { intent: AttackIntent | null; thought: AgentThought }; }
export interface DefenderPolicy { decidir(e: Engine): { intent: RespondIntent | null; thought: AgentThought }; }

// -------- Atacante heurístico: avanza la kill chain hacia el objetivo y saquea .env / docs --------
export const atacanteHeuristico: AttackerPolicy = {
  decidir(e) {
    const ruta = e.rutaAObjetivo();
    const opciones: { intent: AttackIntent; prioridad: number; nombre: string; razon: string }[] = [];

    for (const n of e.nodos) {
      for (const t of TECNICAS) {
        const intent = { tecnicaId: t.id, nodoId: n.id };
        if (e.validarAtaque(intent)) continue;

        let p = (faseIndex(t.faseProduce) + 1) + 2 * e.probExito(t.id, n);
        let razon = `Avanzar fase con éxito ${(e.probExito(t.id, n) * 100).toFixed(0)}%`;

        if (t.id === 'exfil') {
          p += 14;
          razon = `Objetivo cumbre: exfiltrar base de datos y archivos críticos de ${n.nombre}`;
        } else if (t.id === 'sqli_dump') {
          const hasSqliLoot = e.loot.some(l => l.nodoId === n.id && l.item.includes('sqli_dump'));
          p += hasSqliLoot ? -2 : 8.5;
          razon = `Inyección SQL en ${n.nombre} para sustraer tablas confidenciales y credenciales`;
        } else if (t.id === 'dump_lsass') {
          const hasLsassLoot = e.loot.some(l => l.nodoId === n.id && l.item.includes('lsass_hashes'));
          p += hasLsassLoot ? -3 : 8.0;
          razon = `Volcado de memoria LSASS con Mimikatz en ${n.nombre} para extraer hashes NTLM de dominio`;
        } else if (t.id === 'persist_backdoor') {
          p += 6.0;
          razon = `Instalar persistencia (WebShell + Cron) en ${n.nombre} para blindar el acceso C2`;
        } else if (t.id === 'phishing_spray') {
          p += 5.5;
          razon = `Rociado de credenciales / Pass-the-Hash contra servicios expuestos de ${n.nombre}`;
        } else if (t.id === 'scan_docs') {
          // Búsqueda a fondo de .env, claves y documentos
          const archivosPendientes = (n.archivosSensibles ?? []).filter(s => !e.loot.some(l => l.nodoId === n.id && l.item === s));
          if (archivosPendientes.length > 0) {
            p += 7.0;
            razon = `Descubrir y volcar ${archivosPendientes.length} archivos (.env / credenciales / docs) en ${n.nombre}`;
          } else {
            p -= 4; // Ya saqueado
          }
        } else if (t.id === 'pivot') {
          p += 5.5;
          razon = `Pivote lateral e infiltración hacia nodo adyacente ${n.nombre}`;
        } else if (t.id === 'privesc') {
          p += 5.0;
          razon = `Escalar privilegios a ROOT/SYSTEM en ${n.nombre}`;
        }

        const idx = ruta.indexOf(n.id);
        if (idx >= 0) p += 6 + idx;
        else p -= 5;

        p -= ({ bajo: 0, medio: 0.3, alto: 0.6 } as const)[t.ruido];
        opciones.push({ intent, prioridad: p, nombre: `${t.nombre} → ${n.nombre}`, razon });
      }
    }

    opciones.sort((a, b) => b.prioridad - a.prioridad);
    const base = { tick: e.tick, lado: 'attacker' as const };

    if (opciones.length === 0) {
      const th = { ...base, observacion: 'Sin jugadas viables inmediatas (red contenida o aislada).', razonamiento: 'Reevaluando topología y aguardando que expire algún aislamiento.', accion: 'reconectar_c2' };
      e.pensar(th);
      return { intent: null, thought: th };
    }

    const elegido = opciones[0];
    const th: AgentThought = {
      ...base,
      observacion: `${opciones.length} vectores viables identificados; objetivo: ${e.nodoNombre(e.objetivo)}. Archivos capturados: ${e.loot.length}.`,
      razonamiento: `${elegido.razon}. Prioridad: ${elegido.prioridad.toFixed(1)} (bajo ruido / alto impacto).`,
      accion: elegido.nombre,
    };
    e.pensar(th);
    return { intent: elegido.intent, thought: th };
  },
};

// -------- Defensor heurístico: respuesta proactiva multicapa (SOC Senior) --------
export const defensorHeuristico: DefenderPolicy = {
  decidir(e) {
    const base = { tick: e.tick, lado: 'defender' as const };
    const activos = e.nodos.filter(n => n.estado !== 'aislado');

    // 1. Detección de nodos con compromiso crítico o exfiltración inminente
    const critico = activos.find(n => n.compromisoReal && (n.fase === 'escalada' || n.fase === 'exfiltracion' || n.score > 0.88));
    if (critico) {
      let resp: RespondIntent;
      let motivo: string;
      if (critico.score > 0.92 || critico.fase === 'exfiltracion') {
        resp = { respuesta: 'aislar', nodoId: critico.id };
        motivo = 'Riesgo inminente de robo de base de datos → Cuarentena eBPF inmediata para aislar el host.';
      } else if (critico.fase === 'escalada') {
        resp = { respuesta: 'yara_memory_scan', nodoId: critico.id };
        motivo = 'Proceso o backdoor con privilegios detectado → Ejecutando escaneo YARA en memoria para purgar beacons sin disrupción.';
      } else {
        resp = { respuesta: 'terminar_proceso', nodoId: critico.id };
        motivo = 'Proceso malicioso activo detectado → Ejecutando SIGKILL para expulsar al atacante.';
      }

      const th: AgentThought = {
        ...base,
        observacion: `AMENAZA CRÍTICA en ${critico.nombre} (score ${(critico.score * 100).toFixed(0)}%, fase: ${critico.fase ?? 'activa'}).`,
        razonamiento: motivo,
        accion: `${resp.respuesta} → ${critico.nombre}`,
      };
      e.pensar(th);
      return { intent: resp, thought: th };
    }

    // 2. Detección de robo de .env / documentos o reconocimiento anómalo
    const sospechosoRecon = activos.find(n => (n.senales['s_recon'] ?? 0) > 0.35 || (n.senales['s_tecnica'] ?? 0) > 0.4 || n.fase === 'recon');
    if (sospechosoRecon && sospechosoRecon.score > 0.45) {
      const resp: RespondIntent = (sospechosoRecon.senales['s_reputacion'] ?? 0) > 0.3
        ? { respuesta: 'rotate_keys', nodoId: sospechosoRecon.id }
        : { respuesta: 'parchear_env', nodoId: sospechosoRecon.id };
      const th: AgentThought = {
        ...base,
        observacion: `Sondeo o filtración detectada en ${sospechosoRecon.nombre} (s_recon: ${(sospechosoRecon.senales['s_recon'] ?? 0).toFixed(2)}).`,
        razonamiento: resp.respuesta === 'rotate_keys'
          ? 'Sondeo o pass-the-hash sospechoso → Revocando claves SSH y tickets Kerberos expuestos.'
          : 'Rotando credenciales expuestas y securizando variables .env y documentos con zero downtime.',
        accion: `${resp.respuesta} → ${sospechosoRecon.nombre}`,
      };
      e.pensar(th);
      return { intent: resp, thought: th };
    }

    // 3. Proactividad: Parcheo de vulnerabilidades o despliegue de HoneyTokens
    const vulnerable = activos.find(n => n.posturaDefensiva < 0.4 && n.vulnerabilidades.some(v => v.dificultad < 0.65));
    if (vulnerable && e.tick % 4 === 0) {
      const resp: RespondIntent = { respuesta: 'parchear_vuln', nodoId: vulnerable.id };
      const th: AgentThought = {
        ...base,
        observacion: `Vulnerabilidades conocidas sin parchear en ${vulnerable.nombre} (resistencia baja).`,
        razonamiento: 'Aplicando hotfix preventivo de seguridad para inmunizar el host frente a exploits RCE remotos.',
        accion: `parchear_vuln → ${vulnerable.nombre}`,
      };
      e.pensar(th);
      return { intent: resp, thought: th };
    }

    // 4. Nodos con score de anomalía por encima de umbral moderado
    const peor = activos.slice().sort((a, b) => b.score - a.score)[0];
    if (peor && peor.score >= 0.55) {
      let resp: RespondIntent;
      let por: string;
      if (peor.fase && peor.compromisoReal) {
        resp = { respuesta: 'terminar_proceso', nodoId: peor.id };
        por = 'Proceso malicioso detectado en host comprometido → forzando terminación de sesión.';
      } else if (peor.posturaDefensiva < 0.35) {
        resp = { respuesta: 'canary_token', nodoId: peor.id };
        por = 'Anomalía moderada → sembrando HoneyTokens de alta fidelidad para tender una trampa canaria.';
      } else if (peor.posturaDefensiva < 0.6) {
        resp = { respuesta: 'honeypot', nodoId: peor.id };
        por = 'Anomalía moderada → desplegando contenedor honeypot señuelo para desviar sondas.';
      } else {
        resp = { respuesta: 'bloquear_ip', nodoId: peor.id };
        por = 'Filtro de reputación perimetral → bloqueando IP atacante en firewall XDP.';
      }

      const th: AgentThought = {
        ...base,
        observacion: `${peor.nombre} con anomalía ${(peor.score * 100).toFixed(0)}% (señales: ${Object.keys(peor.senales).join(', ')}).`,
        razonamiento: por,
        accion: `${resp.respuesta} → ${peor.nombre}`,
      };
      e.pensar(th);
      return { intent: resp, thought: th };
    }

    // Estado seguro bajo umbral
    const maxScore = peor ? peor.score : 0;
    const th: AgentThought = {
      ...base,
      observacion: `Topología estable. Score máximo en red: ${(maxScore * 100).toFixed(0)}%. Telemetría eBPF normal.`,
      razonamiento: 'Anomalías bajo umbral de intervención. No se aplican contramedidas para preservar el 100% de disponibilidad.',
      accion: 'vigilar_red',
    };
    e.pensar(th);
    return { intent: null, thought: th };
  },
};
