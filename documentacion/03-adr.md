# Project X — Architecture Decision Records (ADR)

Formato: Contexto → Decisión → Alternativas → Consecuencias. Estado: **Aceptado**. ADR-0001 a 0008 el 2026-10-16; ADR-0009 a 0014 el 2026-10-23 (ronda de construcción robusta aplicando las 7 sesiones del curso — ver [07-construccion-sw707](07-construccion-sw707.md)); ADR-0015 a 0020 el 2026-10-23 (evolución a v2.0 / Etapa II, Unidades 3 y 4 — ver [08-evolucion-v2](08-evolucion-v2.md)).

---

## ADR-0001 — Simulación en memoria, no eBPF/kernel real
**Contexto.** La propuesta original usa eBPF/XDP y syscalls reales. Debe correr en 2 PCs cualesquiera (incluida Windows), ser seguro para un curso y reproducible para calificar.
**Decisión.** Modelar todo como una **simulación en memoria** en el servidor: la "actividad del sistema" son eventos sintéticos; las "sondas" son generadores de eventos; la "respuesta XDP" es un cambio de estado del nodo.
**Alternativas.** (a) eBPF real en una VM Linux — descartado: no portable, riesgoso, no reproducible. (b) Contenedores Docker con tráfico real — descartado: complejidad de montaje y exposición a tooling real.
**Consecuencias.** + Portable, seguro, determinista, calificable. − No mide rendimiento de kernel real; se documenta la correspondencia concepto↔real en `06`.

---

## ADR-0002 — Backend en Python (FastAPI) + frontend TypeScript/React
**Contexto.** El sistema se abre en la web (frontend tipado) y necesita un backend que sea la autoridad del estado. El dominio del paper (IA/grafos) es más natural en Python, y permite crecer hacia PyTorch/LLM sin cambiar de lenguaje de servidor.
**Decisión.** **Python 3.11 + FastAPI** en el backend (motor de simulación, gateway WebSocket, agentes). **TypeScript + React + Vite** en el frontend. El contrato de datos es la **única fuente de verdad** en `shared/protocol.ts`; el backend produce exactamente esa forma (dicts que serializan 1:1 a esas interfaces).
**Alternativas.** Un solo lenguaje en todo el stack — descartado: el dominio IA/grafos y el *hook* a LLM viven mejor en Python, y el frontend igual requiere TS/React. Backend en Go — descartado: menos ecosistema de IA.
**Consecuencias.** + Backend idiomático para IA, un solo backend que mantener, contrato tipado end-to-end. − El contrato se mantiene a mano en dos lados (lo cubre la validación de la barricada, ADR-0010, y los tests).

---

## ADR-0003 — Servidor autoritativo + WebSocket (arquitectura dirigida por eventos)
**Contexto.** Dos clientes deben ver el mismo estado con baja latencia (RNF-01) y no debe poder hacerse trampa desde el cliente.
**Decisión.** El **servidor es la única autoridad** del estado. Los clientes envían *intents* (acciones); el servidor valida, aplica en el tick y **difunde** el nuevo estado y los eventos por **WebSocket** (`ws`). EDA: todo es un flujo de eventos.
**Alternativas.** P2P entre las 2 PCs (WebRTC) — descartado: sin árbitro hay trampa y desincronización. REST + polling — descartado: latencia y no push. socket.io — descartado: dependencia pesada; `ws` basta.
**Consecuencias.** + Anti-trampa, sincronía, reconexión simple. − Necesita un proceso servidor accesible por ambas PCs (ver ADR-0007).

---

## ADR-0004 — Simulación por ticks deterministas con RNG sembrado
**Contexto.** RF-11/RNF-03 exigen reproducibilidad para calificar y para el replay.
**Decisión.** Bucle de **ticks** a frecuencia fija (p. ej. 4 Hz). Todo azar pasa por un **PRNG sembrado** (mulberry32). El estado en el tick *n* es función pura de (estado *n-1*, intents del tick, PRNG).
**Alternativas.** Tiempo real continuo con `Date.now()` — descartado: no reproducible. Event-driven puro sin tick — descartado: más difícil de sincronizar y de razonar sobre latencia.
**Consecuencias.** + Replay exacto, tests deterministas, latencia acotada. − Granularidad del tick limita la "resolución" temporal (aceptable, 250 ms).

