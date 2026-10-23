# Project X — Construcción de Software II: de la teoría al código

Este documento es la **trazabilidad** entre las 7 sesiones del curso SW707 y el
código del proyecto. Para cada sesión: la idea central, dónde se aplicó y cómo
verificarlo. Es el mapa para explicar el proyecto en la sustentación.

> Todo el backend está en `backend/` (Python 3.11 + FastAPI). Una sola fuente de
> verdad; sin backend duplicado.

---

## Panorama en una frase

> **Diseña para la flexibilidad (Semana 2), construye para el rendimiento, y
> defiéndete contra la incertidumbre del runtime (Semanas 3-7).**

El motor del juego es el "sistema" que se construye con rigor industrial: el
navegador es territorio hostil, el tick es el runtime impredecible, y cada
sesión aporta una capa de defensa.

```
  Navegador (HOSTIL)                     NÚCLEO (CONFIABLE)
  ┌───────────┐   barricada.py   ┌──────────────────────────────────┐
  │  WebSocket │ ──validación──▶ │ match → engine                    │
  │  (cliente) │   (Semana 4)    │   técnicas/respuestas polimórficas │ (Semana 2)
  └───────────┘                  │   contratos + invariantes          │ (Semana 3)
        ▲                        │   energía/puntaje/combos           │
        │ logs JSON + correlation│   agentes ReAct                    │
        │ (Semana 5)             └──────────────┬─────────────────────┘
        │                                       │
   observabilidad.py          resiliencia.py (Semana 7): circuit breaker,
   (Semana 5)                 contrapresión, proxy que degrada sin caerse
                              app.py: candado por-socket (Semana 6)
```

---

## Semana 1 — Construcción, reúso y dependencias

**Ideas:** construir *para* la verificación; el código en ejecución no es el
código en disco; gestión de dependencias y cadena de suministro; la IA acelera
sintaxis pero el ingeniero es el dueño del runtime.

**Aplicado en:**
- **Construcción para la verificación:** cada módulo nuevo deja una prueba
  ejecutable (`test_engine.py`, 15 tests) y aserciones vivas (`contratos.py`).
- **Dependencias mínimas y auditadas:** `requirements.txt` fija versiones
  (`fastapi==0.115.6`, `pydantic`, `uvicorn`, `wsproto`). Sin dependencias
  pesadas innecesarias (no se añadió socket.io, structlog, etc.).
- **Responsabilidad del ingeniero sobre la IA:** los agentes del juego son
  heurística determinista nuestra; el *hook* LLM es opcional y va envuelto en
  un proxy de resiliencia (no se delega el runtime a ciegas).

---

## Semana 2 — Problemas de runtime en la POO: polimorfismo y enlace dinámico

**Ideas:** una interfaz, múltiples realidades; el enlace dinámico es una
indirección de memoria (V-Table); genéricos; la flexibilidad dinámica tiene
costo de rendimiento y **superficie de ataque** (reflexión → Log4Shell).

**Aplicado en:**
- **Polimorfismo (`techniques.py`, `response.py`):** `Tecnica` y `Respuesta`
  son clases base; cada técnica/respuesta concreta sobreescribe `validar()`,
  `efecto()` / `aplicar()`. El motor hace `tecnica.efecto(e, n)` y el **runtime
  despacha** al método del tipo real — sin que el motor sepa cuál es.
- **Abierto/cerrado:** añadir una técnica = una subclase nueva + registrarla.
  `engine.py` **no cambia**. (ver ADR-0009)
- **Evitar la superficie de ataque de la reflexión:** el id que manda el cliente
  solo indexa un **diccionario cerrado** (`TECNICA_POR_ID`). Nunca hay `getattr`,
  `import` dinámico ni `eval` con datos del cliente — justo la lección Log4Shell.

**Verificación:** `test_dump_lsass_requires_escalada`, `test_persistencia_resiste_sigkill_pero_no_yara`.

---

## Semana 3 — Desarrollo por Contratos (DbC)

**Ideas:** precondición (obligación del cliente), postcondición (obligación del
proveedor), invariante de clase (la "constitución"); aserciones ejecutables con
"dientes"; fail-fast; separación comando-consulta (CQS).

