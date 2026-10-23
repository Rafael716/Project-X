# Project X — Modelo de Simulación

Este documento define la semántica que implementa el servidor. Es la "verdad" del juego.

## 1. Correspondencia concepto real ↔ simulación

| Concepto del paper (real) | En Project X (simulado) | Dónde |
|---------------------------|--------------------------|-------|
| Actividad del sistema / syscalls | Eventos sintéticos por tick | `engine` |
| Sonda eBPF | Generador de eventos (benignos + de ataque) | `engine`, `attack catalog` |
| Grafo dinámico Proceso→Socket→Archivo | Grafo de red: Nodos + Aristas con tipo | `net model` |
| TGNN (detección) | Score de anomalía explicable (EWMA + reglas) | `detector` |
| Agente LLM/ReAct | Política ReAct heurística (+hook LLM) | `agents` |
| Respuesta XDP (aislar red) | Cambio de estado del nodo a *aislado* | `response` |
| MITRE ATT&CK | Catálogo de técnicas abstraídas | `attack catalog` |
| Latencia < 100 ms | Tick de 250 ms + score < 50 ms | ADR-0004 |

## 2. Red simulada

Un **escenario** define una topología. Nodo:

```
Nodo {
  id, nombre, tipo: workstation|server|router|database|honeypot
  servicios: string[]           // p.ej. ssh, http, smb, sql
  vulnerabilidades: {id, dificultad 0..1, tactica}[]
  valor: number                 // importancia (afecta score de disponibilidad)
  estado: limpio|sondeado|comprometido|aislado|honeypot
  compromisoReal: boolean       // ¿realmente lo logró el atacante? (para penalizar FP)
}
```

Aristas: conexiones de red (quién puede alcanzar a quién) + aristas dinámicas de actividad (proceso→socket) que nacen de los eventos y envejecen.

**Niveles disponibles** (`scenario.py`, registro cerrado):
- **PYMES-01** (Normal): router, 2 workstations, web server, database. Entrada por Recepción, objetivo la base de datos. Meta 6 MB, 240 ticks.
- **DATACENTER-02** (Difícil): firewall/VPN, DMZ, microservicios, Active Directory, vault de secretos y data lake con PII. Vulnerabilidades más duras, meta 10 MB, 300 ticks.

Cada nodo trae `pos` (x,y en 0..1) para dibujar el mapa diseñado del nivel en la web.

## 3. Kill chain (fases)

```
recon  ->  acceso_inicial  ->  escalada  ->  movimiento_lateral  ->  exfiltracion
```

Reglas duras (neuro-simbólico, parte "simbólica"), tal como las implementa `engine.validarAtaque`:
- Sobre un **mismo nodo** la cadena directa es `recon → acceso_inicial → escalada`; cada paso exige el anterior.
- **Movimiento lateral (`pivot`)**: en lugar de recorrer todas las fases en cada nodo, propaga el foothold. Requiere que un nodo **adyacente** esté en `escalada` (jump-off) y lleva al nodo destino directamente a `comprometido` (sin recon). Así el atacante avanza por la topología hacia el objetivo.
- **Exfiltración (`exfil`)**: requiere que el nodo esté `comprometido` y tenga datos (`valor > 0`); se puede hacer una sola vez por nodo y suma su `valor` a los datos robados.
- Un nodo solo es **alcanzable** si es la entrada o es adyacente a un nodo comprometido no aislado (hay que tener foothold para llegar).
- Sobre un nodo `aislado` toda técnica falla (contención). El aislamiento es **temporal** (§6): al expirar, el host vuelve `limpio` (remediado).

## 4. Catálogo de técnicas (abstraído de MITRE ATT&CK)

Cada técnica declara: táctica, fase que requiere/produce, servicio objetivo, "ruido" que genera (afecta detección) y dificultad base. **No contiene comandos ni payloads reales** — solo parámetros numéricos de simulación.

| Técnica | Táctica MITRE | Fase | Ruido | Nota |
|--------|---------------|------|-------|------|
| Barrido de puertos | TA0007 Discovery | recon | alto | fácil de detectar |
| Enumeración de servicios | TA0007 Discovery | recon | medio | |
| Fuerza de credenciales | TA0006 Credential Access | acceso_inicial | medio | |
| Explotación de servicio | TA0001 Initial Access | acceso_inicial | bajo | difícil, sigiloso |
| Escalada de privilegios | TA0004 Priv Esc | escalada | bajo | |
| Pivote lateral | TA0008 Lateral Movement | movimiento_lateral | medio | |
| Robo de datos | TA0010 Exfiltration | exfiltracion | alto | objetivo final |

> **Implementación (Semana 2):** cada técnica es una subclase de `Tecnica`
> (`techniques.py`) con sus metadatos (incluido `costo` de energía y `puntos`) y
> sus métodos `validar()`/`efecto()`. El motor las despacha por polimorfismo; el
> catálogo completo vigente son 12 técnicas (barrido, enum, scan_docs, bruteforce,
> exploit, sqli_dump, privesc, dump_lsass, persist_backdoor, phishing_spray, pivot,
> exfil). Añadir una no toca el motor (ADR-0009).

Resolución de una técnica en el tick (si el atacante tiene energía ≥ `costo`):

```
p_exito = clamp( base_facilidad_tecnica
               * (1 - dificultad_vuln_nodo)
               * (1 - postura_defensiva_nodo)   // sube si hay honeypot/vigilancia
               , 0.02, 0.98 )
exito = PRNG() < p_exito
```

## 5. Detector de anomalía (surrogate de TGNN) — RF-30/31

Por cada nodo se mantiene un vector de señales con decaimiento EWMA (ventana temporal = memoria del "TGNN"):