---

## ADR-0005 — Detección: heurística explicable que emula un TGNN
**Contexto.** El paper usa TGNN (PyTorch Geometric Temporal). En TS, sin GPU y en tiempo de curso, entrenar un TGNN real es inviable y poco explicable para una demo.
**Decisión.** Implementar un **detector de anomalía explicable** sobre el grafo dinámico: *score* por nodo combinando señales (rareza de aristas nuevas proceso→socket, fan-out de conexiones, frecuencia de técnicas, reputación de IP) con pesos + ventana temporal (EWMA). Umbral configurable con falsos positivos. Se documenta como "modelo neuro-simbólico": señales estadísticas + reglas duras.
**Alternativas.** TGNN real en TS (tfjs) — descartado: coste, opacidad, no cabe en el curso. Solo reglas — descartado: no muestra el componente "ML/anomalía".
**Consecuencias.** + Explicable (cada alerta dice *por qué*), rápido (RNF-02), suficiente para docencia. − No generaliza como una red entrenada; es un *surrogate*. Camino de evolución: exportar eventos y entrenar un TGNN offline (fuera de alcance).

---

## ADR-0006 — Agentes: bucle ReAct heurístico, LLM opcional por *hook*
**Contexto.** RF-23/34 piden agentes trazables; el paper sugiere LangGraph/DSPy + LLM. No puede depender de una API de pago ni de GPU para correr en clase.
**Decisión.** Agentes con bucle **ReAct** (*reason → act → observe*) cuya política por defecto es **heurística determinista** (sembrada). Se expone una interfaz `AgentPolicy` con un *hook* opcional para delegar la decisión a un **LLM local/API** sin cambiar el motor.
**Alternativas.** LLM obligatorio — descartado: no corre offline, no determinista, no calificable. Árbol de decisión fijo sin traza — descartado: no muestra el "razonamiento".
**Consecuencias.** + Corre offline y determinista; se puede "subir de nivel" a LLM para la evolución. − La heurística no es tan creativa como un LLM; aceptable para MVP.

---

## ADR-0007 — Despliegue para LAN del laboratorio
**Contexto.** Dos PCs deben conectarse. Exponer a internet añade auth, TLS y superficie de ataque innecesaria (fuera de alcance).
**Decisión.** El servidor escucha en `0.0.0.0:PORT` en la PC-host; la otra PC entra por `http://IP-DEL-HOST:PORT`. La partida se protege por **código efímero**, no por cuentas.
**Alternativas.** Deploy en la nube — descartado por alcance/latencia/auth. Túnel tipo ngrok — opcional y documentado, no requerido.
**Consecuencias.** + Cero infraestructura, arranque en minutos. − Solo LAN por defecto; si se quiere remoto, usar un túnel (documentado en README).

---

## ADR-0008 — Estado en memoria + replay a JSON, sin base de datos
**Contexto.** Persistencia multi-partida está fuera de alcance; se quiere simplicidad.
**Decisión.** El estado de cada partida vive **en memoria** del servidor. Al terminar, se puede **exportar el replay** (semilla + lista de intents + eventos) a **JSON**; reproducirlo regenera la partida (por ADR-0004).
**Alternativas.** SQLite/Postgres — descartado: innecesario para el MVP, añade esquema y migraciones.
**Consecuencias.** + Sin dependencias de datos. − Si el servidor se reinicia se pierden partidas en curso (aceptable; el replay cubre el post-mortem).

---

