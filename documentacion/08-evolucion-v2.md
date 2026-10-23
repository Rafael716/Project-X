# Project X — Documento Técnico Final (Etapa II / v2.0)

Evolución de la versión aprobada en el Parcial (v1.0) a la versión final (v2.0),
aplicando las **Unidades 3 y 4** del curso SW707. No se reinició el proyecto: se
evolucionó el mismo producto (ver [CHANGELOG](../CHANGELOG.md), regla del brief
§14). Este documento sigue la estructura del *Documento Técnico Final* (§18 del
brief). La trazabilidad de la Etapa I (Unidades 1-2) está en
[07-construccion-sw707](07-construccion-sw707.md).

```
FUNCIONAR → VERIFICARSE → FALLAR BIEN → RESISTIR → CONCURRIR → OBSERVARSE →
            OPTIMIZARSE → REFACTORIZARSE → MANTENERSE → EVOLUCIONAR
   └── Etapa I (v1.0) ──┘               └──────── Etapa II (v2.0) ────────┘
```

## 1. Resumen de la evolución desde el Parcial

| Unidad 3-4 | Qué se hizo | Evidencia |
|------------|-------------|-----------|
| Estados / tablas | Ciclo de vida de la partida → tabla de transiciones | `backend/estados.py` |
| Configuración + feature flags | Config externalizada en un módulo; 4 flags | `backend/config.py`, `.env.example` |
| Internacionalización | Mensajes al jugador `es`/`en` | `backend/i18n.py` |
| Distribución / API | REST de solo lectura junto al WebSocket | `backend/app.py` (`/api/*`) |
| Contenedores | Imagen única multi-stage | `Dockerfile`, `docker-compose.yml` |
| Observabilidad | (ya en v1.0) logs JSON + `/metrics` | `backend/observabilidad.py` |
| Rendimiento | Baseline + profiling | `benchmarks/bench_tick.py` |
| Refactorización | Smells removidos con tests de respaldo | §8 |
| Mantenimiento | 4 cambios clasificados ISO 14764 | [CHANGELOG](../CHANGELOG.md) |
| Legacy | Characterization tests | `backend/test_caracterizacion.py` |
| Ingeniería reversa | Arquitectura recuperada del código | §11 |
| Reingeniería | Estrategia de modernización incremental | §12 |

## 2. Arquitectura inicial vs. evolucionada

- **Inicial (v1.0):** gateway WebSocket + motor autoritativo + barricada +
  resiliencia + observabilidad. Config en constantes; estados con `if`; sin REST,
  sin contenedor, sin i18n. (C4 en [04-arquitectura-c4](04-arquitectura-c4.md).)
- **Evolucionada (v2.0):** se añaden tres módulos transversales nuevos
  (`config`, `estados`, `i18n`), una superficie **REST** de lectura, el
  empaquetado **Docker** y la carpeta `benchmarks/`. El núcleo (engine/match) no
  cambió de responsabilidad; solo pasó a **leer** config y a **disparar** eventos
  de estado en vez de fijarlos a mano. Diagrama de dependencias en §11.

## 3. Estados y construcción basada en tablas

`backend/estados.py` define `TRANSICIONES: (estado, evento) → estado`. `match.py`
ya no asigna estados: llama `estados.transita(self.estado, evento)`. Una
transición no declarada lanza `ReglaDeJuego` (fail-fast), así "pausar una partida
terminada" es inalcanzable en silencio. Decisión: **ADR-0015**. (El nodo de red
tiene además su propia FSM `limpio→sondeado→comprometido→aislado` en
`engine.sincronizar_estado`, doc 06 §3.)

Check: `python backend/estados.py` recorre el camino feliz hasta `terminada` y
verifica que una transición ilegal se rechaza.

## 4. Configuración e internacionalización

- **Configuración (ADR-0016):** `config.py` lee entorno + `.env` una vez, con
  defaults, y es el único módulo que toca `os.environ`. Perillas de balance
  (energía, puntaje meta, umbral del detector), puertos, nivel de log, idioma y
  **feature flags** salen de ahí. `/api/config` la expone en caliente. Plantilla
  documentada en `.env.example`; secretos fuera del repo (`.gitignore`).
