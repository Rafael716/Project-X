# Project X — Visión y Alcance

> **Naturaleza del sistema:** Project X es un **simulador académico** (ciber-rango / *cyber range* educativo). No ejecuta ataques reales, no toca el kernel, no escanea redes reales y no contiene malware. Todo ocurre sobre una **red simulada en memoria**. Su propósito es docente: entender el ciclo ataque–detección–respuesta y las técnicas de IA que lo apoyan (GNN/TGNN, agentes ReAct, EDA, razonamiento neuro-simbólico) sin ningún riesgo operativo.

---

## 1. Propósito

Construir un entorno de **combate cibernético simulado en bucle cerrado**, jugable entre **dos personas en dos PCs distintas** conectadas por web:

- **PC A — Rol Atacante (Red Team):** opera un agente ofensivo que elige técnicas estilo MITRE ATT&CK contra una red simulada.
- **PC B — Rol Defensor (Blue Team):** opera un agente defensivo que observa el flujo de eventos, detecta anomalías y aplica respuestas (aislar, matar proceso, desplegar honeypot).

Cada lado puede jugarse en **modo manual** (la persona decide), **modo autónomo** (el agente IA decide con ReAct heurístico) o **modo asistido** (la IA sugiere, la persona confirma).

## 2. ¿Por qué un simulador y no la versión real?

La propuesta original (eBPF + TGNN + XDP) requiere kernel Linux, GPU y datasets de linaje. Para un curso, eso es:

- difícil de montar en 2 PCs cualesquiera (Windows incluido),
- peligroso si se maneja tooling ofensivo real,
- imposible de calificar de forma reproducible.

El simulador **preserva los conceptos académicos** (grafo dinámico, detección por anomalía, agentes, EDA de baja latencia, win-condition por MTTD/MTTR) y los hace **ejecutables en cualquier navegador**, reproducibles y seguros. La correspondencia concepto-real está en `06-modelo-de-simulacion.md`.

## 3. Objetivos

| # | Objetivo | Métrica de éxito |
|---|----------|------------------|
| O1 | Jugar un enfrentamiento atacante vs defensor entre 2 PCs vía web | Dos navegadores en LAN entran a la misma partida y ven el mismo estado en < 200 ms |
| O2 | Modelar el ciclo recon → acceso → movimiento lateral → exfiltración | El atacante puede completar una *kill chain* contra la red simulada |
| O3 | Detección por anomalía sobre grafo dinámico | El defensor recibe un *score* de anomalía por nodo/arista y alertas |
| O4 | Respuesta activa y su efecto | Aislar/matar/honeypot reduce de forma medible el avance del atacante |
| O5 | Agentes IA para ambos lados | Cada lado puede correr en autoplay con decisiones trazables (ReAct) |
| O6 | Frontend simple e intuitivo | Un estudiante sin instrucción previa entiende la pantalla en < 2 min |

## 4. Alcance incluido (MVP jugable)

1. **Lobby:** crear partida / unirse por código, elegir rol, elegir escenario.
2. **Red simulada:** topología de nodos (hosts, servidores, router, DB) con servicios y vulnerabilidades.
3. **Catálogo de técnicas** de atacante mapeadas a tácticas MITRE ATT&CK (abstraídas, sin payloads reales).
4. **Motor de simulación** autoritativo en el servidor (tick determinista + RNG con semilla).
5. **Detección** por anomalía (heurística que emula un TGNN) con *score* y alertas.
6. **Respuestas** del defensor: aislar nodo, terminar proceso, desplegar honeypot, bloquear IP.
7. **Dos agentes IA** (atacante y defensor) con bucle ReAct heurístico; *hook* opcional para LLM.
8. **Visualización:** grafo de red en vivo, feed de eventos, panel de razonamiento del agente, marcador.
9. **Condición de victoria:** por objetivos del atacante (exfil) o por contención del defensor (MTTD/MTTR) o por tiempo.
10. **Replay/resumen** al final de la partida.

## 5. Fuera de alcance (explícito)

- Cualquier ejecución real de código ofensivo, escaneo de red real, o integración con herramientas de pentesting.
- Sondas eBPF reales, XDP, captura de syscalls del sistema anfitrión.
- Persistencia multi-partida en base de datos (se usa estado en memoria; replay se exporta a JSON).
- Autenticación de usuarios / cuentas (la partida se protege por código efímero).
- Despliegue en internet público (diseñado para LAN del laboratorio; ver ADR-0007).

## 6. Actores

- **Jugador Atacante** (humano, Red Team).
- **Jugador Defensor** (humano, Blue Team).
- **Agente Atacante** (IA, autónomo/asistente).
- **Agente Defensor** (IA, autónomo/asistente).
- **Espectador** (opcional, solo lectura — p. ej. el docente).
- **Servidor de Simulación** (autoridad del estado; no es persona pero es el sistema).

## 7. Supuestos y restricciones

- Las dos PCs están en la **misma red local** (o pueden alcanzar al servidor por IP/puerto).
- Un solo lenguaje de implementación: **TypeScript** (servidor Node + frontend React/Vite).
- Sin dependencia de GPU, Linux ni privilegios de administrador.
- Debe arrancar con `npm install && npm run dev` en Windows, macOS o Linux.