## ADR-0009 — Técnicas y respuestas como jerarquía polimórfica (Semana 2)
**Contexto.** El catálogo de técnicas del atacante y de respuestas del defensor crece; con `if/elif` por id en el motor, cada técnica nueva obliga a editar el motor (acoplamiento) y el bloque de condicionales se vuelve ilegible.
**Decisión.** Cada técnica es una **subclase de `Tecnica`** que sobreescribe `validar()`/`efecto()`; cada respuesta, una subclase de `Respuesta` con `aplicar()`. El motor llama `tecnica.efecto(e, n)` sin saber cuál es: el **enlace dinámico** (la "V-Table" de la Semana 2) despacha al método del tipo real. Los registros `TECNICA_POR_ID`/`RESPUESTA_POR_ID` son diccionarios **cerrados**: el id del cliente es solo una clave, nunca se usa para cargar código (sin reflexión → se evita la clase de fallo Log4Shell de la Semana 2).
**Alternativas.** `match/case` o `dict` de funciones — funciona, pero no agrupa metadatos+validación+efecto por técnica. Plugins cargados dinámicamente — descartado: superficie de ataque y complejidad que el curso explícitamente marca como riesgosa.
**Consecuencias.** + Añadir una técnica = escribir una clase y registrarla; el motor **no se toca** (abierto a extensión, cerrado a modificación). + El coste del enlace dinámico es irrelevante a 4 Hz. − Una jerarquía más que leer (documentada).

---

## ADR-0010 — Barricada de entrada con validación por capas (Semana 4)
**Contexto.** Todo lo que llega del navegador por WebSocket es **hostil** hasta probar lo contrario (inputs malformados, payloads gigantes, inyección). El núcleo no debe ensuciarse con validación defensiva repetida.
**Decisión.** Una única **barricada** (`barricada.py`) en la frontera valida cada mensaje en tres capas (tipo/tamaño → rango/enum → semántica contra los catálogos) usando **pydantic** con `extra='forbid'`. Detrás de la barricada, el núcleo asume datos limpios y usa **contratos** (ADR-0011). Programación defensiva en la frontera; Diseño por Contrato en el interior — la distinción exacta de la Semana 4.
**Alternativas.** Validar ad-hoc en cada handler — descartado: disperso, se olvida un caso. Confiar en el frontend — descartado: el cliente es manipulable (ADR-0003).
**Consecuencias.** + Una sola puerta, mensajes de error claros, núcleo limpio. + Límite de 4 KB por mensaje corta payloads abusivos. − Hay que mantener el esquema alineado con el contrato (tests lo cubren).

---

## ADR-0011 — Diseño por Contrato con aserciones ejecutables (Semana 3)
**Contexto.** El motor tiene invariantes que, si se rompen, indican un **bug** (score fuera de [0,1], exfiltración de un nodo inexistente, energía negativa). Un comentario `# PRE:` no se verifica solo.
**Decisión.** `contratos.py` expone `requiere()` (precondición = obligación del llamador), `asegura()` (postcondición = obligación de la rutina) e `invariantes_del_motor()` que se ejecuta **al final de cada tick**. Al violarse, lanzan `ContratoRoto` (**fail-fast**: el bug se detiene donde ocurre, no se propaga en silencio). Se pueden apagar con `PX_CONTRATOS=0` (como `java -ea`).
**Alternativas.** Solo tests — descartado: no cubren estados en producción. Validación defensiva redundante dentro del núcleo — descartado: confunde "bug mío" con "input hostil" (eso es la barricada).
**Consecuencias.** + Los bugs se detectan en el tick exacto que los causa; el contrato roto dice qué módulo rompió su promesa (debugging en minutos, Semana 3). − Costo de verificación por tick (despreciable; apagable).

---

## ADR-0012 — Observabilidad: logs estructurados JSON + contexto por tarea (Semana 5)
**Contexto.** Con varias partidas y dos jugadores por partida escribiendo a la vez, un log de texto plano secuencial es ilegible y no se puede consultar por máquina.
**Decisión.** Todo log es un **objeto JSON** (`observabilidad.py`) con nivel, evento y contexto. Un `correlation_id` por mensaje viaja en un **ContextVar** (equivalente async del MDC/ThreadLocal de la Semana 5), así las líneas de dos jugadores no se mezclan. Se loguea **una sola vez en la frontera** (nada de *log-and-throw*). `/metrics` expone contadores.
**Alternativas.** `print()` — descartado: no estructurado, no filtrable. Librería pesada (structlog/loguru) — innecesaria para el alcance.
**Consecuencias.** + Logs consultables, trazables por partida, sin ruido duplicado. − Formato menos "bonito" para leer a ojo (se asume consumo por máquina, Semana 5).

