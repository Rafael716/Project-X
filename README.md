# Project X

## Sistema Autónomo de Simulación y Defensa Cibernética

Project X es un entorno experimental de ciberseguridad orientado a la **detección y respuesta autónoma ante comportamientos maliciosos** en un laboratorio controlado.

El proyecto busca integrar **eBPF, análisis de grafos, aprendizaje automático y agentes inteligentes** para construir un ciclo cerrado de ataque y defensa.


---

## 1. Problema

Los ataques modernos pueden comprometer sistemas en cuestión de minutos, mientras que la identificación y respuesta humana puede tomar mucho más tiempo.

Las soluciones tradicionales de monitoreo y detección pueden generar grandes cantidades de alertas, incluyendo falsos positivos, y normalmente requieren intervención humana antes de ejecutar acciones defensivas.

Project X propone investigar una arquitectura capaz de:

- Observar actividad del sistema en tiempo real.
- Representar las relaciones entre procesos, archivos y conexiones.
- Detectar comportamientos anómalos.
- Automatizar la respuesta ante amenazas.
- Mantener el sistema dentro de un entorno controlado y aislado.

---

## 2. Objetivo

Construir progresivamente un entorno autónomo de simulación y combate cibernético capaz de detectar y responder a comportamientos maliciosos en tiempo real.

Como objetivo inicial se busca desarrollar el pipeline:

```text
Actividad del sistema
        ↓
       eBPF
        ↓
Captura de eventos
        ↓
Procesamiento
        ↓
Grafo dinámico
        ↓
Detección mediante IA
        ↓
Respuesta automática