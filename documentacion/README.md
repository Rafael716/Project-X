# UNIVERSIDAD NACIONAL DE INGENIERÍA
### Facultad de Ingeniería Industrial y de Sistemas
#### Escuela Profesional de Ingeniería de Software

---

## PROYECTO INTEGRADOR DEL CURSO
### CONSTRUCCIÓN DE SOFTWARE II – SW707
**PROYECTO DE TEMA LIBRE ELEGIDO POR EL EQUIPO**

- **Tipo de documento:** Documento oficial para estudiantes
- **Semestre académico:** 7mo
- **Docente:** ANIBAL JAVIER GUILLEN VASQUEZ
- **Fecha:** 18/09/2026
- **Equipo:** Leonardo (Tech Lead Staff) y Rafael (Scrum Master Senior)

---

## 6. Ficha inicial de propuesta

| Campo | Contenido requerido |
| :--- | :--- |
| **Nombre del proyecto** | **Project X** |
| **Problema** | La respuesta humana en ciberseguridad toma horas o días; los ataques modernos comprometen redes en minutos. Los EDR/SIEM actuales lanzan demasiadas alertas falsas y no aplican defensas activas inmediatas por temor a tumbar el sistema. |
| **Usuarios/actores** | • **Humanos:** Analistas de SOC (Tier 2/3) y equipos Red/Blue.<br>• **Agentes:** Atacante autónomo (LLM + ReAct), Defensor. |
| **Objetivo** | Construir un entorno autónomo de simulación y combate cibernético en bucle cerrado que detecte ataques en menos de 100 ms. |
| **Alcance inicial** | 1. Sonda eBPF para capturar syscalls clave (`execve`, `connect`).<br>2. Conversión de eventos a grafo dinámico continuo (Proceso → Socket → Archivo).<br>3. Modelo TGNN base para detectar anomalías (port scans y reverse shells).<br>4. Agente atacante LLM con ejecución de 3 técnicas básicas de MITRE ATT&CK.<br>5. Aislamiento automático de red del contenedor atacado usando eBPF/XDP. |
| **Complejidad técnica** | • Filtrar miles de syscalls/segundo sin congelar el sistema ni saturar la GPU.<br>• Inferencia en grafos dinámicos en tiempo real (< 100 ms).<br>• Evitar alucinaciones de sintaxis en el LLM atacante.<br>• Prevenir falsos positivos que bloqueen procesos legítimos del sistema operativo. |
| **Datos** | • **Benignos:** Tráfico sintético simulado dentro del contenedor (navegación web, tareas cron).<br>• **Maliciosos:** Datasets públicos de linaje de kernel (DARPA OpTC) y ataques controlados con Atomic Red Team. |
| **Tecnología propuesta** | • **Kernel:** eBPF (C / Rust con Aya o Tetragon).<br>• **IA y Grafos:** Python, PyTorch Geometric Temporal (TGN).<br>• **Agente Atacante:** LangGraph / DSPy conectando con LLM (Llama 3 / DeepSeek local o API).<br>• **Infraestructura:** Docker/Mininet en Linux y Redis para streaming de eventos. |
| **Técnicas SW707** | 1. Machine Learning en Grafos (GNN / TGNN).<br>2. Agentes Inteligentes con Planificación Heurística / ReAct.<br>3. Arquitecturas Dirigidas por Eventos (EDA) de ultra baja latencia.<br>4. Razonamiento Neuro-Simbólico (reglas formales de seguridad + IA probabilística). |
| **Evolución prevista** | 1. Integración de Monte Carlo Tree Search (MCTS) en el atacante para movimientos laterales sigilosos.<br>2. Decepción activa (desvío a honeypots señuelo antes de matar procesos).<br>3. Auto-juego continuo (Self-play) donde atacante y defensor evolucionan solos.<br>4. Dashboard interactivo con el grafo de ataque en 3D. |
