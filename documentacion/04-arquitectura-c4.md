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
    Container(web, "Web App (SPA)", "TypeScript, React, Vite", "Lobby, grafo en vivo, terminal, paneles, marcador de juego")
    Container(srv, "Servidor de Simulación", "Python 3.11, FastAPI, wsproto", "Autoridad del estado: barricada, motor por ticks, detección, agentes, resiliencia")
    ContainerDb(mem, "Estado en memoria", "Objetos Python", "Partidas vivas; export a JSON para replay")
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
  Container_Boundary(srv, "Servidor de Simulación (backend/, Python)") {
    Component(gw, "Gateway WS", "app.py", "Conexiones async, salas, reconexión, candado por-socket, captura de errores")
    Component(barr, "Barricada", "barricada.py", "Valida todo input hostil en 3 capas (Semana 4)")
    Component(res, "Resiliencia", "resiliencia.py", "Circuit breaker, contrapresión, proxy que degrada (Semana 7)")
    Component(obs, "Observabilidad", "observabilidad.py", "Logs JSON + correlation_id (Semana 5)")
    Component(match, "Match Manager", "match.py", "Ciclo de vida de partidas, roles, bucle de tick")
    Component(engine, "Motor de Simulación", "engine.py", "Ticks, PRNG sembrado, energía/puntaje, invariantes (Semana 3)")
    Component(atkcat, "Técnicas / Respuestas", "techniques.py / response.py", "Jerarquía polimórfica (Semana 2)")
    Component(detect, "Detector de Anomalía", "detector.py", "Score por nodo, alertas, FP (surrogate TGNN)")
    Component(agents, "Agentes ReAct", "agents.py", "Política atacante/defensor; hook LLM opcional")
    Component(con, "Contratos", "contratos.py", "Pre/post/invariantes ejecutables (Semana 3)")
    Component(esc, "Escenarios", "scenario.py", "Niveles (PYMES-01, DATACENTER-02)")
  }
  Rel(gw, barr, "valida cada mensaje")
  Rel(gw, obs, "loguea 1 vez (frontera)")
  Rel(gw, match, "enruta intents validados")
  Rel(match, res, "envuelve agentes con proxy")
  Rel(match, engine, "crea/avanza")
  Rel(engine, atkcat, "despacha técnica/respuesta (polimorfismo)")
  Rel(engine, detect, "alimenta eventos")
  Rel(engine, agents, "pide decisión (autoplay)")
  Rel(engine, con, "verifica invariantes por tick")
  Rel(match, esc, "carga nivel")
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
    N["Python + FastAPI: Servidor de Simulación\n0.0.0.0:8787\n+ sirve la Web App buildeada (web/dist)"]
  end
  subgraph PCB["PC B - Defensor"]
    BB["Navegador"]
  end
  BA -- "ws://IP-HOST:8787" --> N
  BB -- "ws://IP-HOST:8787" --> N
```

> **Nota de despliegue:** en producción de clase, el servidor FastAPI también sirve el build estático de la web (`web/dist`), así ambas PCs solo necesitan `http://IP-HOST:8787`. En desarrollo, Vite corre aparte en :5174 y el servidor en :8787.
