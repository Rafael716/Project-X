# Project X — Simulador de Ciber-Combate (académico)

Juego/simulador de **ataque vs defensa** sobre una red simulada, para **dos PCs** conectadas por web: una persona opera el **Atacante** (Red Team) y otra el **Defensor** (Blue Team). Cada lado puede jugarlo una persona o su **agente de IA** (bucle ReAct trazable). Curso **SW707 – Construcción de Software II**, UNI-FIIS.

> ⚠️ **Es una simulación con fines educativos.** No ejecuta ataques reales, no escanea redes, no toca el kernel ni contiene malware. Toda la "actividad" son eventos sintéticos en memoria. La correspondencia con la propuesta original (eBPF/TGNN/XDP) está en [`documentacion/06-modelo-de-simulacion.md`](documentacion/06-modelo-de-simulacion.md).

## Qué incluye

- **Red simulada** (router, PCs, servidor web, base de datos) con servicios, CVEs pedagógicos y archivos sensibles (.env, docs, bases de datos).
- **Kill chain** estilo MITRE ATT&CK: recon → acceso inicial → escalada → movimiento lateral → exfiltración.
- **Terminal interactiva en vivo (Streaming CLI)**: Cada computadora ve en vivo qué comando ejecuta su agente o jugador (Kali C2 CLI para el Atacante, SecOps eBPF Console para el Defensor).
- **Extracción profunda de vulnerabilidades y Loot**: El atacante busca y sustrae variables `.env`, tokens, documentos corporativos y dumps SQL en vivo.
- **Detección por anomalía explicable (TGNN surrogate)**: Score por host + desglose de señales en tiempo real.
- **Respuestas activas multicapa**: Aislar nodo (eBPF), terminar proceso (SIGKILL), parchear .env y rotar secretos, desplegar honeypots y bloquear IPs hostiles.
- **Dos agentes IA (ReAct)**: Atacante y Defensor con trazabilidad de razonamiento, envueltos en un *proxy de resiliencia* que degrada sin congelar la partida si fallan.
- **Capa de juego**: energía por lado (presupuesto de acciones), puntaje con combos, marcador *tug-of-war* en vivo y **dos niveles** (PYMES-01 normal, DATACENTER-02 difícil).
- **Métricas Senior Staff**: MTTD, MTTR, disponibilidad de red %, volumen de exfiltración y replay JSON exportable.
- **Construido con rigor**: barricada de entrada, Diseño por Contrato con invariantes en ejecución, logs JSON con `correlation_id`, concurrencia segura y patrones de resiliencia (circuit breaker, contrapresión).

## Stack

- **Backend**: Python 3.11+ con **FastAPI**, **WebSockets** y bucle de simulación autoritativo (`backend/app.py`). Construcción robusta aplicando las 7 sesiones del curso: barricada de entrada, Diseño por Contrato, jerarquía de excepciones, logs JSON, concurrencia segura y patrones de resiliencia (ver [`documentacion/07-construccion-sw707.md`](documentacion/07-construccion-sw707.md)).
- **Frontend**: TypeScript con **React**, **Vite** y CSS Cyber SOC Dark Mode (`web/`).
- **Contrato tipado**: [`shared/protocol.ts`](shared/protocol.ts) — única fuente de verdad de la forma de datos.

```
Project-X/
├─ backend/         # Servidor Python FastAPI: barricada, motor, detector, agentes, resiliencia, observabilidad
├─ shared/          # Contrato tipado front ↔ back (protocol.ts)
├─ web/             # SPA React + Vite (terminal en vivo, topología, paneles, loot, marcador de juego)
└─ documentacion/   # Visión, requerimientos, 20 ADR, C4, diagramas, modelo y trazabilidad del curso
```

## Cómo correr

Requisitos: **Python 3.10+** y **Node 18+** (o solo **Docker**). Dos PCs en la **misma red local (LAN)**.

### Opción A — Docker (lo más simple)

```bash
docker compose up --build        # web + WebSocket en http://localhost:8787
```

Copia `.env.example` a `.env` para ajustar puertos, idioma o feature flags; es opcional.

### Opción B — Local sin Docker

En la **PC host** (la que hospeda la partida):

```bash
# 1) Construir el frontend web
cd web && npm install && npm run build

# 2) Levantar el backend FastAPI (sirve la web construida y los WebSockets en el puerto 8787)
cd ../backend
pip install -r requirements.txt
python app.py
```

El servidor queda disponible en `http://0.0.0.0:8787`.

- En la PC host abre `http://localhost:8787` y pulsa **Crear partida** (elige rol).
- En la otra PC abre `http://IP-DE-LA-PC-HOST:8787`, pulsa **Unirse** con el código y elige el rol opuesto.
- Averigua la IP del host: Windows `ipconfig` → "Dirección IPv4"; Linux/mac `hostname -I`.

### Opción C — Desarrollo (Hot Reload)

Dos terminales en la PC host:

```bash
# Terminal 1: Backend FastAPI
cd backend && uvicorn app:app --host 0.0.0.0 --port 8787 --reload

# Terminal 2: Frontend Vite
cd web && npm run dev -- --host
```

### Pruebas de Invariantes

```bash
cd backend && pytest        # 18 tests: invariantes, barricada, contratos, resiliencia y caracterización
```

### Configuración y API

- Variables de entorno / `.env` (ver `.env.example`): puertos, `PX_LANG` (es/en),
  perillas de balance y feature flags (`PX_FEATURE_*`). Todo se lee en `backend/config.py`.
- API REST de lectura: `GET /api/version`, `/api/config`, `/api/escenarios`,
  `/api/tecnicas`, `/api/partidas`, más `/health` y `/metrics`.

## Cómo se juega (2 min)

1. **Lobby:** uno crea la partida y comparte el código; el otro se une con el rol contrario. Cada quien elige jugar **manual** o dejar su **agente IA**. Ambos marcan *listo* → *Iniciar*.
2. **Atacante:** clic en un nodo → elige una técnica aplicable. Avanza la kill chain hacia la **base de datos** para exfiltrar. Ojo: las técnicas ruidosas te delatan.
3. **Defensor:** vigila el **score de anomalía** y las **alertas**; aplica respuestas. Aislar o bloquear nodos sanos **baja tu disponibilidad** (falsos positivos penalizados).
4. **Fin:** gana el atacante si roba suficientes datos; gana el defensor si contiene y mantiene la red disponible hasta el final. Se muestran MTTD/MTTR y puedes descargar el replay.

## Documentación

Índice completo en [`documentacion/00-indice.md`](documentacion/00-indice.md): visión y alcance, requerimientos (RF/RNF), 20 ADR, diagramas C4, casos de uso, flujo, estados, secuencia, el modelo de simulación, la trazabilidad del curso (Etapa I) y el documento técnico final (Etapa II). Historial de versiones en [`CHANGELOG.md`](CHANGELOG.md).