- **Feature flags:** `FEATURES` enciende/apaga capacidades (honeypot, canary,
  phishing, nivel difícil) **sin recompilar**. El servidor solo anuncia los ids
  activos y la barricada rechaza los apagados — defensa en profundidad.
- **i18n (ADR-0017):** `i18n.t(clave)` traduce los mensajes al jugador a `es`/`en`
  según `PX_LANG`, con fallback. Alcance acotado y justificado (no gettext).

## 5. Distribución e integración

**API REST de solo lectura** (ADR-0018) en el mismo FastAPI, sin tocar la
autoridad del WebSocket (ADR-0003):

| Método | Ruta | Devuelve |
|--------|------|----------|
| GET | `/api/version` | producto, versión, periodo de tick |
| GET | `/api/config` | config efectiva + feature flags (sin secretos) |
| GET | `/api/escenarios` | niveles disponibles (filtrados por flag) |
| GET | `/api/tecnicas` | catálogo de técnicas/respuestas activas |
| GET | `/api/partidas` | partidas vivas (código, estado, tick, ganador) |
| GET | `/health`, `/metrics` | salud y contadores (observabilidad) |

Ninguna muta estado (CQS a nivel de transporte). Integrable con `curl`/fetch.

## 6. Contenedores

`Dockerfile` multi-stage (ADR-0019): etapa Node construye `web/dist`, etapa
Python corre el backend y sirve el build. `docker compose up --build` deja todo
en `http://localhost:8787`. `.env` es opcional (compose `required: false`);
si falta, `config.py` usa defaults. `HEALTHCHECK` consulta `/health`.

## 7. Observabilidad, profiling y rendimiento

- **Observabilidad** (ya en v1.0, Sesión 5): logs JSON con `correlation_id`/MDC
  (`observabilidad.py`), contadores en `/metrics`.
- **Baseline (RNF-02: < 50 ms/tick):** `benchmarks/bench_tick.py` mide
  throughput. Medición 2026-10-23 (autoplay, datacenter02):

  ```
  10 000 ticks en 2.449 s  →  4 084 ticks/s  |  0.245 ms/tick
  RNF-02 (<50 ms/tick): OK  (margen ×204)
  ```

- **Profiling:** `bench_tick.py --profile` (cProfile, orden por tiempo
  acumulado) ubica el cuello de botella. Con holgura ×204 no se optimizó
  prematuramente (YAGNI): la perilla queda para cuando el presupuesto apriete.

## 8. Refactorización y deuda técnica

*Code smells* corregidos con las pruebas de respaldo (18 tests + characterization):

- **Lógica de estado dispersa** (`if estado == ...` en `match.py`) → tabla única
  (`estados.py`). Respaldo: `test_caracterizacion`, self-check de `estados.py`.
- **Constantes mágicas de balance** en `engine.py` → `config.py`. Respaldo:
  los 18 tests siguen verdes tras mover las perillas.
- **Lectura de entorno dispersa** (`os.environ` en `app.py`) → `config.py` como
  única frontera de configuración.

Deuda reconocida (marcada con comentarios `ponytail:`): el contrato tipado
`shared/protocol.ts` se mantiene a mano en dos lados (lo cubren la barricada y
los tests); i18n no cubre pluralización (no aplica al dominio).

## 9. Mantenimiento y análisis de impacto

Cuatro cambios clasificados por tipo (ISO/IEC 14764) con su alcance, en el
[CHANGELOG](../CHANGELOG.md): **correctivo** (transición de pausa validada),
**preventivo** (characterization tests), **perfectivo** (config + flags),
**adaptativo** (Docker + i18n). Impacto acotado: los tres módulos nuevos son
transversales y el núcleo solo pasó a *leerlos*, por eso el golden determinista
no cambió (lo confirma `test_caracterizacion`).

## 10. Legacy y pruebas de caracterización

