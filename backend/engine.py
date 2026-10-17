"""Motor de simulación autoritativo. Port de engine.ts.

Estado como dicts (coincide 1:1 con shared/protocol.ts para que el frontend
TypeScript lo consuma sin cambios)."""

from rng import Rng
from techniques import TECNICA_POR_ID, fase_index, ORDEN_FASE
from detector import Detector
from response import aplicar_respuesta, RESPUESTA_POR_ID

VENTANA = 60  # eventos/alertas recientes conservados para la UI


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


class Engine:
    def __init__(self, esc: dict, seed: int):
        self.esc = esc
        self.rng = Rng(seed)
        self.nodos = esc['nodos']  # ya es copia profunda (cargar_escenario)
        for n in self.nodos:
            n['senales'] = {}
        self.aristas = [dict(a) for a in esc['aristas']]
        self.eventos = []
        self.alertas = []
        self.pensamientos = []
        self.loot = []
        self.terminalLogs = []
        self.tick = 0
        self.tickMax = esc['tickMax']
        self.detector = Detector()
        self._firstMaliciousTick = None
        self._firstTrueAlertTick = None
        self._containmentTick = None
        self._penalDisponibilidad = 0
        self._datosExfiltrados = 0
        self._exfiltrados = set()
        self._metaExfiltracion = esc['metaExfiltracion']
        self._sumValor = sum(n['valor'] for n in self.nodos)
        self.objetivo = esc['objetivo']
        self._ruta = None

        self._log(tipo='sistema', texto=f"Escenario {esc['nombre']} cargado. Objetivo del atacante: exfiltrar {self.nodo_nombre(esc['objetivo'])}.")
        self.log_terminal('attacker', 'projectx-c2 --init --stealth-profile',
                          f"[+] C2 Console activada. Target network: {esc['nombre']} | Punto de entrada: {esc['entrada']} | Objetivo crítico: {self.nodo_nombre(esc['objetivo'])}", 'cmd')
        self.log_terminal('defender', 'systemctl status ebpf-soc-daemon',
                          "[+] SOC SecOps activo. Monitores eBPF/XDP desplegados. Analizador de grafos TGNN en escucha.", 'cmd')

    # --------- consultas ----------
    def nodo(self, nid):
        return next((n for n in self.nodos if n['id'] == nid), None)

    def nodo_nombre(self, nid):
        n = self.nodo(nid)
        return n['nombre'] if n else nid

    def adyacentes(self, nid):
        r = []
        for a in self.aristas:
            if a['tipo'] != 'red':
                continue
            if a['from'] == nid:
                r.append(a['to'])
            if a['to'] == nid:
                r.append(a['from'])
        return r

    def alcanzable(self, nid):
        if nid == self.esc['entrada']:
            return True
        for v in self.adyacentes(nid):
            n = self.nodo(v)
            if n and n['compromisoReal'] and n['estado'] != 'aislado':
                return True
        return False

    def tiene_salto_lateral(self, nid):
        for v in self.adyacentes(nid):
            n = self.nodo(v)
            if n and n['estado'] != 'aislado' and fase_index(n['fase']) >= fase_index('escalada'):
                return True
        return False

    def ruta_a_objetivo(self):
        if self._ruta:
            return self._ruta
        prev = {}
        q = [self.esc['entrada']]
        visto = {self.esc['entrada']}
        while q:
            u = q.pop(0)
            if u == self.objetivo:
                break
            for v in self.adyacentes(u):
                if v not in visto:
                    visto.add(v)
                    prev[v] = u
                    q.append(v)
        ruta = []
        c = self.objetivo
        while c is not None:
            ruta.insert(0, c)
            c = prev.get(c)
        self._ruta = ruta if ruta and ruta[0] == self.esc['entrada'] else [self.esc['entrada'], self.objetivo]
        return self._ruta

    # --------- validación ----------
    def validar_ataque(self, i: dict):
        """None si válida, o string con el motivo de rechazo."""
        n = self.nodo(i['nodoId'])
        if not n:
            return 'Nodo inexistente'
        if n['estado'] == 'aislado':
            return 'Nodo aislado (contenido)'
        t = TECNICA_POR_ID.get(i['tecnicaId'])
        if not t:
            return 'Técnica desconocida'
        fx = fase_index(n['fase'])
        if t['id'] in ('scan_docs', 'sqli_dump', 'phishing_spray'):
            if not self.alcanzable(i['nodoId']):
                return 'Nodo no alcanzable (necesitas un foothold adyacente)'
            return None
        if t['id'] == 'dump_lsass':
            if fx < fase_index('escalada'):
                return 'Requiere privilegios elevados (escalada/root) para volcar memoria de procesos'
            return None
        if t['id'] == 'persist_backdoor':
            if fx < fase_index('acceso_inicial'):
                return 'Requiere acceso inicial previo en el nodo'
            return None
        if t['id'] == 'pivot':
            if fx >= fase_index('acceso_inicial'):
                return 'El nodo ya está comprometido'
            if not self.tiene_salto_lateral(n['id']):
                return 'Necesitas un nodo adyacente con privilegios (escalada)'
            return None
        if t['id'] == 'exfil':
            if fx < fase_index('acceso_inicial'):
                return 'Debes comprometer el nodo antes de exfiltrar'
            if n['valor'] <= 0:
                return 'Nodo sin datos de valor'
            if n['id'] in self._exfiltrados:
                return 'Datos ya exfiltrados de este nodo'
            return None
        if not self.alcanzable(i['nodoId']):
            return 'Nodo no alcanzable (necesitas un foothold adyacente)'
        if fx < fase_index(t['faseRequiere']):
            return f"Requiere fase previa: {t['faseRequiere']}"
        if fx >= fase_index(t['faseProduce']):
            return 'Fase ya alcanzada en este nodo'
        return None

    def prob_exito(self, tecnica_id, n):
        t = TECNICA_POR_ID.get(tecnica_id)
        if not t:
            return 0
        return clamp(t['facilidadBase'] * (1 - self._resistencia(n)) * (1 - n['posturaDefensiva']), 0.02, 0.98)

    def _resistencia(self, n):
        vulns = n['vulnerabilidades']
        if not vulns:
            return 0.6
        avg = sum(v['dificultad'] for v in vulns) / len(vulns)
        return clamp(avg, 0.2, 0.9)

    def _sinc_estado_visual(self, n):
        if n['estado'] in ('aislado', 'honeypot'):
            return
        fx = fase_index(n['fase'])
        n['estado'] = 'limpio' if fx < 0 else 'sondeado' if fx == 0 else 'comprometido'

    # --------- resolver ataque ----------
    def _resolver_ataque(self, i):
        motivo = self.validar_ataque(i)
        t = TECNICA_POR_ID.get(i['tecnicaId'])
        n = self.nodo(i['nodoId'])
        target_label = n['nombre'] if n else i['nodoId']
        cmd_str = (t['comandoEjemplo'] if t and t.get('comandoEjemplo') else f"{i['tecnicaId']} {i['nodoId']}").replace('{target}', target_label)

        if motivo:
            self._log(tipo='ataque', lado='attacker', nodoId=i['nodoId'], malicioso=True, exito=False,
                      texto=f"{t['nombre'] if t else i['tecnicaId']}: rechazado ({motivo})")
            self.log_terminal('attacker', cmd_str, f"[-] EXECUTION REJECTED: {motivo}", 'error', i['nodoId'])
            return

        if self._firstMaliciousTick is None:
            self._firstMaliciousTick = self.tick
        p_exito = self.prob_exito(t['id'], n)
        exito = self.rng.chance(p_exito)
        ruido = t['ruido']

        self._log(tipo='ataque', lado='attacker', nodoId=n['id'], malicioso=True, exito=exito,
                  texto=f"{t['nombre']} sobre {n['nombre']} [ruido:{ruido}] (p={p_exito:.2f}) -> {'ÉXITO' if exito else 'fallo'}")

        if not exito:
            self.log_terminal('attacker', cmd_str, f"[-] PROBE FAILED: La sonda/exploit sobre {n['nombre']} fue bloqueada o no respondió (p={round(p_exito*100)}%).", 'error', n['id'])
            self.log_terminal('defender', 'ebpf_trace -e net_drop', f"[eBPF ALERT] Intento de conexión sospechosa mitigado en {n['nombre']} [ruido: {ruido}]", 'alerta', n['id'])
            return

        salida_detalle = f"[+] SUCCESS: Técnica {t['nombre']} exitosa sobre {n['nombre']}."

        if t['id'] == 'scan_docs':
            n['fase'] = n['fase'] or 'recon'
            sensibles = n.get('archivosSensibles') or []
            extraidos = 0
            for archivo in sensibles:
                if not any(l['nodoId'] == n['id'] and l['item'] == archivo for l in self.loot):
                    tipo = 'doc'
                    sec = 'Documento clasificado interno de la organización.'
                    if 'env' in archivo:
                        tipo = 'env'
                        sec = f"DB_USER=admin_{n['id']} | DB_PASS=Secret@2026! | JWT_SECRET=sk_live_948f2a1b_{n['id']}"
                    elif 'sql' in archivo or 'dump' in archivo or 'tar.gz' in archivo:
                        tipo = 'db'
                        sec = f"DUMP_SQL: {archivo} ({n['valor']*2.8:.1f} MB con registros confidenciales)"
                    elif 'pass' in archivo or 'rsa' in archivo or 'vault' in archivo or 'key' in archivo:
                        tipo = 'cred'
                        sec = f"CREDENTIALS: Clave privada / hash extraído de {archivo}"
                    self.loot.append({'id': f"loot-{self.tick}-{len(self.loot)}", 'tick': self.tick,
                                      'nodoId': n['id'], 'nodoNombre': n['nombre'], 'item': archivo, 'tipo': tipo, 'secreto': sec})
                    extraidos += 1
            salida_detalle = (f"[+] VULN DISCOVERY: Descubiertos {extraidos} archivos (.env, configs, documentos) en {n['nombre']}:\n" +
                              "\n".join(f"    * [ARCH_EXPUESTO] {s}" for s in sensibles))
        elif t['id'] == 'sqli_dump':
            n['fase'] = ORDEN_FASE[max(fase_index(n['fase']), fase_index('acceso_inicial'))]
            item_name = f"sqli_dump_{n['id']}.sql"
            if not any(l['nodoId'] == n['id'] and l['item'] == item_name for l in self.loot):
                sec = f"SQL TABLE DUMP: Esquemas 'usuarios', 'roles', 'transacciones' extraídos ({n['valor']*1.8:.1f} MB con registros y hashes)."
                self.loot.append({'id': f"loot-{self.tick}-{len(self.loot)}", 'tick': self.tick,
                                  'nodoId': n['id'], 'nodoNombre': n['nombre'], 'item': item_name, 'tipo': 'db', 'secreto': sec})
            for archivo in n.get('archivosSensibles') or []:
                if ('sql' in archivo or 'dump' in archivo) and not any(l['nodoId'] == n['id'] and l['item'] == archivo for l in self.loot):
                    self.loot.append({'id': f"loot-{self.tick}-{len(self.loot)}", 'tick': self.tick,
                                      'nodoId': n['id'], 'nodoNombre': n['nombre'], 'item': archivo, 'tipo': 'db',
                                      'secreto': f"EXTRACTED SQL TABLE: {archivo} sustraído mediante inyección de consultas."})
            salida_detalle = (f"[+] SQLMAP 1.7.2#STABLE - INYECCIÓN SQL EXITOSA en {n['nombre']}:\n"
                              f"    [INFO] DBMS identificado: PostgreSQL/MySQL (Inyección booleana y UNION confirmada)\n"
                              f"    [+] Tablas identificadas: ['usuarios_admin', 'cuentas_2026', 'sesiones_activas']\n"
                              f"    [+] Hash volcado: admin_$2y$12$K8j7m..e8b662d005b79942 (Descifrado: Secret@2026!)\n"
                              f"    [+] Registros guardados en C2: sqli_dump_{n['id']}.sql")
        elif t['id'] == 'dump_lsass':
            n['fase'] = 'escalada'
            item_name = f"lsass_hashes_{n['id']}.txt"
            if not any(l['nodoId'] == n['id'] and l['item'] == item_name for l in self.loot):
                sec = f"NTLM_HASHES: Administrator:500:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::"
                self.loot.append({'id': f"loot-{self.tick}-{len(self.loot)}", 'tick': self.tick,
                                  'nodoId': n['id'], 'nodoNombre': n['nombre'], 'item': item_name, 'tipo': 'cred', 'secreto': sec})
            for archivo in n.get('archivosSensibles') or []:
                if ('pass' in archivo or 'rsa' in archivo or 'key' in archivo) and not any(l['nodoId'] == n['id'] and l['item'] == archivo for l in self.loot):
                    self.loot.append({'id': f"loot-{self.tick}-{len(self.loot)}", 'tick': self.tick,
                                      'nodoId': n['id'], 'nodoNombre': n['nombre'], 'item': archivo, 'tipo': 'cred',
                                      'secreto': f"CREDENTIAL VAULT: {archivo} extraído de memoria de procesos."})
            salida_detalle = (f"[+] MIMIKATZ 2.2.0 - SEKURLSA::LOGONPASSWORDS en {n['nombre']}:\n"
                              f"    * SeDebugPrivilege: Activado (Handle de proceso LSASS obtenido)\n"
                              f"    * Dominio: CORP | Usuario: Administrator (RID 500)\n"
                              f"    * Hash NTLM: 31d6cfe0d16ae931b73c59d7e0c089c0\n"
                              f"    * Kerberos TGT: Ticket de dominio capturado y guardado en C2.")
        elif t['id'] == 'persist_backdoor':
            n['fase'] = ORDEN_FASE[max(fase_index(n['fase']), fase_index('escalada'))]
            n['persistente'] = True
            salida_detalle = (f"[+] PERSISTENCIA INSTALADA en {n['nombre']}:\n"
                              f"    * Cronjob implantado: /etc/cron.d/sys-telemetry (Ejecuta beacon C2 cada 3 min)\n"
                              f"    * WebShell camuflada: /var/www/html/.cache_api.php (SHA-256 verificado)\n"
                              f"    * Rootkit eBPF activo: Control persistente que resiste SIGKILL estándar.")
        elif t['id'] == 'phishing_spray':
            n['fase'] = ORDEN_FASE[max(fase_index(n['fase']), fase_index('acceso_inicial'))]
            salida_detalle = (f"[*] CRACKMAPEXEC v5.2.2 - PASS-THE-HASH & CREDENTIAL SPRAY sobre {n['nombre']}:\n"
                              f"    [+] SMB 445 / WinRM: Autenticación exitosa con credenciales de dominio.\n"
                              f"    [+] CORP\\admin_ws : Secret@2026! (Pwn3d!) -> Shell interactiva establecida.\n"
                              f"    [+] Foothold y credenciales activas en {n['nombre']}.")
        elif t['id'] == 'exfil':
            self._exfiltrados.add(n['id'])
            n['fase'] = 'exfiltracion'
            self._datosExfiltrados += n['valor']
            self.loot.append({'id': f"loot-{self.tick}-{len(self.loot)}", 'tick': self.tick,
                              'nodoId': n['id'], 'nodoNombre': n['nombre'], 'item': f"dump_exfiltrado_{n['id']}.db", 'tipo': 'db',
                              'secreto': f"EXFILTRACIÓN COMPLETADA: Base de datos completa sustraída ({n['valor']} MB). Total robado: {self._datosExfiltrados}/{self._metaExfiltracion} MB."})
            salida_detalle = f"[+] EXFILTRATION HARVEST: Extraídos {n['valor']} MB de {n['nombre']} hacia C2 (Total: {self._datosExfiltrados}/{self._metaExfiltracion} MB)."
            self._log(tipo='ataque', lado='attacker', nodoId=n['id'], malicioso=True, exito=True,
                      texto=f"Datos exfiltrados de {n['nombre']} (+{n['valor']}). Total: {self._datosExfiltrados}/{self._metaExfiltracion}")
        else:
            n['fase'] = ORDEN_FASE[max(fase_index(n['fase']), fase_index(t['faseProduce']))]
            if t['id'] == 'privesc':
                salida_detalle = f"[+] ROOT ACCESS GRANTED: Elevación de privilegios conseguida en {n['nombre']}. Control total del nodo."
            elif t['id'] == 'pivot':
                salida_detalle = f"[+] PIVOT ESTABLISHED: Túnel lateral abierto hacia {n['nombre']}. Nuevo salto de red disponible."
            elif t['id'] == 'exploit':
                salida_detalle = f"[+] RCE SHELL OPEN: Explotación exitosa. Shell remota establecida en {n['nombre']}."

        if fase_index(n['fase']) >= fase_index('acceso_inicial'):
            n['compromisoReal'] = True
        self._sinc_estado_visual(n)
        self.aristas.append({'from': 'atacante', 'to': n['id'], 'tipo': 'actividad', 'edad': 0})

        self.log_terminal('attacker', cmd_str, salida_detalle, 'exito', n['id'])
        self.log_terminal('defender', f"ebpf_probe --event sys_enter_connect --host {n['nombre']}",
                          f"[eBPF TELEMETRÍA] Tráfico hostil detectado en {n['nombre']} [técnica: {t['nombre']}, ruido: {ruido}]",
                          'alerta' if ruido == 'alto' else 'output', n['id'])

    def _expirar_aislamientos(self):
        for n in self.nodos:
            if n['estado'] == 'aislado' and n.get('aisladoHasta') is not None and self.tick >= n['aisladoHasta']:
                n['estado'] = 'limpio'
                n['fase'] = None
                n['compromisoReal'] = False
                n['posturaDefensiva'] *= 0.5
                n['senales'] = {}
                n['score'] = 0
                n['aisladoHasta'] = None
                self._log(tipo='sistema', nodoId=n['id'], texto=f"{n['nombre']} vuelve online (remediado)")
                self.log_terminal('defender', f"xdp_filter --restore --host {n['nombre']}",
                                  f"[SOC] Aislamiento concluido. Host {n['nombre']} restaurado a la red corporativa tras desinfección.", 'output', n['id'])

    def _resolver_respuesta(self, i):
        n = self.nodo(i['nodoId'])
        r = aplicar_respuesta(self.nodos, i['respuesta'], i['nodoId'], self.tick)
        self.eventos.append(r['evento'])
        self._penalDisponibilidad += r['penalizaDisponibilidad']
        r_meta = RESPUESTA_POR_ID.get(i['respuesta'])
        cmd_def = (r_meta['comandoEjemplo'] if r_meta and r_meta.get('comandoEjemplo') else f"{i['respuesta']} {i['nodoId']}")
        cmd_def = cmd_def.replace('{target}', n['nombre'] if n else i['nodoId']).replace('{attacker_ip}', '192.168.1.188')
        self.log_terminal('defender', cmd_def, f"[+] DEFENSE APPLIED: {r['evento']['texto']}", 'exito', i['nodoId'])
        nombre = n['nombre'] if n else i['nodoId']
        if i['respuesta'] == 'aislar':
            self.log_terminal('attacker', f"ping -c 1 {nombre}", f"[-] CONNECTION DROPPED: Destino inalcanzable. El host {nombre} ha sido aislado por el defensor.", 'error', i['nodoId'])
        elif i['respuesta'] == 'terminar_proceso':
            self.log_terminal('attacker', f"session_check --host {nombre}", "[-] SIGNAL KILLED: Conexión o shell interrumpida por el SOC defensor.", 'error', i['nodoId'])
        elif i['respuesta'] == 'parchear_env':
            self.log_terminal('attacker', f"curl -s http://{nombre}/.env", "[-] ACCESS DENIED (403): Variables y credenciales rotadas/parcheadas.", 'error', i['nodoId'])
        elif i['respuesta'] == 'parchear_vuln':
            self.log_terminal('attacker', f"check_exploit --target {nombre}", f"[-] EXPLOIT MITIGATED: El servicio en {nombre} fue parchado por el SOC. CVE no explotable (Hotfix).", 'error', i['nodoId'])
        elif i['respuesta'] == 'yara_memory_scan':
            if n and n.get('persistente'):
                n['persistente'] = False
            self.log_terminal('attacker', f"beacon_ping --node {nombre}", f"[-] BEACON DESTROYED: Proceso hostil en memoria purgado mediante firma YARA.", 'error', i['nodoId'])
        elif i['respuesta'] == 'canary_token':
            self.log_terminal('defender', f"canary_monitor --token-status --node {nombre}", f"[CANARY ARM] Trampa HoneyToken sembrada en {nombre}. Telemetría lista.", 'output', i['nodoId'])
            self.log_terminal('attacker', f"probe_env --node {nombre}", f"[!] DECOY SUSPECTED: Detectadas credenciales señuelo en {nombre}.", 'alerta', i['nodoId'])
        elif i['respuesta'] == 'rotate_keys':
            self.log_terminal('attacker', f"ssh -i id_rsa {nombre}", f"[-] AUTH REJECTED: Llaves SSH / Kerberos revocadas en {nombre} por el SOC.", 'error', i['nodoId'])

    def _ruido_benigno(self):
        activos = [x for x in self.nodos if x['estado'] != 'aislado']
        if not activos:
            return
        n = self.rng.pick(activos)
        if self.rng.chance(0.5):
            acciones = ['navegación web', 'tarea cron', 'actualización', 'sincronización de archivos', 'consulta DNS']
            self._log(tipo='benigno', nodoId=n['id'], malicioso=False, texto=f"{n['nombre']}: {self.rng.pick(acciones)}")
            if self.rng.chance(0.18):
                self.log_terminal('defender', 'auditd -k benign_telemetry', f"[AUDIT INFO] Actividad normal en {n['nombre']}: sincronización de rutina verificada.", 'output', n['id'])

    # --------- un tick completo ----------
    def avanzar(self, ataque=None, respuesta=None):
        self.tick += 1
        self._expirar_aislamientos()
        self.detector.decae(self.nodos)
        self._ruido_benigno()
        for ev in [e for e in self.eventos if e['tick'] == self.tick and e['tipo'] == 'benigno']:
            self.detector.observa(self.nodos, ev)
        if ataque:
            self._resolver_ataque(ataque)
            for ev in [e for e in self.eventos if e['tick'] == self.tick and e['tipo'] == 'ataque']:
                self.detector.observa(self.nodos, ev)
        if respuesta:
            self._resolver_respuesta(respuesta)
        # envejecer aristas de actividad
        nuevas_aristas = []
        for a in self.aristas:
            if a['tipo'] == 'red':
                nuevas_aristas.append(a)
            else:
                a['edad'] = a.get('edad', 0) + 1
                if a['edad'] < 12:
                    nuevas_aristas.append(a)
        self.aristas = nuevas_aristas
        # detección
        for al in self.detector.califica(self.nodos, self.tick):
            self.alertas.append(al)
            self._log(tipo='deteccion', lado='defender', nodoId=al['nodoId'],
                      texto=f"ALERTA en {self.nodo_nombre(al['nodoId'])} score={al['score']} {'' if al['verdadera'] else '(posible falso positivo)'}")
            self.log_terminal('defender', f"tgnn_anomaly_eval --node {al['nodoId']}",
                              f"🚨 ALERTA TGNN: Anomalía {al['score']*100:.1f}% en {self.nodo_nombre(al['nodoId'])} | Vectores: {al['senales']}", 'alerta', al['nodoId'])
            if al['verdadera'] and self._firstTrueAlertTick is None:
                self._firstTrueAlertTick = self.tick
        if self._firstTrueAlertTick is not None and self._containmentTick is None:
            queda = any(n['compromisoReal'] and n['estado'] != 'aislado' for n in self.nodos)
            if not queda:
                self._containmentTick = self.tick
        self._recortar()

    # --------- fin de partida ----------
    def terminada(self):
        return self._datosExfiltrados >= self._metaExfiltracion or self.tick >= self.tickMax

    def ganador(self):
        if self._datosExfiltrados >= self._metaExfiltracion:
            return 'attacker'
        return 'defender' if self._disponibilidad() >= 0.5 else 'empate'

    def _disponibilidad(self):
        return clamp(1 - self._penalDisponibilidad / self._sumValor, 0, 1)

    def metricas(self):
        return {
            'mttd': (self._firstTrueAlertTick - self._firstMaliciousTick) if (self._firstMaliciousTick is not None and self._firstTrueAlertTick is not None) else None,
            'mttr': (self._containmentTick - self._firstTrueAlertTick) if (self._firstTrueAlertTick is not None and self._containmentTick is not None) else None,
            'disponibilidad': round(self._disponibilidad(), 3),
            'datosExfiltrados': self._datosExfiltrados,
            'metaExfiltracion': self._metaExfiltracion,
            'alertasTotales': len(self.alertas),
            'alertasFalsas': sum(1 for a in self.alertas if not a['verdadera']),
        }

    # --------- utilidades ----------
    def _log(self, **e):
        self.eventos.append({'tick': self.tick, 'id': f"e{self.tick}-{len(self.eventos)}", **e})

    def log_terminal(self, lado, cmd, salida, tipo='output', nodoId=None):
        self.terminalLogs.append({'id': f"tlog-{self.tick}-{len(self.terminalLogs)}", 'tick': self.tick,
                                  'lado': lado, 'cmd': cmd, 'salida': salida, 'tipo': tipo, 'nodoId': nodoId})
        if len(self.terminalLogs) > 90:
            self.terminalLogs = self.terminalLogs[-90:]

    def pensar(self, p):
        self.pensamientos.append(p)
        self._recortar()

    def _recortar(self):
        if len(self.eventos) > VENTANA:
            self.eventos = self.eventos[-VENTANA:]
        if len(self.pensamientos) > 24:
            self.pensamientos = self.pensamientos[-24:]
        if len(self.alertas) > VENTANA:
            self.alertas = self.alertas[-VENTANA:]
        if len(self.loot) > 50:
            self.loot = self.loot[-50:]
