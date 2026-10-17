"""Agentes ReAct heurísticos (observar -> razonar -> actuar). ADR-0006.
Port de agents.ts. Política determinista; hook LLM posible reemplazando decidir()."""

from techniques import TECNICAS, fase_index

_RUIDO_PEN = {'bajo': 0, 'medio': 0.3, 'alto': 0.6}


def atacante_decidir(e):
    ruta = e.ruta_a_objetivo()
    opciones = []
    for n in e.nodos:
        for t in TECNICAS:
            intent = {'tecnicaId': t['id'], 'nodoId': n['id']}
            if e.validar_ataque(intent):
                continue
            pexito = e.prob_exito(t['id'], n)
            p = (fase_index(t['faseProduce']) + 1) + 2 * pexito
            razon = f"Avanzar fase con éxito {round(pexito * 100)}%"

            if t['id'] == 'exfil':
                p += 14
                razon = f"Objetivo cumbre: exfiltrar base de datos y archivos críticos de {n['nombre']}"
            elif t['id'] == 'sqli_dump':
                has_sqli_loot = any(l['nodoId'] == n['id'] and 'sqli_dump' in l['item'] for l in e.loot)
                p += 8.5 if not has_sqli_loot else -2
                razon = f"Inyección SQL en {n['nombre']} para sustraer tablas confidenciales y credenciales"
            elif t['id'] == 'dump_lsass':
                has_lsass_loot = any(l['nodoId'] == n['id'] and 'lsass_hashes' in l['item'] for l in e.loot)
                p += 8.0 if not has_lsass_loot else -3
                razon = f"Volcado de memoria LSASS con Mimikatz en {n['nombre']} para extraer hashes NTLM de dominio"
            elif t['id'] == 'persist_backdoor':
                p += 6.0 if not n.get('persistente') else -4
                razon = f"Instalar persistencia (WebShell + Cron) en {n['nombre']} para blindar el acceso C2"
            elif t['id'] == 'phishing_spray':
                p += 5.5
                razon = f"Rociado de credenciales / Pass-the-Hash contra servicios expuestos de {n['nombre']}"
            elif t['id'] == 'scan_docs':
                pendientes = [s for s in (n.get('archivosSensibles') or [])
                              if not any(l['nodoId'] == n['id'] and l['item'] == s for l in e.loot)]
                if pendientes:
                    p += 7.0
                    razon = f"Descubrir y volcar {len(pendientes)} archivos (.env / credenciales / docs) en {n['nombre']}"
                else:
                    p -= 4
            elif t['id'] == 'pivot':
                p += 5.5
                razon = f"Pivote lateral e infiltración hacia nodo adyacente {n['nombre']}"
            elif t['id'] == 'privesc':
                p += 5.0
                razon = f"Escalar privilegios a ROOT/SYSTEM en {n['nombre']}"

            idx = ruta.index(n['id']) if n['id'] in ruta else -1
            if idx >= 0:
                p += 6 + idx
            else:
                p -= 5
            p -= _RUIDO_PEN[t['ruido']]
            opciones.append({'intent': intent, 'prioridad': p, 'nombre': f"{t['nombre']} → {n['nombre']}", 'razon': razon})

    opciones.sort(key=lambda o: o['prioridad'], reverse=True)
    base = {'tick': e.tick, 'lado': 'attacker'}

    if not opciones:
        th = {**base, 'observacion': 'Sin jugadas viables inmediatas (red contenida o aislada).',
              'razonamiento': 'Reevaluando topología y aguardando que expire algún aislamiento.', 'accion': 'reconectar_c2'}
        e.pensar(th)
        return None, th

    elegido = opciones[0]
    th = {**base,
          'observacion': f"{len(opciones)} vectores viables identificados; objetivo: {e.nodo_nombre(e.objetivo)}. Archivos capturados: {len(e.loot)}.",
          'razonamiento': f"{elegido['razon']}. Prioridad: {elegido['prioridad']:.1f} (bajo ruido / alto impacto).",
          'accion': elegido['nombre']}
    e.pensar(th)
    return elegido['intent'], th


