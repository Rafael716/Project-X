"""Agentes ReAct heurísticos (observar -> razonar -> actuar). ADR-0006.

Política determinista y sembrada. Cada agente implementa `decidir(e) -> (intent, pensamiento)`.
En match.py se envuelven con `PoliticaResiliente` (Sesión 7): si la política
primaria fallara o tardara, el proxy degrada a una política mínima sin congelar
el tick — el "Proxy de Resiliencia" de la diapositiva de la PC2.
"""

from techniques import TECNICA_POR_ID, fase_index

_RUIDO_PEN = {'bajo': 0, 'medio': 0.3, 'alto': 0.6}


def _asequible(e, lado, costo):
    return e.energia[lado] >= costo


def atacante_decidir(e):
    ruta = e.ruta_a_objetivo()
    base = {'tick': e.tick, 'lado': 'attacker'}
    opciones = []
    for n in e.nodos:
        for t in TECNICA_POR_ID.values():
            intent = {'tecnicaId': t.id, 'nodoId': n['id']}
            if e.validar_ataque(intent):
                continue
            pexito = e.prob_exito(t.id, n)
            p = (fase_index(t.faseProduce) + 1) + 2 * pexito
            razon = f"Avanzar en {n['nombre']} ({round(pexito * 100)}% de que funcione)"

            if t.id == 'exfil':
                p += 14
                razon = f"¡A robar los datos de {n['nombre']}! Es lo que me hace ganar."
            elif t.id == 'sqli_dump':
                repetido = any(l['nodoId'] == n['id'] and 'sqli_dump' in l['item'] for l in e.loot)
                p += -2 if repetido else 8.5
                razon = f"Robar la base de datos de {n['nombre']} (tablas y contraseñas)"
            elif t.id == 'dump_lsass':
                repetido = any(l['nodoId'] == n['id'] and 'lsass_hashes' in l['item'] for l in e.loot)
                p += -3 if repetido else 8.0
                razon = f"Robar las contraseñas guardadas en {n['nombre']}"
            elif t.id == 'persist_backdoor':
                p += 6.0
                razon = f"Dejar una puerta trasera en {n['nombre']} para no perder el acceso"
            elif t.id == 'phishing_spray':
                p += 5.5
                razon = f"Probar contraseñas robadas en {n['nombre']}"
            elif t.id == 'scan_docs':
                pend = [s for s in (n.get('archivosSensibles') or [])
                        if not any(l['nodoId'] == n['id'] and l['item'] == s for l in e.loot)]
                p += 7.0 if pend else -4
                if pend:
                    razon = f"Buscar {len(pend)} archivos secretos en {n['nombre']}"
            elif t.id == 'pivot':
                p += 5.5
                razon = f"Saltar a {n['nombre']} desde una PC vecina"
            elif t.id == 'privesc':
                p += 5.0
                razon = f"Volverme administrador de {n['nombre']}"

            # Conquista total: el objetivo es quedarse con TODAS las máquinas, así
            # que tomar una máquina que aún no es suya vale mucho (aunque no esté
            # en la ruta directa al objetivo).
            if not n['compromisoReal'] and fase_index(t.faseProduce) >= fase_index('acceso_inicial'):
                p += 9

            idx = ruta.index(n['id']) if n['id'] in ruta else -1
            p += (6 + idx) if idx >= 0 else -1   # las de fuera de ruta ya no se entierran
            p -= _RUIDO_PEN[t.ruido]
            if not _asequible(e, 'attacker', t.costo):
                p -= 100   # no puede pagarla ahora: al fondo de la lista
            opciones.append({'intent': intent, 'prioridad': p, 'nombre': f"{t.nombre} → {n['nombre']}", 'razon': razon, 'costo': t.costo})

    opciones = [o for o in opciones if _asequible(e, 'attacker', o['costo'])]
    opciones.sort(key=lambda o: o['prioridad'], reverse=True)

    if not opciones:
        th = {**base, 'observacion': f"Me quedé sin energía ({e.energia['attacker']}/{e.ENERGIA_MAX}).",
              'razonamiento': 'Espero a que se recargue y vuelvo a mirar el mapa.', 'accion': 'recargar energía'}
        e.pensar(th)
        return None, th

    elegido = opciones[0]
    th = {**base,
          'observacion': f"Tengo {len(opciones)} jugadas posibles. Quiero llegar a {e.nodo_nombre(e.objetivo)}. Cosas robadas: {len(e.loot)}. Energía {e.energia['attacker']}/{e.ENERGIA_MAX}.",
          'razonamiento': elegido['razon'],
          'accion': elegido['nombre']}
    e.pensar(th)
    return elegido['intent'], th


def _puede_def(e, respuesta, costo):
    return _asequible(e, 'defender', costo)