**Aplicado en:**
- **`contratos.py`:** `requiere()` (pre), `asegura()` (post),
  `invariantes_del_motor()` (invariante). Al romperse lanzan `ContratoRoto`
  (**fail-fast**). Ejemplo real: `registrar_exfiltracion()` en `engine.py`
  declara `requiere(n['compromisoReal'], ...)` y `asegura(...)` que la suma
  cuadre.
- **Invariante del motor:** al final de **cada tick**, `avanzar()` llama
  `invariantes_del_motor(self)` — score en [0,1], energía en rango, no hay
  exfiltración de nodos inexistentes, etc.
- **CQS:** las consultas (`validar_ataque`, `alcanzable`, `prob_exito`,
  `disponibilidad`) son **puras** (no mutan estado); los comandos (`avanzar`,
  `_resolver_*`) mutan y no devuelven datos que se usen como consulta.
- **Contrato ≠ barricada:** los contratos asumen **confianza** (entre módulos
  internos; si fallan es bug nuestro). La validación de input hostil es la
  barricada (Semana 4).

**Verificación:** `test_contrato_detecta_score_corrupto`.

---

## Semana 4 — Programación Defensiva y barricadas

**Ideas:** el mundo real es hostil; la barricada define el perímetro entre
código no confiable y confiable; validación por capas (tipo/tamaño → rango →
semántica); fail-fast vs robustez tolerante; las aserciones son el sistema
inmunológico interno; los desbordamientos son ejecución de código.

**Aplicado en:**
- **`barricada.py`:** única puerta entre el WebSocket (hostil) y el núcleo.
  Tres capas con **pydantic** (`extra='forbid'`): (1) tipo y tamaño —máx 4 KB—,
  (2) rango/enum —nombre 1..20, código `[A-HJ-NP-Z2-9]{6}`—, (3) semántica —la
  técnica/escenario existe—.
- **Fail-fast vs robustez:** dentro del núcleo, un contrato roto aborta
  (fail-fast). En la frontera, el servidor es tolerante: una jugada ilegal se
  **informa** y la partida sigue (`ReglaDeJuego` → mensaje al jugador).
- **Barricada ↔ contrato:** la barricada asume **hostilidad** (sanea y rechaza);
  el contrato asume **confianza** (aborta si se viola). Exactamente la diapositiva
  "¿Contratos o barricadas?".

**Verificación:** `test_barricada_rechaza_basura`, `test_barricada_acepta_valido`.

---

## Semana 5 — Manejo de errores, excepciones y observabilidad

**Ideas:** condición de error (esperada) vs excepción (anómala); jerarquía de
excepciones de dominio; exception chaining (preservar la causa raíz);
antipatrones (swallowing, catch-all, log-and-throw); mensajes informativos;
logging estructurado JSON; MDC / correlation_id; niveles de log.

**Aplicado en:**
- **Jerarquía de dominio (`errores.py`):** `ProjectXError` como base de la app;
  `EntradaInvalida`, `ReglaDeJuego` (y `SinEnergia`), `PartidaNoEncontrada`,
  `DemasiadasAcciones`, `ContratoRoto`. Las excepciones del lenguaje nunca
  llegan a la UI.
- **Condición de error vs excepción:** una jugada ilegal es **esperada**
  (`ReglaDeJuego`, ni se loguea como error); un `ContratoRoto` es anómalo (bug).
- **Exception chaining:** `barricada.py` hace `raise EntradaInvalida(...) from e`
  para no perder la causa raíz (`JSONDecodeError`, `ValidationError`).
- **Sin antipatrones:** se captura en **un solo lugar** (la frontera `manejar()`
  en `app.py`); nada de `catch` vacío ni *log-and-throw*.
- **Logging estructurado (`observabilidad.py`):** cada línea es **JSON** con
  nivel/evento/contexto. `correlation_id` por mensaje en un **ContextVar** (el
  MDC async). Niveles usados: INFO (partida creada/iniciada/terminada), WARNING
  (entrada inválida, contrapresión), ERROR (falló operación), CRITICAL (bug).
- **Mensajes informativos:** cada excepción lleva `contexto` (qué partida, nodo,
  técnica) → al depurar no hay que adivinar.

---

## Semana 6 — Concurrencia

**Ideas:** la ilusión secuencial vs la realidad concurrente; condición de
carrera y deadlock; thread safety; primitivas (mutex, semáforo, monitor);
memoria compartida vs paso de mensajes; async/await libera hilos; atomicidad;
visibilidad de memoria.

