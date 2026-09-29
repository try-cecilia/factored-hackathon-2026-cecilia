# Estado de la integración (29/09/2026)

Brief para que todo el equipo arranque del mismo punto: qué entra con el PR de integración, qué se probó y con qué
resultado, cómo reproducirlo y qué queda pendiente.

## 1. Punto de partida

- **En `origin/main`:** ya se mergearon #19 y #20 (sesión y login web), #21 (chequeo de alertas del reporte de calidad),
  #22 (preregistro), #23 (`feat/validate-data-ml`), #24 (`feat/web-chat`) y #25 (`feat/web-operator`). Sobre el último, `origin/main`
  (`49f5c83`) da 560 tests en verde, el gate se cumple y la web compila.
- **El PR de integración** (`integracion/2026-09-29`) trae todo lo demás, que ya estaba integrado y probado en `main` local. Las ramas
  están entrelazadas (por ejemplo, `feat/prod-resilience` tuvo que incorporar `main` para resolver el lock entre procesos), así que van
  en un solo PR en lugar de uno por rama. Se puede revisar commit por commit: cada rama entra con su merge.
- **Criterio para integrar:** cada rama pasó por revisión de código independiente. Cada hallazgo se reprodujo, se corrigió con un
  test que fallaba antes del arreglo y se volvió a revisar. Lo que quedó abierto está en §6 y va en PRs aparte.

## 2. Qué trae el PR de integración

| Rama | Qué trae | Revisión |
|---|---|---|
| `feat/prod-resilience` | Id de correlación (`X-Request-ID`, `traceparent`) de punta a punta y spans por etapa. Reintentos acotados. Deadline por turno que cubre la conexión, los headers, el cuerpo y la espera del pool. Handoff con presupuesto propio por paso, que nombra un ticket solo si está confirmado. Trabajo acotado con un límite conjunto (`BOUNDED_OPS_LIMIT`). Fallback seguro por cada modo de falla. Límites de tamaño, concurrencia y tasa con `Retry-After`, y `GET /admin/capacity`. Proveedor LLM `local` (Ollama). Los errores del proveedor no dejan texto crudo. | Aprobada (6 rondas) |
| `feat/prod-operations` | Dependencias con hashes (`make lock`, `make lock-check`). `docker compose` con API, web, Prometheus, Grafana y Ollama opcional. `/metrics`, `/livez`, `/readyz`. 23 reglas de alerta con tests de promtool. Matriz de acceso ruta × rol: el servicio no arranca si falta una ruta. Retención programada y auditada con lock entre procesos. CI en 6 jobs y `make compose-e2e` aislado. | 2 rondas; quedan 2 hallazgos (§6) |
| `feat/heldout-failure-eval` | Set reservado de 226 casos ES/PT para sesión vencida, acceso no autorizado, prompt injection, fallo de herramienta y ambigüedad, con fallas inyectadas en el harness. El sistema se caía en 16 casos: ahora esos casos derivan a una persona. Pisos por categoría en el gate. Muestra chica en vivo con Groq. | 1 ronda; 5 hallazgos del evaluador (§6) |
| `feat/web-ui-kit` | Tokens de Paper y kit en `web/src/ui/`: botones, loaders, sidebar, DataTable y mensajes de chat. i18n ES/PT con el idioma resuelto en el servidor. Galería `/dev/ui` solo en desarrollo. Tests DOM con vitest. | 2 rondas; el último hallazgo (Node 24.0) está corregido |
| `fix/integracion-local` | `WEB_PUBLIC_ORIGIN` y las demás variables de la web en el compose. e2e con login de cliente y de operador, y `/dev/ui` cerrado. CI con `pnpm test:all` y árbol limpio al final. `make evidence` separado de `make gate`. `make env-check` y `make env-fill`, compatibles con dotenv. `Referrer-Policy: same-origin`: sin eso, el login de operador en un navegador real daba 403. | Aprobada (3 rondas) |
| `feat/web-screens-operador` | Consola con el diseño aprobado: densidad compacta, cola con filtros y paginación, panel de detalle con los 4 estados del ticket y bloqueo del 409 que sobrevive a errores. Monitoreo y trazas, i18n ES/PT, sidebar en tinta. | Aprobada (4 rondas) |
| `feat/web-screens-cliente` | Login, inicio y chat con el diseño aprobado. Sidebar con Casos, rail y cajón móvil. Mensajes por disposición, estados de entrega y banner de modo limitado. `GET /chat/history` rehidrata el chat al recargar. Paleta azul, sin sunrise. | 1 ronda; 5 hallazgos (§6) |
| `docs/estado-integracion` | Este brief. | — |

