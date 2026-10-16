# Project X — Requerimientos

Identificadores: **RF** = requerimiento funcional, **RNF** = no funcional. Prioridad MoSCoW: **M** (Must), **S** (Should), **C** (Could).

## 1. Requerimientos funcionales

### Partida y conexión
| ID | Prioridad | Requerimiento | Criterio de aceptación |
|----|-----------|---------------|------------------------|
| RF-01 | M | El sistema permite **crear una partida** y genera un **código** de 6 caracteres. | Al crear, el host recibe un código único reusable mientras la partida viva. |
| RF-02 | M | Un segundo jugador puede **unirse** con el código. | Con código válido entra; con inválido recibe error claro. |
| RF-03 | M | Cada jugador **elige rol** (atacante/defensor); no pueden coincidir. | Si un rol ya está tomado, no se ofrece. |
| RF-04 | S | Un **espectador** puede unirse en modo solo-lectura. | El espectador ve todo pero no tiene panel de acciones. |
| RF-05 | M | La partida **no inicia** hasta que atacante y defensor estén presentes y marquen "listo". | Botón *Iniciar* deshabilitado hasta 2 roles listos. |

### Simulación
| ID | Prioridad | Requerimiento | Criterio de aceptación |
|----|-----------|---------------|------------------------|
| RF-10 | M | El servidor mantiene el **estado autoritativo** de la red simulada y lo difunde. | Ambos clientes ven el mismo estado tras cada tick. |
| RF-11 | M | La simulación avanza por **ticks** deterministas con RNG **sembrado**. | Misma semilla + mismas acciones ⇒ misma partida (reproducible). |
| RF-12 | M | Se genera **tráfico benigno** de fondo (ruido realista). | El feed muestra eventos benignos aun sin acciones del atacante. |
| RF-13 | M | La red tiene **nodos** con servicios, vulnerabilidades y estado de compromiso. | Cada nodo expone: tipo, servicios, vulns, estado {limpio, sondeado, comprometido, aislado}. |

### Atacante
| ID | Prioridad | Requerimiento | Criterio de aceptación |
|----|-----------|---------------|------------------------|
| RF-20 | M | El atacante elige una **técnica** del catálogo contra un **nodo objetivo**. | La acción se valida (técnica aplicable al estado/servicio del nodo). |
| RF-21 | M | El resultado (éxito/fallo) depende de vuln del nodo, postura defensiva y RNG. | Resultado y probabilidad se registran en el evento. |
| RF-22 | M | El avance sigue una **kill chain**: recon → acceso inicial → escalada → lateral → exfil. | No se permite exfiltrar desde un nodo no comprometido. |
| RF-23 | S | El **agente atacante IA** puede jugar en autoplay con bucle ReAct trazable. | Cada decisión muestra *pensamiento → acción → observación*. |

### Defensor
| ID | Prioridad | Requerimiento | Criterio de aceptación |
|----|-----------|---------------|------------------------|
| RF-30 | M | El defensor recibe el **flujo de eventos** y un **score de anomalía** por nodo/arista. | El score se actualiza en cada tick. |
| RF-31 | M | Se generan **alertas** cuando el score supera un umbral; con tasa de falsos positivos no nula. | Hay alertas verdaderas y algunas falsas (configurable). |
| RF-32 | M | El defensor aplica **respuestas**: aislar nodo, terminar proceso, desplegar honeypot, bloquear IP. | Cada respuesta cambia el estado y afecta al atacante de forma visible. |
| RF-33 | M | Respuestas **mal dirigidas tienen costo** (aislar un nodo legítimo daña el servicio). | Aislar nodo crítico sano baja el puntaje de disponibilidad. |
| RF-34 | S | El **agente defensor IA** puede jugar en autoplay con ReAct trazable. | Igual que RF-23. |

### Resultado y cierre
| ID | Prioridad | Requerimiento | Criterio de aceptación |
|----|-----------|---------------|------------------------|
| RF-40 | M | Condición de victoria por objetivo del atacante, por contención del defensor o por tiempo. | Al cumplirse, la partida pasa a estado *terminada* y muestra ganador. |
| RF-41 | M | Métricas finales: **MTTD** (tiempo a detección), **MTTR** (tiempo a contención), disponibilidad, datos exfiltrados. | Se muestran en la pantalla de resumen. |
| RF-42 | C | **Exportar replay** de la partida (eventos + estados) a JSON. | Botón *Descargar replay* produce un archivo válido. |

## 2. Requerimientos no funcionales

| ID | Categoría | Requerimiento | Meta medible |
|----|-----------|---------------|--------------|
| RNF-01 | Latencia (EDA) | Propagación de estado servidor→clientes | p95 < 200 ms en LAN |
| RNF-02 | Latencia (detección) | Cómputo de score tras un evento | < 50 ms por tick en el servidor |
| RNF-03 | Reproducibilidad | Partida determinista dada semilla + acciones | 100 % reproducible en replay |
| RNF-04 | Usabilidad | Curva de aprendizaje | Estudiante entiende la UI en < 2 min; textos en español |
| RNF-05 | Accesibilidad | Contraste y teclado | WCAG AA de contraste; foco visible; navegable por teclado |
| RNF-06 | Portabilidad | Ejecutable en Win/mac/Linux | `npm install && npm run dev`, sin GPU ni admin |
| RNF-07 | Resiliencia | Reconexión de cliente | Si un cliente cae y vuelve con el mismo código, retoma el estado |
| RNF-08 | Seguridad (del propio simulador) | No ejecutar nada real | Sin `eval`, sin shell, sin red externa; entrada validada en el servidor |
| RNF-09 | Mantenibilidad | Un solo lenguaje, tipos compartidos | Protocolo tipado compartido entre front y back |
| RNF-10 | Observabilidad | Trazas de agente y log de eventos | Todo evento y decisión IA queda en el log de la partida |

## 3. Trazabilidad requerimiento → documento

- Arquitectura que satisface RNF-01/02/09: `04-arquitectura-c4.md`, `ADR-0001`, `ADR-0003`.
- Modelo que satisface RF-11/13/20-22/30-33: `06-modelo-de-simulacion.md`.
- Flujos que satisfacen RF-01-05/40: `05-diagramas.md` (casos de uso, estados, secuencia).