---

## ADR-0013 — Tolerancia a fallas: proxy de resiliencia y contrapresión (Semana 7)
**Contexto.** El tick no puede congelarse ni caerse porque un agente falle o un cliente inunde de mensajes. El *hook* a LLM (ADR-0006) añade un punto de fallo por red/latencia.
**Decisión.** `resiliencia.py` implementa **circuit breaker**, **token bucket** (contrapresión: rechazo temporal tipo HTTP 429 si el cliente va muy rápido) y **PoliticaResiliente**, un *proxy/decorador* que envuelve la política de cada agente con breaker + timeout suave + **degradación elegante** a una política mínima. Es la "Arquitectura de una PC2 exitosa" de la Semana 7: si la política primaria (p. ej. un LLM remoto) falla o tarda, el agente baja a la heurística **sin bloquear el tick**.
**Alternativas.** Reintentos ciegos — descartado: la Semana 7 muestra que causan tormentas (DDoS accidental). Sin protección — descartado: un cliente malicioso congela el servidor.
**Consecuencias.** + La partida sobrevive a fallos de agente y a clientes abusivos. + El breaker usa el **tick como reloj** → también es determinista (ADR-0004). − Más piezas que entender (documentadas en 07).

---

## ADR-0014 — Capa de juego: energía, puntaje y combos
**Contexto.** El pedido es que se sienta **más como un juego**. El motor original solo tenía win-condition por exfiltración/contención; faltaba tensión momento a momento y una forma de "ir ganando".
**Decisión.** Cada lado tiene **energía** (presupuesto que se gasta por acción y regenera por tick: fuerza a priorizar, no spamear), **puntaje** (cada técnica/respuesta otorga puntos; un falso positivo resta) y **combos** (acciones encadenadas con éxito valen más). Victoria también por **puntaje meta** o por disponibilidad < 50%, además de exfiltración/tiempo. Hay **dos niveles** (`PYMES-01` normal, `DATACENTER-02` difícil).
**Alternativas.** Dejar solo la condición original — descartado: menos jugable. Cooldowns por acción en vez de energía — equivalente; energía es un único recurso legible en la UI.
**Consecuencias.** + Más jugable y rejugable, decisiones con costo de oportunidad. + La energía/puntaje son estado determinista con sus invariantes (ADR-0011). − Hay que balancear (perillas por escenario, doc 06).

---

## ADR-0015 — Ciclo de vida de la partida como máquina de estados table-driven (Unidad 3)
**Contexto.** El estado de la partida (`lobby/lista/en_curso/pausada/terminada`) se decidía con `if estado == ...` repartidos por `match.py`; era fácil permitir una transición inválida (p. ej. pausar una partida ya terminada) sin que nadie lo notara.
**Decisión.** Centralizar las transiciones en una **tabla** `(estado, evento) → estado` en `backend/estados.py`. Toda transición pasa por `transita()`; una no declarada lanza `ReglaDeJuego` (fail-fast). `match.py` ya no decide estados, solo dispara eventos.
**Alternativas.** Librería de FSM (`transitions`) — descartado: una dependencia para 5 estados es sobre-ingeniería. Enums + métodos — más código sin más garantías que la tabla.
**Consecuencias.** + Agregar/cambiar una transición es editar un dict; las transiciones ilegales son imposibles de alcanzar en silencio. + Base natural para diagramar el ciclo de vida (doc 05). − Un cambio de flujo exige actualizar la tabla (deseable).

---

## ADR-0016 — Configuración externalizada + feature flags en un módulo único (Unidad 3)
**Contexto.** Perillas de balance y puertos estaban como constantes en el código; cambiar una exigía editar y reiniciar, y no había forma de apagar una capacidad sin borrar código.
**Decisión.** Un módulo `backend/config.py` lee **toda** la configuración de variables de entorno/`.env` una vez al importar (con defaults), expone **feature flags** (`FEATURES`) y una vista pública en `/api/config`. Ningún otro módulo lee `os.environ`. El servidor solo anuncia las técnicas/respuestas cuya feature está activa y la barricada rechaza las apagadas.
**Alternativas.** `pydantic-settings` — innecesario para ~15 variables. Archivo YAML/TOML — otra dependencia y otro formato; `.env` + entorno es el estándar 12-factor.
**Consecuencias.** + Config sin recompilar, descubrible y testeable; capacidades activables por despliegue. + Secretos fuera del repo (`.gitignore` + `.env.example`). − Hay que documentar cada variable (está en `.env.example`).

