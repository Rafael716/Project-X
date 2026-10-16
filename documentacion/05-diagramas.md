# Project X — Diagramas (casos de uso, flujo, estados, secuencia)

## 1. Casos de uso

```mermaid
flowchart TB
  atk(("Jugador\nAtacante"))
  def(("Jugador\nDefensor"))
  spec(("Espectador"))
  subgraph PX["Project X"]
    UC1["Crear partida"]
    UC2["Unirse por código"]
    UC3["Elegir rol y escenario"]
    UC4["Marcar listo / Iniciar"]
    UC5["Ejecutar técnica de ataque"]
    UC6["Activar autoplay del agente"]
    UC7["Ver grafo y feed en vivo"]
    UC8["Aplicar respuesta defensiva"]
    UC9["Revisar alertas y score"]
    UC10["Ver resumen y descargar replay"]
  end
  atk --- UC1 & UC2 & UC3 & UC4 & UC5 & UC6 & UC7 & UC10
  def --- UC2 & UC3 & UC4 & UC6 & UC7 & UC8 & UC9 & UC10
  spec --- UC2 & UC7 & UC10
```

### Caso de uso detallado: UC5 — Ejecutar técnica de ataque
- **Actor:** Jugador Atacante (o Agente Atacante en autoplay).
- **Precondición:** partida en estado *en curso*; es el lado atacante quien actúa.
- **Flujo principal:**
  1. El atacante selecciona un **nodo objetivo** y una **técnica** aplicable.
  2. El cliente envía `intent:attack{tecnica, nodoId}`.
  3. El servidor valida (técnica aplicable al estado/servicio del nodo).
  4. En el siguiente tick, resuelve éxito/fallo (vuln del nodo × postura defensiva × PRNG).
  5. Genera eventos; actualiza estado de compromiso y métricas; difunde.
- **Flujos alternativos:** 3a técnica no aplicable → error de validación; 4a defensor tenía el nodo aislado → la técnica falla por contención.
- **Postcondición:** el nodo puede avanzar en la kill chain; el defensor ve nuevos eventos y posible alerta.

### Caso de uso detallado: UC8 — Aplicar respuesta defensiva
- **Actor:** Jugador/Agente Defensor.
- **Precondición:** partida *en curso*.
- **Flujo principal:** elige respuesta (aislar/matar/honeypot/bloquear IP) y objetivo → `intent:respond{...}` → el servidor la aplica en el tick → cambia estado y afecta al atacante.
- **Regla de costo:** si el objetivo era legítimo (sin compromiso real), baja la **disponibilidad** (falso positivo penalizado — RF-33).

## 2. Diagrama de flujo — resolución de un tick

```mermaid
flowchart TD
  A["Inicio de tick n"] --> B["Recolectar intents encolados\n(atacante + defensor)"]
  B --> C{"¿Lado en autoplay?"}
  C -- "sí" --> D["Agente ReAct genera intent\n(reason -> act)"]
  C -- "no" --> E["Usar intents del jugador"]
  D --> F["Validar intents"]
  E --> F
  F --> G["Generar tráfico benigno (ruido)"]
  G --> H["Aplicar intents del atacante\n(resolver técnica con PRNG)"]
  H --> I["Aplicar respuestas del defensor\n(aislar/matar/honeypot/bloquear)"]
  I --> J["Actualizar grafo dinámico\n(nodos, aristas, estados)"]
  J --> K["Detector: recalcular score + alertas"]
  K --> L["Scoring: MTTD, MTTR, disponibilidad, exfil"]
  L --> M{"¿Condición de victoria\no fin de tiempo?"}
  M -- "sí" --> N["Estado = terminada\nCalcular resumen"]
  M -- "no" --> O["Difundir estado + eventos a clientes"]
  N --> O
  O --> P["Fin de tick n -> n+1"]
```

## 3. Diagrama de estados — Partida

```mermaid
stateDiagram-v2
  [*] --> Lobby
  Lobby --> Lista: ambos roles presentes y listos
  Lista --> EnCurso: host inicia (RF-05)
  EnCurso --> EnCurso: tick (sim avanza)
  EnCurso --> Pausada: host pausa
  Pausada --> EnCurso: host reanuda
  EnCurso --> Terminada: win-condition / fin de tiempo
  Pausada --> Terminada: host cancela
  Terminada --> [*]
  note right of EnCurso
    Difunde estado cada tick (4 Hz)
    Acepta intents validados
  end note
```

## 4. Diagrama de estados — Nodo de la red

```mermaid
stateDiagram-v2
  [*] --> Limpio
  Limpio --> Sondeado: recon exitoso
  Sondeado --> Comprometido: acceso inicial/escalada exitosa
  Comprometido --> Comprometido: movimiento lateral / exfil
  Limpio --> Aislado: respuesta defensiva
  Sondeado --> Aislado: respuesta defensiva
  Comprometido --> Aislado: respuesta defensiva (contención)
  Aislado --> Limpio: remediado (si no había compromiso real)
  Aislado --> Comprometido: reconectado sin remediar
  Comprometido --> Honeypot: desviado a señuelo
  note right of Aislado
    Si el nodo era legitimo/sano:
    penaliza disponibilidad (FP)
  end note
```

## 5. Diagrama de secuencia — enfrentamiento típico

```mermaid
sequenceDiagram
  participant A as Cliente Atacante
  participant S as Servidor (Motor)
  participant D as Cliente Defensor
  A->>S: intent:attack{recon, nodo7}
  Note over S: tick: resuelve con PRNG -> éxito
  S-->>A: estado{nodo7=sondeado} + evento
  S-->>D: estado{nodo7=sondeado} + evento
  Note over S: detector sube score de nodo7
  S-->>D: alerta{nodo7, score=0.72}
  D->>S: intent:respond{aislar, nodo7}
  Note over S: tick: nodo7 aislado -> futuros ataques fallan
  S-->>A: estado{nodo7=aislado}
  S-->>D: estado{nodo7=aislado} + MTTR actualizado
  A->>S: intent:attack{exfil, nodo7}
  Note over S: nodo aislado -> técnica falla (contención)
  S-->>A: evento{fallo: nodo aislado}
```

## 6. Ciclo de vida del agente ReAct (atacante o defensor)

```mermaid
flowchart LR
  OBS["Observación\n(estado + eventos del tick)"] --> REASON["Razonar\n(evaluar opciones segun objetivo)"]
  REASON --> ACT["Actuar\n(emitir 1 intent)"]
  ACT --> WAIT["Esperar resultado del tick"]
  WAIT --> OBS
```