def defensor_decidir(e):
    from response import RESPUESTA_POR_ID
    base = {'tick': e.tick, 'lado': 'defender'}
    activos = [n for n in e.nodos if n['estado'] != 'aislado']

    def resp_costo(rid):
        r = RESPUESTA_POR_ID.get(rid)
        return r.costo if r else 99

    def emitir(rid, nodo, obs, razon):
        r = RESPUESTA_POR_ID.get(rid)
        nombre_accion = f"{r.nombre} → {nodo['nombre']}" if r else f"{rid} → {nodo['nombre']}"
        th = {**base, 'observacion': obs, 'razonamiento': razon, 'accion': nombre_accion}
        e.pensar(th)
        return {'respuesta': rid, 'nodoId': nodo['id']}, th

    # 1. Compromiso crítico / exfiltración inminente
    critico = next((n for n in activos if n['compromisoReal'] and (n['fase'] in ('escalada', 'exfiltracion') or n['score'] > 0.88)), None)
    if critico and _puede_def(e, 'aislar', resp_costo('aislar')):
        if critico['score'] > 0.92 or critico['fase'] == 'exfiltracion':
            return emitir('aislar', critico, f"¡Peligro! {critico['nombre']} está muy comprometida ({round(critico['score']*100)}%).",
                          'Lo desconecto ya para frenar el robo de datos.')
        if critico.get('persistente') or critico['fase'] == 'escalada':
            if _puede_def(e, 'yara_memory_scan', resp_costo('yara_memory_scan')):
                return emitir('yara_memory_scan', critico, f"Parece que dejaron una puerta trasera en {critico['nombre']}.",
                              'Reviso la memoria para quitarla.')
        if _puede_def(e, 'terminar_proceso', resp_costo('terminar_proceso')):
            return emitir('terminar_proceso', critico, f"Hay un programa malicioso activo en {critico['nombre']}.",
                          'Lo cierro para echar al atacante.')

    # 2. Reconocimiento / fuga de .env
    sosp = next((n for n in activos if (n['senales'].get('s_recon', 0) > 0.35 or n['senales'].get('s_tecnica', 0) > 0.4 or n['fase'] == 'recon')), None)
    if sosp and sosp['score'] > 0.45:
        if sosp['senales'].get('s_reputacion', 0) > 0.3 and _puede_def(e, 'rotate_keys', resp_costo('rotate_keys')):
            return emitir('rotate_keys', sosp, f"Alguien está usando contraseñas robadas en {sosp['nombre']}.",
                          'Cambio las llaves de acceso para cortarle el paso.')
        if _puede_def(e, 'parchear_env', resp_costo('parchear_env')):
            return emitir('parchear_env', sosp, f"Están husmeando {sosp['nombre']} buscando archivos y contraseñas.",
                          'Cambio las contraseñas y limpio la configuración.')

    # 3. Parcheo preventivo
    vuln = next((n for n in activos if n['posturaDefensiva'] < 0.4 and any(v['dificultad'] < 0.65 for v in n['vulnerabilidades'])), None)
    if vuln and e.tick % 4 == 0 and _puede_def(e, 'parchear_vuln', resp_costo('parchear_vuln')):
        return emitir('parchear_vuln', vuln, f"{vuln['nombre']} tiene fallas sin reparar.",
                      'Las reparo antes de que el atacante las aproveche.')

    # 4. Anomalía moderada
    peor = max(activos, key=lambda n: n['score']) if activos else None
    if peor and peor['score'] >= 0.55:
        if peor['fase'] and peor['compromisoReal'] and _puede_def(e, 'terminar_proceso', resp_costo('terminar_proceso')):
            return emitir('terminar_proceso', peor, f"{peor['nombre']} está comprometida ({round(peor['score']*100)}%).",
                          'Cierro el programa malicioso.')
        if peor['posturaDefensiva'] < 0.35 and _puede_def(e, 'canary_token', resp_costo('canary_token')):
            return emitir('canary_token', peor, f"Actividad rara en {peor['nombre']} ({round(peor['score']*100)}%).",
                          'Pongo un cebo para pillar al atacante.')
        if _puede_def(e, 'honeypot', resp_costo('honeypot')):
            return emitir('honeypot', peor, f"Actividad rara en {peor['nombre']} ({round(peor['score']*100)}%).",
                          'Pongo una trampa al lado para despistarlo.')
        if _puede_def(e, 'bloquear_ip', resp_costo('bloquear_ip')):
            return emitir('bloquear_ip', peor, f"Conexión sospechosa hacia {peor['nombre']}.",
                          'Bloqueo al atacante.')

    max_score = peor['score'] if peor else 0
    th = {**base, 'observacion': f"Todo tranquilo. Lo más raro está al {round(max_score*100)}%. Energía {e.energia['defender']}/{e.ENERGIA_MAX}.",
          'razonamiento': 'Sin amenazas serias: cuido que la red siga funcionando y junto energía.', 'accion': 'vigilar la red'}
    e.pensar(th)
    return None, th


class _Politica:
    def __init__(self, fn):
        self._fn = fn

    def decidir(self, e):
        return self._fn(e)


class _Minima:
    """Política de respaldo del proxy de resiliencia: 1 jugada barata y segura."""

    def __init__(self, lado):
        self.lado = lado

    def decidir(self, e):
        th = {'tick': e.tick, 'lado': self.lado,
              'observacion': 'Modo de respaldo activo.',
              'razonamiento': 'Juego seguro un momento mientras el agente principal se recupera.',
              'accion': 'esperar'}
        return None, th


atacante_heuristico = _Politica(atacante_decidir)
defensor_heuristico = _Politica(defensor_decidir)
atacante_minimo = _Minima('attacker')
defensor_minimo = _Minima('defender')