---

## ADR-0017 — Internacionalización acotada por catálogo (Unidad 3)
**Contexto.** La UI es español-primero (curso UNI). El brief pide i18n *cuando el dominio lo justifique*, o justificar su alcance.
**Decisión.** Externalizar los **mensajes que ve el jugador** a un catálogo por idioma en `backend/i18n.py`, seleccionable con `PX_LANG`, con fallback a la clave. Se prueba la competencia (texto separado del código, locale configurable, fallback) sin gettext/Babel ni `.po`, que serían sobre-ingeniería para 2 idiomas.
**Alternativas.** gettext + archivos `.po` — maquinaria pensada para catálogos grandes con pluralización/traductores; no aplica. No hacer nada — no evidencia la competencia.
**Consecuencias.** + Mecanismo real de i18n demostrable y barato. − No cubre pluralización ni formato de fechas/números (no hacen falta aquí; se justifica).

---

## ADR-0018 — API REST de lectura junto al WebSocket (Unidad 3: distribución)
**Contexto.** El juego fluye por WebSocket (ADR-0003), pero un cliente externo o un tablero necesita consultar versión, config, catálogos y partidas sin entrar a jugar.
**Decisión.** Exponer endpoints **REST de solo lectura** (`/api/version`, `/api/config`, `/api/escenarios`, `/api/tecnicas`, `/api/partidas`) en el mismo FastAPI. El WebSocket sigue siendo el único canal que **muta** el estado; REST no cambia nada (CQS a nivel de transporte).
**Alternativas.** Todo por WebSocket — obliga a un cliente con socket para una simple consulta. gRPC — innecesario para LAN/navegador.
**Consecuencias.** + Integrable por `curl`/fetch/monitoreo; separa lectura (REST) de la autoridad (WS). − Dos superficies que mantener (mínimas y de solo lectura).

---

## ADR-0019 — Contenerización con imagen única multi-stage (Unidad 3)
**Contexto.** Desplegar exige Node (build web) y Python (runtime). Pedir ambos en cada PC es fricción.
**Decisión.** Un `Dockerfile` **multi-stage**: etapa Node construye `web/dist`, etapa Python instala el backend y copia el build; el contenedor final solo tiene Python y sirve web + WebSocket en un puerto. `docker-compose.yml` lo levanta con `.env` opcional.
**Alternativas.** Dos contenedores (web + api) con proxy — innecesario: el backend ya sirve la web (ADR-0003). Imagen única con Node en runtime — más pesada y con superficie extra.
**Consecuencias.** + `docker compose up` y listo, sin instalar toolchains; imagen de runtime liviana. + Reproducible entre máquinas (adaptativo). − Requiere Docker en la máquina host.

---

## ADR-0020 — Characterization tests antes de refactorizar/modernizar (Unidad 4)
**Contexto.** La Etapa II refactoriza el motor (estados, config). Sin una red que fije el comportamiento determinista actual, un refactor podría cambiarlo sin que nadie lo note.
**Decisión.** `backend/test_caracterizacion.py` **fotografía** el curso de partidas deterministas (golden por `escenario+semilla`) y lo afirma. No codifica lo que *debería* pasar (eso lo hacen los contratos) sino lo que *pasa hoy*; si un cambio lo altera, el test revienta y obliga a decidir si fue intencional.
**Alternativas.** Solo tests de contrato — verifican invariantes, no el curso exacto. No pinnear — deja el refactor sin red.
**Consecuencias.** + Refactor seguro; el golden documenta el comportamiento legacy. − Hay que re-generar el golden cuando el cambio de comportamiento es deliberado (el archivo explica cómo).