def defensor_decidir(e):
    base = {'tick': e.tick, 'lado': 'defender'}
    activos = [n for n in e.nodos if n['estado'] != 'aislado']

    # 1. Compromiso crítico o exfiltración inminente
    critico = next((n for n in activos if n['compromisoReal'] and (n['fase'] == 'escalada' or n['fase'] == 'exfiltracion' or n['score'] > 0.88)), None)
    if critico:
        if critico['score'] > 0.92 or critico['fase'] == 'exfiltracion':
            resp = {'respuesta': 'aislar', 'nodoId': critico['id']}
            motivo = 'Riesgo inminente de robo de base de datos → Cuarentena eBPF inmediata para aislar el host.'
        elif critico.get('persistente') or critico['fase'] == 'escalada':
            resp = {'respuesta': 'yara_memory_scan', 'nodoId': critico['id']}
            motivo = 'Proceso o backdoor con privilegios detectado → Ejecutando escaneo YARA en memoria para purgar beacons sin disrupción.'
        else:
            resp = {'respuesta': 'terminar_proceso', 'nodoId': critico['id']}
            motivo = 'Proceso malicioso activo detectado → Ejecutando SIGKILL para expulsar al atacante.'
        th = {**base,
              'observacion': f"AMENAZA CRÍTICA en {critico['nombre']} (score {round(critico['score']*100)}%, fase: {critico['fase'] or 'activa'}).",
              'razonamiento': motivo,
              'accion': f"{resp['respuesta']} → {critico['nombre']}"}
        e.pensar(th)
        return resp, th

    # 2. Robo de .env o rociado de credenciales / reconocimiento anómalo
    sospechoso = next((n for n in activos if (n['senales'].get('s_recon', 0) > 0.35 or n['senales'].get('s_tecnica', 0) > 0.4 or n['fase'] == 'recon')), None)
    if sospechoso and sospechoso['score'] > 0.45:
        if sospechoso['senales'].get('s_reputacion', 0) > 0.3:
            resp = {'respuesta': 'rotate_keys', 'nodoId': sospechoso['id']}
            motivo = 'Sondeo o pass-the-hash sospechoso → Revocando claves SSH y tickets Kerberos expuestos.'
        else:
            resp = {'respuesta': 'parchear_env', 'nodoId': sospechoso['id']}
            motivo = 'Sondeo o filtración de .env detectado → Rotando credenciales expuestas y securizando variables .env con zero downtime.'
        th = {**base,
              'observacion': f"Sondeo o filtración detectada en {sospechoso['nombre']} (s_recon: {sospechoso['senales'].get('s_recon', 0):.2f}).",
              'razonamiento': motivo,
              'accion': f"{resp['respuesta']} → {sospechoso['nombre']}"}
        e.pensar(th)
        return resp, th

    # 3. Proactividad: Parcheo de vulnerabilidades o despliegue de HoneyTokens
    vulnerable = next((n for n in activos if n['posturaDefensiva'] < 0.4 and any(v['dificultad'] < 0.65 for v in n.get('vulnerabilidades', []))), None)
    if vulnerable and e.tick % 4 == 0:
        resp = {'respuesta': 'parchear_vuln', 'nodoId': vulnerable['id']}
        th = {**base,
              'observacion': f"Vulnerabilidades conocidas sin parchear en {vulnerable['nombre']} (resistencia baja).",
              'razonamiento': 'Aplicando hotfix preventivo de seguridad para inmunizar el host frente a exploits RCE remotos.',
              'accion': f"parchear_vuln → {vulnerable['nombre']}"}
        e.pensar(th)
        return resp, th

    # 4. Score por encima de umbral moderado
    peor = sorted(activos, key=lambda n: n['score'], reverse=True)[0] if activos else None
    if peor and peor['score'] >= 0.55:
        if peor['fase'] and peor['compromisoReal']:
            resp = {'respuesta': 'terminar_proceso', 'nodoId': peor['id']}
            por = 'Proceso malicioso detectado en host comprometido → forzando terminación de sesión.'
        elif peor['posturaDefensiva'] < 0.35:
            resp = {'respuesta': 'canary_token', 'nodoId': peor['id']}
            por = 'Anomalía moderada → sembrando HoneyTokens de alta fidelidad para tender una trampa canaria.'
        elif peor['posturaDefensiva'] < 0.6:
            resp = {'respuesta': 'honeypot', 'nodoId': peor['id']}
            por = 'Anomalía moderada → desplegando contenedor honeypot señuelo para desviar sondas.'
        else:
            resp = {'respuesta': 'bloquear_ip', 'nodoId': peor['id']}
            por = 'Filtro de reputación perimetral → bloqueando IP atacante en firewall XDP.'
        th = {**base,
              'observacion': f"{peor['nombre']} con anomalía {round(peor['score']*100)}% (señales: {', '.join(peor['senales'].keys())}).",
              'razonamiento': por, 'accion': f"{resp['respuesta']} → {peor['nombre']}"}
        e.pensar(th)
        return resp, th

    max_score = peor['score'] if peor else 0
    th = {**base,
          'observacion': f"Topología estable. Score máximo en red: {round(max_score*100)}%. Telemetría eBPF normal.",
          'razonamiento': 'Anomalías bajo umbral de intervención. No se aplican contramedidas para preservar el 100% de disponibilidad.',
          'accion': 'vigilar_red'}
    e.pensar(th)
    return None, th


class Decision(tuple):
    def __new__(cls, intent, thought):
        return super().__new__(cls, (intent, thought))

    @property
    def intent(self):
        return self[0]

    @property
    def thought(self):
        return self[1]

    def __getitem__(self, item):
        if item == 'intent':
            return self[0]
        if item == 'thought':
            return self[1]
        return super().__getitem__(item)


class _AtacanteHeuristico:
    def decidir(self, e):
        intent, thought = atacante_decidir(e)
        return Decision(intent, thought)


class _DefensorHeuristico:
    def decidir(self, e):
        intent, thought = defensor_decidir(e)
        return Decision(intent, thought)


atacante_heuristico = _AtacanteHeuristico()
defensor_heuristico = _DefensorHeuristico()

