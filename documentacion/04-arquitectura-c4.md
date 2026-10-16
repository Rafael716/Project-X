# Project X — Arquitectura (modelo C4)

Diagramas en Mermaid (se renderizan en GitHub/VS Code). Cuatro niveles: Contexto, Contenedores, Componentes, y despliegue en LAN.

## Nivel 1 — Contexto

```mermaid
C4Context
  title Project X - Contexto
  Person(atk, "Jugador Atacante", "Red Team, PC A")
  Person(def, "Jugador Defensor", "Blue Team, PC B")
  Person(spec, "Espectador / Docente", "Solo lectura (opcional)")
  System(px, "Project X", "Simulador de ciber-combate en bucle cerrado")
  Rel(atk, px, "Opera agente atacante / acciones", "WebSocket")
  Rel(def, px, "Opera agente defensor / respuestas", "WebSocket")
  Rel(spec, px, "Observa la partida", "WebSocket")
```

## Nivel 2 — Contenedores

```mermaid
C4Container
  title Project X - Contenedores
  Person(atk, "Atacante")
  Person(def, "Defensor")
  System_Boundary(px, "Project X") {
    Container(web, "Web App (SPA)", "TypeScript, React, Vite", "Lobby, grafo en vivo, feed, paneles de agente y acciones")
    Container(srv, "Servidor de Simulación", "TypeScript, Node, ws", "Autoridad del estado: motor por ticks, detección, agentes, difusión")
    ContainerDb(mem, "Estado en memoria", "Objetos JS", "Partidas vivas; export a JSON para replay")
  }
  Rel(atk, web, "Usa", "HTTPS/HTTP")
  Rel(def, web, "Usa", "HTTPS/HTTP")
  Rel(web, srv, "Intents y suscripción a estado", "WebSocket JSON")
  Rel(srv, mem, "Lee/escribe", "en proceso")
```

## Nivel 3 — Componentes del Servidor

```mermaid
C4Component
  title Servidor de Simulación - Componentes
  Container_Boundary(srv, "Servidor de Simulación") {
    Component(gw, "Gateway WS", "ws", "Conexiones, salas por código, reconexión")
    Component(match, "Match Manager", "TS", "Ciclo de vida de partidas, roles, listo/inicio")
    Component(engine, "Motor de Simulación", "TS", "Bucle de ticks, PRNG sembrado, aplica intents")
    Component(net, "Modelo de Red", "TS", "Nodos, aristas, servicios, vulnerabilidades, estados")
    Component(atkcat, "Catálogo de Técnicas", "TS", "Tácticas MITRE abstraídas y sus efectos")
    Component(detect, "Detector de Anomalía", "TS", "Score por nodo/arista, alertas, FP configurables")
    Component(resp, "Motor de Respuesta", "TS", "Aislar, matar, honeypot, bloquear IP y sus costos")
    Component(agents, "Agentes ReAct", "TS", "Política atacante/defensor; hook LLM opcional")
    Component(score, "Scoring y Métricas", "TS", "MTTD, MTTR, disponibilidad, exfil, win-condition")
  }
  Rel(gw, match, "enruta intents")
  Rel(match, engine, "crea/avanza")
  Rel(engine, net, "muta estado")
  Rel(engine, atkcat, "resuelve técnica")
  Rel(engine, detect, "alimenta eventos")
  Rel(engine, resp, "aplica respuesta")
  Rel(engine, agents, "pide decisión (autoplay)")
  Rel(engine, score, "actualiza métricas")
  Rel(engine, gw, "difunde estado+eventos")
```

## Nivel 3 — Componentes de la Web App

```mermaid
C4Component
  title Web App - Componentes
  Container_Boundary(web, "Web App") {
    Component(ws, "Cliente WS", "TS", "Conexión, reconexión, envío de intents")
    Component(storeC, "Store de Estado", "TS (reducer)", "Estado de partida recibido del servidor")
    Component(lobby, "Lobby", "React", "Crear/unir, elegir rol/escenario, listo")
    Component(graph, "Vista de Grafo", "React + SVG/Canvas", "Topología viva, estados de nodo, score")
    Component(feed, "Feed de Eventos", "React", "Línea de tiempo de eventos y alertas")
    Component(panelA, "Panel Atacante", "React", "Técnica + objetivo; autoplay; kill chain")
    Component(panelD, "Panel Defensor", "React", "Respuestas; alertas; costo de FP")
    Component(reason, "Panel de Razonamiento IA", "React", "Traza ReAct del agente")
    Component(summary, "Resumen/Replay", "React", "Métricas finales, descarga JSON")
  }
  Rel(ws, storeC, "despacha estado")
  Rel(storeC, graph, "renderiza")
  Rel(storeC, feed, "renderiza")
  Rel(panelA, ws, "envía intent")
  Rel(panelD, ws, "envía intent")
```

## Nivel 4 — Despliegue (LAN del laboratorio)

```mermaid
flowchart LR
  subgraph PCA["PC A - Atacante"]
    BA["Navegador\n(Web App servida por Vite/estático)"]
  end
  subgraph PCH["PC Host (puede ser PC A o B)"]
    N["Node: Servidor de Simulación\n0.0.0.0:8787\n+ sirve la Web App buildeada"]
  end
  subgraph PCB["PC B - Defensor"]
    BB["Navegador"]
  end
  BA -- "ws://IP-HOST:8787" --> N
  BB -- "ws://IP-HOST:8787" --> N
```

> **Nota de despliegue:** en producción de clase, el servidor Node también sirve el build estático de la web, así ambas PCs solo necesitan `http://IP-HOST:8787`. En desarrollo, Vite corre aparte en :5174 y el servidor en :8787.