`backend/test_caracterizacion.py` (ADR-0020) fija el curso determinista actual
como *golden* por `(escenario, semilla)`. Es la red de seguridad del refactor:
afirma lo que el sistema **hace hoy**, no lo que debería. Si un cambio altera el
curso, revienta y obliga a decidir si fue intencional. El archivo documenta cómo
re-generar el golden.

## 11. Ingeniería reversa (arquitectura recuperada del código)

Grafo de dependencias de import recuperado del backend (lo que importa a lo que):

```
app.py ─┬─ barricada ─ errores
        ├─ match ─┬─ engine ─┬─ config
        │         │          ├─ detector
        │         │          ├─ rng
        │         │          ├─ techniques ─ errores
        │         │          ├─ response
        │         │          └─ contratos ─ config, errores, observabilidad
        │         ├─ estados ─ errores
        │         ├─ agents ─ techniques
        │         ├─ resiliencia ─ observabilidad
        │         └─ scenario
        ├─ config ├─ i18n ─ config
        ├─ observabilidad  ├─ resiliencia  └─ scenario
```

Lecturas de la recuperación: (1) `errores` y `config` son las hojas de las que
todo depende — cambiarlas tiene máximo impacto. (2) El flujo de datos es
unidireccional `app → match → engine`; no hay ciclos. (3) La frontera (`app`,
`barricada`) está separada del núcleo (`engine`), como pide ADR-0003/0010. El C4
completo (contexto/contenedores/componentes) está en
[04-arquitectura-c4](04-arquitectura-c4.md); este grafo es la vista recuperada
*desde el código* que la confirma.

## 12. Reingeniería y estrategia de modernización

La modernización fue **incremental y sin big-bang**: cada módulo nuevo
(`config`, `estados`, `i18n`) se introdujo detrás de los tests existentes, se
verificó verde, y recién entonces el núcleo pasó a usarlo. El patrón aplicado es
*strangler* a pequeña escala: la lógica vieja (constantes, `if` de estado) se
reemplaza pieza por pieza por la nueva, nunca de golpe, con el golden de
caracterización garantizando que el comportamiento observable no cambia. La
estrategia a futuro (si creciera): extraer el motor a un paquete reutilizable y
el detector a un servicio aparte solo si un segundo consumidor lo justifica
(hoy sería distribución artificial — el brief §9 permite justificarlo así).

## 13. Pruebas y regresión

`cd backend && pytest` → **18 pruebas** verdes: 15 de contrato/invariantes/
resiliencia (Etapa I) + 3 de caracterización (Etapa II). Self-checks ejecutables
en `config.py`, `estados.py`, `i18n.py` y `bench_tick.py`. Determinismo
(misma semilla ⇒ misma partida) verificado tanto en `test_engine` como en
`test_caracterizacion`.

## 14. Métricas antes / después

| Métrica | v1.0 (Parcial) | v2.0 (Final) |
|---------|----------------|--------------|
| Pruebas automatizadas | 15 | 18 (+3 caracterización) |
| Módulos backend | 15 | 18 (+config, estados, i18n) |
| Superficie de integración | WebSocket | WebSocket + 5 endpoints REST |
| Config en código vs. externa | constantes | entorno/`.env` + 4 feature flags |
| Idiomas de UI | es | es, en |
| Empaquetado | manual (pip+npm) | manual **o** `docker compose up` |
| Throughput del tick | — (no medido) | 0.245 ms/tick (baseline, ×204 RNF-02) |

## 15. Conclusiones y lecciones aprendidas

- La construcción robusta de la Etapa I (contratos, tests, barricada) **pagó** en
  la Etapa II: refactorizar estados y mover la config fue barato y seguro porque
  los invariantes y el golden atrapaban cualquier regresión.
- Table-driven y config externalizada eliminan clases enteras de bugs
  (transiciones ilegales, constantes mágicas) con muy poco código.
- El brief premia *cómo* se construye: varias competencias (i18n, distribución)
  se demuestran mejor con un alcance acotado y **justificado** que con maquinaria
  que el dominio no necesita (§9 del brief).
