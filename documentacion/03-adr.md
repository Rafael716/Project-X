# Project X — Architecture Decision Records (ADR)

Formato: Contexto → Decisión → Alternativas → Consecuencias. Estado de todos: **Aceptado** (2026-10-16) salvo indicación.

---

## ADR-0001 — Simulación en memoria, no eBPF/kernel real
**Contexto.** La propuesta original usa eBPF/XDP y syscalls reales. Debe correr en 2 PCs cualesquiera (incluida Windows), ser seguro para un curso y reproducible para calificar.
**Decisión.** Modelar todo como una **simulación en memoria** en el servidor: la "actividad del sistema" son eventos sintéticos; las "sondas" son generadores de eventos; la "respuesta XDP" es un cambio de estado del nodo.
**Alternativas.** (a) eBPF real en una VM Linux — descartado: no portable, riesgoso, no reproducible. (b) Contenedores Docker con tráfico real — descartado: complejidad de montaje y exposición a tooling real.
**Consecuencias.** + Portable, seguro, determinista, calificable. − No mide rendimiento de kernel real; se documenta la correspondencia concepto↔real en `06`.

---

## ADR-0002 — TypeScript en todo el stack
**Contexto.** El usuario pide abrir el sistema en la web y un solo lenguaje para el frontend; se busca mantenibilidad.
**Decisión.** **TypeScript** en servidor (Node) y en frontend (React + Vite), con un módulo de **protocolo tipado compartido** (`shared/protocol.ts`) importado por ambos.
**Alternativas.** Backend en Python (alineado con PyTorch del paper) + front TS — descartado: dos lenguajes, dos modelos de datos, más fricción. Go para el server — descartado: el modelo IA/heurístico es más corto en TS y comparte tipos con el front.
**Consecuencias.** + Un solo modelo de datos, refactors seguros, menos glue. − El "ML" se implementa como heurística en TS (no PyTorch); aceptable porque es simulación (ver ADR-0005).

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