**Cambios hechos al integrar** (viven en los commits de merge):
- `api/access.py`: filas de `GET /admin/capacity` y `GET /admin/operator/me`.
- `api/main.py`: `_admit()` combina los limitadores de resiliencia con el punto de no retorno de la idempotencia.
- Compose y `.env.example`: los ajustes de resiliencia y `ALERT_BASE_URL`/`ALERT_WEBHOOK_URL` del chequeo de #21.
- `agent/metrics.py`: el tiempo de herramientas sale del audit cuando la traza no trae spans de herramienta.
- `agent/core/orchestrator.py`: una falla al leer novedades de casos se cuenta sin el mensaje de la excepción.
- `tests/test_ops_alerts_check.py`: es el test del chequeo de #21, renombrado porque `feat/prod-operations` trae su propio `tests/test_alerts.py` para las reglas de Prometheus.
- `ops/compose_e2e.sh`: verifica la cola con los textos de la consola nueva.
- `eval/reports/*`: regenerados sobre el resultado integrado con el warehouse completo. Cambiaron la huella, las fechas y las latencias; las métricas son las mismas.

## 3. Qué se probó y con qué resultado

Sobre la rama `integracion/2026-09-29`, con Python 3.11 y Node 24.14:

| Comando | Resultado |
|---|---|
| `python -m pytest tests/ -q` | 1016 passed, 1 skipped (≈100 s) |
| `make web-typecheck`, `make web-build` | OK |
| `make web-test` | 154 node:test, 82 vitest (DOM) y 67 HTTP contra el build de producción, todos en verde |
| `make gate` | "compuerta: se cumple"; el árbol queda limpio |
| `make lock-check`, `make alerts-check` | OK (promtool SUCCESS) |
| `make compose-e2e` | Pasa en 22 s. Cubre API, web, login de cliente y chat, login de operador y cola, `/dev/ui` cerrado, métricas, Prometheus con las reglas y Grafana provisionado |
| `make eval`, `make eval-adversarial` | 548 casos de test. 0 inseguros con el modelo ideal y con el adversarial. Resolución automática segura: 99,2% [97,0–99,8] (n=238) |
| `make eval-failures` | Set reservado: 224/226 resueltos con el modelo ideal y 196/226 con el adversarial. 0 inseguros y 0 caídas. Con el juez más estricto (sesión vencida, resolución correcta, derivación sin ticket) ninguna cifra cambió: 0 de 774 filas difieren |
| `make loadtest-http` (`eval/reports/LOADTEST_HTTP.md`) | Satura en 17,5 chats/s (máximo teórico 17,8 con 32 slots y un modelo simulado de 1,8 s). El exceso se rechaza con 503 + `Retry-After` en 5,7 ms (128 clientes) y 2,0 ms (256) p95 |

Cómo leer las cifras:

- **El set reservado dejó de ser held-out para lo que se arregló.** Los arreglos del orquestador se hicieron después de ver sus
  resultados (`eval/reports/FAILURE_EVAL.md`; los de antes están en `FAILURE_EVAL_BEFORE_FIXES.md`).
- **La muestra en vivo con Groq (`openai/gpt-oss-120b`, plan gratis) es chica:** 65 casos y una sola corrida. Da 39/42 en el set de
  fallos y 0 inseguros (`eval/reports/LIVE_SAMPLE_GROQ.md`). No se puede rearmar desde artefactos: no se guardaron los ids ni las filas
  por caso. La próxima corrida sí queda reproducible (`eval/live_sample.py`, `make eval-live-sample`, `make eval-live-sample-report`).
- **El warehouse completo se construyó con los CSV del organizador en local.** Coincide con el reporte de calidad en las 5 tablas
  de servicio. Faltan las tablas de contact center, así que `make analysis` no se puede reproducir con esa copia.

## 4. Cómo probar en local

Requisitos: Docker, Python 3.11 con `uv`, Node 24 y pnpm 10.33.2. No hace falta cloud: S3 y los proveedores remotos son opcionales.

