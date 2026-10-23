# Changelog — Project X

Evolución exigida por el curso: `v0.x → v1.0 (Parcial) → v1.x → v2.0 (Final)`.
El foco no es agregar funciones, sino **cómo se construye y evoluciona** el
software. Formato basado en [Keep a Changelog](https://keepachangelog.com/es/).

## [2.0.0] — Examen Final (Unidades 3 y 4)

Evolución de la base aprobada en el Parcial. No se reinició el proyecto.

### Añadido
- **Estados / table-driven** (`backend/estados.py`): el ciclo de vida de la
  partida (`lobby→lista→en_curso⇄pausada→terminada`) pasó de `if` dispersos a
  una **tabla de transiciones** única; transición inválida = fail-fast.
- **Configuración externalizada + feature flags** (`backend/config.py`,
  `.env.example`): toda la config se lee de entorno/`.env` en un solo módulo;
  4 feature flags encienden/apagan capacidades sin recompilar.
- **Internacionalización** (`backend/i18n.py`): mensajes al jugador en `es`/`en`
  vía `PX_LANG`, con fallback.
- **API REST** (`/api/version`, `/api/config`, `/api/escenarios`,
  `/api/tecnicas`, `/api/partidas`): lectura para clientes/tableros externos.
- **Contenedores**: `Dockerfile` multi-stage + `docker-compose.yml`.
- **Benchmark de rendimiento** (`benchmarks/bench_tick.py`): baseline
  0.245 ms/tick (RNF-02 exige < 50 ms → margen ×204), con `--profile`.
- **Characterization tests** (`backend/test_caracterizacion.py`): fijan el
  comportamiento determinista actual como red de seguridad del refactor.
- Documento técnico final: `documentacion/08-evolucion-v2.md`.

### Cambiado
- `engine.py` lee las perillas de balance desde `config.py` (antes constantes).
- `app.py` anuncia catálogos ya filtrados por feature flags y traduce mensajes.

## [1.0.0] — Examen Parcial (Unidades 1 y 2)

Primera versión funcional, verificable y robusta.

### Añadido
- Backend Python/FastAPI con motor de simulación autoritativo por ticks
  deterministas (PRNG sembrado) y WebSockets.
- **Diseño por Contrato** (`contratos.py`): pre/post/invariantes verificados en
  ejecución cada tick.
- **Programación defensiva / barricada** (`barricada.py`): validación de 3 capas
  en la frontera (tipo/tamaño → rango/enum → semántica).
- **Jerarquía de excepciones + logs JSON** (`errores.py`, `observabilidad.py`):
  política de errores por capas, `correlation_id`/MDC.
- **Concurrencia** (`app.py`): candado por-socket, tick atómico.
- **Resiliencia** (`resiliencia.py`): circuit breaker, contrapresión
  (token bucket), proxy que degrada a política mínima.
- **Polimorfismo** (`techniques.py`, `response.py`): catálogo extensible sin
  tocar el motor (enlace dinámico).
- Capa de juego: energía, puntaje, combos, 2 niveles; frontend React.
- 15 pruebas automatizadas deterministas.

## [0.x] — Prototipo inicial

Topología simulada, kill chain básica y detector de anomalía; sin contratos ni
resiliencia. Sirvió para validar la idea antes de la construcción robusta.

---

## Clasificación de mantenimiento (ISO/IEC 14764)

Cuatro cambios representativos entre el Parcial y el Final, uno por tipo:

| Tipo | Cambio | Dónde |
|------|--------|-------|
| **Correctivo** | `Match.pausar` cambiaba estado sin validar la transición; ahora pasa por la tabla y una pausa desde `terminada` ya no corrompe el estado. | `match.py`, `estados.py` |
| **Preventivo** | Characterization tests que congelan el curso determinista antes de refactorizar el motor (evitan regresiones futuras). | `test_caracterizacion.py` |
| **Perfectivo** | Perillas de balance y catálogos movidos a configuración externalizada + feature flags (ajuste sin recompilar). | `config.py` |
| **Adaptativo** | Contenerización (Docker) e i18n `es`/`en` para desplegar y usar en entornos distintos. | `Dockerfile`, `i18n.py` |