- `s_recon`: tasa de eventos de descubrimiento recientes.
- `s_fanout`: aristas de conexión nuevas desde el nodo (abanico).
- `s_rareza`: aristas proceso→socket nunca vistas en la línea base benigna.
- `s_tecnica`: peso por técnicas de alto ruido observadas.
- `s_reputacion`: reputación de la IP/origen (lista simulada).

Todas las señales de una técnica de ataque **escalan con su `ruido`**: una técnica de ruido `bajo` (p. ej. explotación sigilosa) casi no mueve el score, mientras que `portscan` o `exfil` (ruido `alto`) lo disparan. Por eso **el sigilo es una estrategia real**: espaciar acciones y preferir técnicas silenciosas retrasa la detección (MTTD más alto).

Score:
```
score(nodo) = sigmoid( Σ w_i * s_i  -  sesgo )
```
Alerta si `score > umbral` (default 0.6). **Falsos positivos:** el ruido benigno puede elevar señales; con `umbral` bajo aparecen FP → el defensor aprende el trade-off (precisión vs. cobertura). Cada alerta incluye el **desglose de señales** que la dispararon (explicabilidad — ADR-0005).

> Calibración: los pesos `w_i`, el `sesgo`, el `umbral` y la tasa de ruido benigno son **perillas** del escenario, no constantes ocultas. Un modelo mínimo sin estas perillas no reproduce el mundo real (sensores/relojes derivan); aquí el "mundo" es el balance ataque/defensa y se afina por escenario. *(ponytail: perillas expuestas a propósito)*

## 6. Respuestas del defensor — RF-32/33

| Respuesta | Efecto | Costo si mal dirigida |
|-----------|--------|------------------------|
| Aislar nodo | El nodo pasa a `aislado` por N ticks (default 24); ataques futuros fallan. Al expirar vuelve `limpio` (remediado) | Costo base de disrupción (todo host offline molesta) + extra si era sano (FP penalizado). No se puede aislar todo gratis |
| Terminar proceso | Revierte la última actividad maliciosa del nodo (baja una fase) | Si no había actividad: sin efecto, pequeño costo de atención |
| Desplegar honeypot | Sube `postura_defensiva`; desvía al atacante y sube detección | Consume presupuesto de respuesta |
| Bloquear IP/origen | Reduce `s_reputacion` futura de ese origen | Puede bloquear tráfico benigno (−disponibilidad leve) |

## 7. Métricas y condición de victoria — RF-40/41

- **MTTD** = ticks entre el primer evento malicioso real y la primera alerta verdadera.
- **MTTR** = ticks entre esa alerta y la contención efectiva del nodo comprometido.
- **Disponibilidad** = 1 − (penalizaciones por aislar/bloquear nodos sanos, ponderadas por `valor`).
- **Datos exfiltrados** = suma del `valor` de datos robados por el atacante.

Fin de partida (condición única y simple de explicar):
- **Gana Atacante** solo si llega a **tener TODAS las máquinas** de la red a la vez
  (`todas_tomadas()`: cada nodo con `compromisoReal` y no aislado). La partida
  termina en ese instante.
- **Gana Defensor** si **aguanta hasta `T_max`** sin que el atacante llegue a tener
  todas las máquinas (resistió).
- No hay otra condición que corte la partida antes: robar datos o bajar la
  disponibilidad **dan puntaje** ("dominio") pero **no terminan** el juego. El
  aislamiento del defensor le quita temporalmente máquinas al atacante y retrasa
  su victoria. `T_max` lleva un pequeño jitter sembrado (replay sigue exacto).

## 8. Determinismo y replay — ADR-0004/0008

Partida = `(semilla, escenarioId, lista ordenada de intents con su tick)`. Reproducir esa tupla regenera byte a byte el curso de la partida. El replay exportado es exactamente esa tupla más el log de eventos para verificación.

## 9. Invariantes (se verifican en tests y en ejecución)

1. Nunca hay exfiltración desde un nodo no comprometido.
2. Un nodo `aislado` no cambia de fase de compromiso mientras siga aislado.
3. MTTD/MTTR solo se fijan una vez (monótonos).
4. La misma semilla + mismos intents ⇒ mismo estado final (determinismo).
5. `score`, `posturaDefensiva`, energía y datos exfiltrados siempre dentro de su rango.

Los invariantes 1 y 5 se verifican **en cada tick** con `contratos.py`
(`invariantes_del_motor`), no solo en tests: si el motor los viola es un bug y
aborta con `ContratoRoto` (fail-fast, Semana 3). Ver `07-construccion-sw707.md`.

## 10. Capa de juego (energía, puntaje, combos)

Para que se sienta como un juego, además de la win-condition clásica:

- **Energía (0..10 por lado):** cada técnica/respuesta cuesta energía; se regenera
  +1 por tick. Fuerza a **priorizar** jugadas en vez de spamear. La UI la muestra
  como pips; un botón sin energía suficiente se deshabilita.
- **Puntaje:** cada acción con éxito da puntos (una técnica silenciosa y profunda
  da más que un barrido ruidoso; una respuesta certera da más que un falso
  positivo, que **resta**). El marcador superior es un *tug-of-war* entre ambos.
- **Combos:** acciones encadenadas con éxito valen progresivamente más (x1.1, x1.2…);
  un fallo rompe el combo. Premia planificar una cadena limpia.
- **Puntaje = "dominio":** es el marcador vistoso (barra *tug-of-war*) y sirve de
  referencia, pero **no define** quién gana. La victoria se decide por tener
  todas las máquinas (atacante) o aguantar hasta el final (defensor), §7.

Todo esto es estado determinista con sus invariantes (punto 5), así que el replay
sigue siendo exacto (§8).