**Aplicado en:**
- **async/await (`app.py`):** el servidor es asíncrono (FastAPI + asyncio). El
  bucle de cada partida (`run_match`) es una tarea; miles de conexiones con
  pocos hilos reales (la lección I/O-bound de la Semana 6).
- **Sección crítica protegida:** escribir a un WebSocket desde el bucle de ticks
  **y** desde un handler a la vez corrompe el socket (condición de carrera real).
  Se protege con un **candado por-socket** (`_lock_for`), no global: un cliente
  lento no congela el broadcast a los demás (se evita un cuasi-deadlock de
  rendimiento). Cada envío lleva **timeout** para no retener el candado para
  siempre.
- **Atomicidad del tick:** un tick aplica todos sus cambios y **solo entonces**
  difunde el estado; los clientes nunca ven un estado a medias (todo-o-nada).
- **Estado autoritativo único:** no hay memoria compartida entre partidas; cada
  `Match` es su propio dominio (aislamiento, como el modelo de actores).

---

## Semana 7 — Tolerancia a fallas y resiliencia

**Ideas:** el radio de impacto; detección-contención-recuperación; reintentos
con backoff (no ciegos → tormenta/DDoS); idempotencia; **circuit breaker**;
**bulkheads**; **contrapresión**; **degradación elegante**; la arquitectura de
una PC2 (proxy de resiliencia que envuelve un cliente inestable).

**Aplicado en (`resiliencia.py`):**
- **Circuit breaker:** estados CERRADO → ABIERTO → SEMI_ABIERTO. Protege las
  llamadas a la política de cada agente. Usa el **tick como reloj** → determinista.
- **Contrapresión (`TokenBucket`):** cada cliente tiene una cubeta; si manda
  mensajes más rápido de lo tolerable, se rechazan temporalmente (equivalente a
  un **HTTP 429**) en vez de encolar sin límite y desbordar memoria.
- **Bulkhead + degradación elegante (`PoliticaResiliente`):** el *proxy/decorador*
  que envuelve a cada agente. Si la política primaria **falla o tarda** (timeout
  suave de 50 ms), el fallo se **contiene** ahí y el agente **degrada** a una
  política mínima — el tick nunca se congela. Es exactamente la "Arquitectura de
  una PC2 exitosa": un proxy de resiliencia alrededor de un cliente inestable
  (preparado para cuando el agente primario sea un LLM remoto, ADR-0006/0013).
- **Detección-contención-recuperación:** dentro del *juego*, estos tres pilares
  son el bucle del defensor (detector → aislar/parchear → remediar). La resiliencia
  del *servidor* es la capa de infraestructura que lo sostiene.

**Verificación:** `test_circuit_breaker_abre_y_se_recupera`,
`test_proxy_degrada_si_la_politica_primaria_revienta`.

---

## Tabla resumen

| Semana | Concepto clave | Archivo(s) | Test |
|--------|----------------|-----------|------|
| 1 | Construir para verificar, dependencias mínimas | `requirements.txt`, todo `test_engine.py` | 15 tests |
| 2 | Polimorfismo / enlace dinámico | `techniques.py`, `response.py` | `test_dump_lsass_*`, `test_persistencia_*` |
| 3 | Diseño por Contrato (pre/post/invariante), CQS | `contratos.py`, `engine.py` | `test_contrato_detecta_score_corrupto` |
| 4 | Barricada / programación defensiva | `barricada.py` | `test_barricada_*` |
| 5 | Jerarquía de excepciones, logs JSON, MDC | `errores.py`, `observabilidad.py` | (flujo en `app.py`) |
| 6 | Concurrencia: async, candado por-socket, atomicidad | `app.py` | smoke WS |
| 7 | Circuit breaker, contrapresión, degradación | `resiliencia.py`, `match.py` | `test_circuit_breaker_*`, `test_proxy_degrada_*` |

---

## Cómo demostrarlo en 60 segundos

```bash
cd backend && pytest -q            # 15 verdes: invariantes + barricada + resiliencia
PX_CONTRATOS=1 python app.py       # arranca con contratos activos
# en otra terminal:
curl http://localhost:8787/metrics # contadores JSON (observabilidad)
# juega una partida, luego mira los logs JSON del servidor (una línea = un evento)
```
