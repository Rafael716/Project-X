"""Motor de simulación autoritativo.

Estado como dicts (coincide 1:1 con el contrato que consume el frontend).

Decisiones de construcción aplicadas de las sesiones del curso:
- Sesión 2 (polimorfismo / enlace dinámico): el motor no sabe qué técnica ni qué
  respuesta ejecuta; llama `tecnica.efecto(e, n)` / `resp.aplicar(e, n)` y el
  runtime despacha a la subclase correcta. Añadir una técnica no toca el motor.
- Sesión 3 (DbC): cada tick termina verificando `invariantes_del_motor(self)`.
  Las ayudas que mutan estado declaran sus pre/postcondiciones.
- Sesión 3 (CQS): los métodos que empiezan por consultar (validar/alcanzable/
  prob_exito) son puros; los que mutan (avanzar/_resolver_*) no devuelven datos
  que se usen como consulta.
- Capa "de juego": energía por lado (presupuesto de acciones), puntaje y combos.
"""

import config
from contratos import asegura, invariantes_del_motor, requiere
from detector import Detector
from response import RESPUESTA_POR_ID
from rng import Rng
from techniques import TECNICA_POR_ID, fase_index

VENTANA = 60  # eventos/alertas recientes conservados para la UI


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


class Engine:
    # perillas de balance externalizadas (config.py / variables de entorno, U3)
    ENERGIA_MAX = config.ENERGIA_MAX
    ENERGIA_REGEN = config.ENERGIA_REGEN    # energía que cada lado recupera por tick
    PUNTOS_META = config.PUNTOS_META        # puntaje que corona una victoria "por dominio"

    def __init__(self, esc: dict, seed: int):
        self.esc = esc
        self.rng = Rng(seed)
        self.nodos = esc['nodos']  # ya es copia profunda (cargar_escenario)
        for n in self.nodos:
            n['senales'] = {}
            n.setdefault('persistente', False)
        self.aristas = [dict(a) for a in esc['aristas']]
        self.eventos = []
        self.alertas = []
        self.pensamientos = []
        self.loot = []
        self.terminalLogs = []
        self.tick = 0
        # Duración con algo de azar (sembrado) para que cada partida se sienta
        # distinta y dure al menos ~1 min: +0..48 ticks (0..12 s) sobre la base.
        self.tickMax = esc['tickMax'] + self.rng.irange(0, 48)
        self.detector = Detector(umbral=config.DETECTOR_UMBRAL)
        self._firstMaliciousTick = None
        self._firstTrueAlertTick = None
        self._containmentTick = None
        self._penalDisponibilidad = 0.0
        self.datos_exfiltrados = 0
        self.exfiltrados = set()
        self.meta_exfiltracion = esc['metaExfiltracion']
        self.suma_valor = sum(n['valor'] for n in self.nodos)
        self.objetivo = esc['objetivo']
        self._ruta = None
        # capa de juego
        self.energia = {'attacker': self.ENERGIA_MAX, 'defender': self.ENERGIA_MAX}
        self.puntos = {'attacker': 0, 'defender': 0}
        self.combo = {'attacker': 0, 'defender': 0}

        self._log(tipo='sistema', texto=f"Partida lista en {esc['nombre']}. El atacante quiere robar los datos de {self.nodo_nombre(esc['objetivo'])}.")
        self.log_terminal('attacker', 'iniciar-ataque',
                          f"Listo para atacar. Red: {esc['nombre']} · Entras por: {self.nodo_nombre(esc['entrada'])} · Meta: robar los datos de {self.nodo_nombre(esc['objetivo'])}.", 'cmd')
        self.log_terminal('defender', 'iniciar-defensa',
                          "Vigilancia activada. Estoy observando toda la red para detectar cualquier cosa rara.", 'cmd')

    # --------- consultas (CQS: puras) ----------
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
        ruta, c = [], self.objetivo
        while c is not None:
            ruta.insert(0, c)
            c = prev.get(c)
        self._ruta = ruta if ruta and ruta[0] == self.esc['entrada'] else [self.esc['entrada'], self.objetivo]
        return self._ruta

    def validar_ataque(self, i: dict):
        """None si la jugada es válida, o string con el motivo de rechazo (CQS: pura)."""
        n = self.nodo(i['nodoId'])
        if not n:
            return 'Nodo inexistente'
        if n['estado'] == 'aislado':
            return 'Nodo aislado (contenido)'
        t = TECNICA_POR_ID.get(i['tecnicaId'])
        if not t:
            return 'Técnica desconocida'
        return t.validar(self, n)

    def prob_exito(self, tecnica_id, n):
        t = TECNICA_POR_ID.get(tecnica_id)
        if not t:
            return 0.0
        return clamp(t.facilidadBase * (1 - self._resistencia(n)) * (1 - n['posturaDefensiva']), 0.02, 0.98)

    def disponibilidad(self):
        return clamp(1 - self._penalDisponibilidad / self.suma_valor, 0, 1)

    def maquinas_tomadas(self):
        """Cuántas máquinas tiene el atacante AHORA (comprometidas y no aisladas)."""
        return sum(1 for n in self.nodos if n['compromisoReal'] and n['estado'] != 'aislado')

    def todas_tomadas(self):
        """True si el atacante tiene TODAS las máquinas de la red (condición de victoria)."""
        return self.maquinas_tomadas() == len(self.nodos)

    def _resistencia(self, n):
        vulns = n['vulnerabilidades']
        if not vulns:
            return 0.6
        avg = sum(v['dificultad'] for v in vulns) / len(vulns)
        return clamp(avg, 0.2, 0.9)

    # --------- mutadores de apoyo (usados por las técnicas/respuestas) ----------
    def sincronizar_estado(self, n):
        if n['estado'] in ('aislado', 'honeypot'):
            return
        fx = fase_index(n['fase'])
        n['estado'] = 'limpio' if fx < 0 else 'sondeado' if fx == 0 else 'comprometido'

    def agregar_loot(self, n, item, tipo, secreto):
        """Añade un botín si no estaba ya. Devuelve 1 si era nuevo, 0 si repetido."""
        if any(l['nodoId'] == n['id'] and l['item'] == item for l in self.loot):
            return 0
        self.loot.append({'id': f"loot-{self.tick}-{len(self.loot)}", 'tick': self.tick,
                          'nodoId': n['id'], 'nodoNombre': n['nombre'], 'item': item, 'tipo': tipo, 'secreto': secreto})
        return 1

    def registrar_exfiltracion(self, n):
        requiere(n['compromisoReal'], 'exfiltrar exige nodo comprometido', nodo=n['id'])
        requiere(n['id'] not in self.exfiltrados, 'no se exfiltra dos veces el mismo nodo', nodo=n['id'])
        antes = self.datos_exfiltrados
        self.exfiltrados.add(n['id'])
        n['fase'] = 'exfiltracion'
        self.datos_exfiltrados += n['valor']
        self.agregar_loot(n, f"dump_exfiltrado_{n['id']}.db", 'db',
                          f"EXFILTRACIÓN COMPLETADA: {n['valor']} MB de {n['nombre']}. Total {self.datos_exfiltrados}/{self.meta_exfiltracion} MB.")
        asegura(self.datos_exfiltrados == antes + n['valor'], 'la exfiltración suma el valor del nodo', nodo=n['id'])

    # --------- resolver ataque ----------
    def _resolver_ataque(self, i):
        t = TECNICA_POR_ID.get(i['tecnicaId'])
        n = self.nodo(i['nodoId'])
        motivo = self.validar_ataque(i)
        target_label = n['nombre'] if n else i['nodoId']
        cmd_str = (t.comandoEjemplo if t and t.comandoEjemplo else f"{i['tecnicaId']} {i['nodoId']}").replace('{target}', target_label)

        if motivo:
            self._rechazo('attacker', i, t, cmd_str, motivo)
            return
        if self.energia['attacker'] < t.costo:
            self._rechazo('attacker', i, t, cmd_str, f'Energía insuficiente ({self.energia["attacker"]}/{t.costo})')
            return

        self.energia['attacker'] -= t.costo
        if self._firstMaliciousTick is None:
            self._firstMaliciousTick = self.tick
        p_exito = self.prob_exito(t.id, n)
        exito = self.rng.chance(p_exito)

        # ruido/fase viajan como DATOS del evento (no incrustados en el texto) para
        # que el detector no dependa de cómo esté redactado el mensaje.
        self._log(tipo='ataque', lado='attacker', nodoId=n['id'], malicioso=True, exito=exito,
                  ruido=t.ruido, fase=t.faseProduce,
                  texto=f"{t.nombre} en {n['nombre']} → {'funcionó' if exito else 'falló'}")

        if not exito:
            self.combo['attacker'] = 0
            self.log_terminal('attacker', cmd_str, f"No funcionó: {n['nombre']} resistió (tenías {round(p_exito*100)}% de chance).", 'error', n['id'])
            self.log_terminal('defender', 'vigilancia', f"Bloqueé algo sospechoso que venía hacia {n['nombre']}.", 'alerta', n['id'])
            return

        salida = t.efecto(self, n)                 # <-- enlace dinámico (Sesión 2)
        self._puntuar('attacker', t.puntos)
        if fase_index(n['fase']) >= fase_index('acceso_inicial'):
            n['compromisoReal'] = True
        self.sincronizar_estado(n)
        self.aristas.append({'from': 'atacante', 'to': n['id'], 'tipo': 'actividad', 'edad': 0})
        self.log_terminal('attacker', cmd_str, salida, 'exito', n['id'])
        self.log_terminal('defender', 'vigilancia',
                          f"Detecté actividad rara en {n['nombre']} (parece: {t.nombre}).",
                          'alerta' if t.ruido == 'alto' else 'output', n['id'])

    def _rechazo(self, lado, i, t, cmd_str, motivo):
        self._log(tipo='ataque', lado=lado, nodoId=i['nodoId'], malicioso=True, exito=False,
                  texto=f"{t.nombre if t else i['tecnicaId']}: no se pudo ({motivo})")
        self.log_terminal(lado, cmd_str, f"No se pudo: {motivo}", 'error', i['nodoId'])

    # --------- resolver respuesta ----------
    def _resolver_respuesta(self, i):
        r = RESPUESTA_POR_ID.get(i['respuesta'])
        n = self.nodo(i['nodoId'])
        if not r or not n:
            return
        cmd = (r.comandoEjemplo or f"{i['respuesta']} {i['nodoId']}").replace('{target}', n['nombre'])
        if self.energia['defender'] < r.costo:
            self.log_terminal('defender', cmd, f"Sin energía: '{r.nombre}' cuesta {r.costo} y tienes {self.energia['defender']}. Espera a que se recargue.", 'error', n['id'])
            return

        self.energia['defender'] -= r.costo
        hostil = n['compromisoReal'] or n['estado'] == 'sondeado'
        res = r.aplicar(self, n)                    # <-- enlace dinámico (Sesión 2)
        self._penalDisponibilidad += res.penalizacion
        self._puntuar('defender', r.puntos if hostil else r.puntos_fp)
        self.eventos.append({'tick': self.tick, 'id': f"r{self.tick}-{n['id']}", 'tipo': 'respuesta',
                             'lado': 'defender', 'nodoId': n['id'], 'texto': res.texto})
        self.log_terminal('defender', cmd, f"✔ {res.texto}", 'exito', n['id'])
        if res.eco:
            self.log_terminal('attacker', 'revisar-acceso', res.eco, 'error', n['id'])

    # --------- puntaje / combos ----------
    def _puntuar(self, lado, base):
        if base <= 0:
            self.puntos[lado] = max(0, self.puntos[lado] + base)
            self.combo[lado] = 0
            return
        self.combo[lado] += 1
        bonus = 1 + 0.1 * (self.combo[lado] - 1)   # combo: acciones encadenadas valen más
        self.puntos[lado] += round(base * bonus)

    # --------- ciclo de vida ----------
    def _expirar_aislamientos(self):
        for n in self.nodos:
            if n['estado'] == 'aislado' and n.get('aisladoHasta') is not None and self.tick >= n['aisladoHasta']:
                n.update(estado='limpio', fase=None, compromisoReal=False, persistente=False,
                         score=0, senales={}, aisladoHasta=None)
                n['posturaDefensiva'] *= 0.5
                self._log(tipo='sistema', nodoId=n['id'], texto=f"{n['nombre']} volvió a funcionar (ya está limpia).")
                self.log_terminal('defender', 'reconectar',
                                  f"{n['nombre']} reconectada y limpia, lista para trabajar.", 'output', n['id'])

    def _ruido_benigno(self):
        activos = [x for x in self.nodos if x['estado'] != 'aislado']
        if not activos:
            return
        n = self.rng.pick(activos)
        if self.rng.chance(0.5):
            acciones = ['navegación web', 'tarea cron', 'actualización', 'sincronización de archivos', 'consulta DNS']
            self._log(tipo='benigno', nodoId=n['id'], malicioso=False, texto=f"{n['nombre']}: {self.rng.pick(acciones)}")

    def avanzar(self, ataque=None, respuesta=None):
        """Un tick completo. Termina verificando los invariantes del motor (DbC)."""
        self.tick += 1
        for lado in self.energia:
            self.energia[lado] = min(self.ENERGIA_MAX, self.energia[lado] + self.ENERGIA_REGEN)
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
        vivas = []
        for a in self.aristas:
            if a['tipo'] == 'red':
                vivas.append(a)
            else:
                a['edad'] = a.get('edad', 0) + 1
                if a['edad'] < 12:
                    vivas.append(a)
        self.aristas = vivas

        for al in self.detector.califica(self.nodos, self.tick):
            self.alertas.append(al)
            self._log(tipo='deteccion', lado='defender', nodoId=al['nodoId'],
                      texto=f"¡Alarma! Algo raro en {self.nodo_nombre(al['nodoId'])} (nivel {round(al['score']*100)}%){'' if al['verdadera'] else ' — quizá sea falsa alarma'}")
            self.log_terminal('defender', 'alarma',
                              f"🚨 Alarma en {self.nodo_nombre(al['nodoId'])}: actividad sospechosa al {round(al['score']*100)}%. ¡Revísala!", 'alerta', al['nodoId'])
            if al['verdadera'] and self._firstTrueAlertTick is None:
                self._firstTrueAlertTick = self.tick
        if self._firstTrueAlertTick is not None and self._containmentTick is None:
            if not any(n['compromisoReal'] and n['estado'] != 'aislado' for n in self.nodos):
                self._containmentTick = self.tick

        self._recortar()
        invariantes_del_motor(self)

    # --------- fin de partida ----------
    def terminada(self):
        # La partida termina SOLO cuando el atacante se queda con TODAS las
        # máquinas de la red, o cuando se acaba el tiempo (el defensor aguantó).
        # Nada más la corta antes: robar datos o bajar la disponibilidad dan
        # puntos, pero no terminan la partida.
        return self.todas_tomadas() or self.tick >= self.tickMax

    def ganador(self):
        # Gana el atacante solo si tomó TODA la red; si se acabó el tiempo sin
        # lograrlo, gana el defensor por haber aguantado.
        return 'attacker' if self.todas_tomadas() else 'defender'

    def metricas(self):
        return {
            'mttd': (self._firstTrueAlertTick - self._firstMaliciousTick) if (self._firstMaliciousTick is not None and self._firstTrueAlertTick is not None) else None,
            'mttr': (self._containmentTick - self._firstTrueAlertTick) if (self._firstTrueAlertTick is not None and self._containmentTick is not None) else None,
            'disponibilidad': round(self.disponibilidad(), 3),
            'datosExfiltrados': self.datos_exfiltrados,
            'metaExfiltracion': self.meta_exfiltracion,
            'alertasTotales': len(self.alertas),
            'alertasFalsas': sum(1 for a in self.alertas if not a['verdadera']),
            'puntosAtacante': self.puntos['attacker'],
            'puntosDefensor': self.puntos['defender'],
            'puntosMeta': self.PUNTOS_META,
            'energiaAtacante': self.energia['attacker'],
            'energiaDefensor': self.energia['defender'],
            'energiaMax': self.ENERGIA_MAX,
            'comboAtacante': self.combo['attacker'],
            'comboDefensor': self.combo['defender'],
            'maquinasTomadas': self.maquinas_tomadas(),
            'maquinasTotales': len(self.nodos),
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