```bash
make env-check           # qué le falta a tu .env (solo nombres) y si INGEST_ARGS iría a S3
make env-fill            # agrega solo las variables que faltan, con secretos generados; no toca las existentes
make monitoring-up       # API + web + Prometheus + Grafana sobre el warehouse de fixtures
make up-dataset RAW_DIR=/ruta/a/data/raw   # en vez del fixture, los CSV del organizador (solo lectura)
make up-llm-host         # con un modelo local: Ollama nativo en el host (en macOS, Ollama en Docker va solo en CPU)
make compose-e2e         # la prueba de punta a punta, en un proyecto aparte
make down                # baja el stack y conserva los volúmenes (make clean-volumes los borra, pregunta antes)
```

| Qué | Dónde | Credenciales |
|---|---|---|
| App del cliente | http://127.0.0.1:3000 | PIN de prueba en los escenarios de demo (`DEMO_MODE=1`) |
| Consola de operador | http://127.0.0.1:3000/operador/login | `ADMIN_API_KEY` (lectura) y una clave de `OPERATOR_KEYS` (acción) |
| API | http://127.0.0.1:8000 (`/livez`, `/readyz`, `/metrics`) | `/metrics` con `Authorization: Bearer $METRICS_TOKEN` |
| Prometheus | http://127.0.0.1:9090 (Alerts muestra las 23 reglas) | — |
| Grafana | http://127.0.0.1:3001 | usuario `admin`, contraseña `GRAFANA_ADMIN_PASSWORD` |

Sin Docker: `make web-setup` y `make serve-all-fixture` (warehouse de tests y modelo simulado), o `make serve-all` con
`data/warehouse/bank.duckdb` y una clave de modelo. El warehouse completo se construye con
`python -m data.pipeline --profile all --source local --raw-dir /ruta/a/data/raw --report /tmp/quality.json`.

## 5. Decisiones tomadas

- **Nada requiere cloud.** Todo se levanta en Docker local. S3, Render y los proveedores remotos son opciones.
- **Modelos para probar:** Groq en plan gratis, u Ollama local por el proveedor `local`. OpenRouter se descartó.
- **La UI está en español y portugués**, con selector de idioma. Las respuestas de la asistente llegan de la API en el idioma del cliente.
- **Diseño:** la fuente de verdad es el archivo "Cecil.ai" de Paper.
  - Paleta azul; el ámbar queda solo para precaución.
  - Sin bordes y sin streaming (ADR-001). La única acción es rastrear un movimiento, con confirmación (ADR-002).
  - Los sidebars van con texto e íconos en tinta. El azul queda solo en el foco, los puntos de no leído y el caret.
- **Operador:** para decidir hay que haber tomado el caso. Las acciones son de un clic, sin diálogo, con `expected_version`.
- **Dependencias Python:** se editan en `requirements.in` y se corre `make lock`. Los `requirements*.txt` son generados.
- **Evidencia:** `make gate` y `make validate-data-ml` solo verifican. `make evidence` y `make eval*` regeneran lo versionado.

## 6. Pendiente (va en PRs aparte, sobre este)

| Tema | Qué falta |
|---|---|
| Pantallas del cliente | (1) Una recarga tardía del historial puede mezclar sesiones o pisar mensajes nuevos. (2) La purga no vacía la caché en memoria de la conversación, y una sesión vencida puede volver a guardarla. (3) El historial acotado pierde casos del sidebar y la recuperación del 409. (4) El foco se escapa de los cajones modales. (5) Demo y "¿Por qué?" sin portugués. |
| Operación | (1) Los probes de `/readyz` que vencen dejan hilos bloqueados que se acumulan. (2) Falta una prueba integrada de que la espera entre reintentos del modelo se atribuye al LLM y no a política. |
| Evaluador held-out | (1) Una respuesta con datos y sesión vencida puede contarse como segura. (2) "Correcto y seguro" acepta respuestas a otra consulta. (3) El caso de cola caída no verifica lo que se le dice al cliente. (4) CI no aplica los pisos al reporte recién calculado. (5) La muestra Groq no versiona la selección ni los resultados por caso. Son falsos positivos del juez, no fugas del sistema. |
| Sin medir | Un modelo local real (Ollama). Una muestra en vivo más grande. |
| Sin revisar | El portugués de la UI por alguien nativo. El kit en Firefox y Safari (el login local ya se verificó en WebKit, ver LIMITATIONS.md). |
