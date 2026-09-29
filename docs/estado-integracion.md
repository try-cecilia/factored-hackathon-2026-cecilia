# Estado de la integración (29/09/2026)

Brief para que todo el equipo arranque del mismo punto: qué hay en `main` local, qué se probó y con qué resultado,
cómo reproducirlo y qué falta. Todo lo integrado sigue en su rama y va a tener su propio PR.

## 1. Punto de partida

- **Base:** `origin/main` en `9d62bfb` (PR #18) más los PR abiertos **#19** (`feat/api-session-endpoints`) y **#20**
  (`feat/web-auth`, con su fix `83d05b8`), mergeados localmente en `8865592`. Esos dos PR siguen abiertos y sin revisión humana.
- **Ramas nuevas:** todas salen de `8865592` y se integraron en `main` local **sin push**. La excepción es `feat/web-ui-kit`, que sale del
  HEAD de `feat/web-chat` en `299536d`.
- **Estado probado:** `main` local en `0b355ef`. El tag `pre-integracion-total` marca el punto anterior a la integración masiva.
- **Criterio para integrar:** cada rama pasó por revisión de código independiente. Cada hallazgo se reprodujo, se corrigió con un
  test que fallaba antes del arreglo, y se volvió a revisar.

## 2. Ramas integradas

| Rama | Qué trae | Revisión |
|---|---|---|
| `feat/validate-data-ml` | `make validate-data-ml`: 43 pruebas, una por afirmación de los docs, sobre contratos, calidad, linaje (SHA-256 por archivo fuente, `python -m data.lineage --verify`), frescura, clasificador contra línea base y fuga. Rechaza decimales que el cast redondearía. Evidencia en `docs/evidence/data_ml_validation.md`. | Aprobada (3 rondas) |
| `feat/web-chat` | Tokens de Paper, shell y chat del cliente por el BFF (el token nunca llega al navegador). Rastreo con Sí/No, escalamiento con número de caso y fallos visibles: sesión vencida, 401, 429, API caída, timeout. `Idempotency-Key` en `POST /chat` (`api/idempotency.py`). `make serve-all-fixture` para correr sin S3 ni claves. | Aprobada (5 rondas) |
| `feat/web-operator` | Consola en `/operador/*`: login por formulario nativo (las claves nunca quedan en el navegador), cola, detalle, acciones con `expected_version`, monitoreo y trazas. Chequeo de origen contra `WEB_PUBLIC_ORIGIN`, rotación atómica de la sesión y vencimiento por inactividad. `GET /admin/operator/me`. | Aprobada (7 rondas) |
| `feat/web-ui-kit` | Tokens completos de Paper y kit en `web/src/ui/`: botones, loaders, sidebar, DataTable y mensajes de chat por disposición. i18n ES/PT con el idioma resuelto en el servidor y selector. Galería `/dev/ui` solo en desarrollo. Tests DOM con vitest. | 2 rondas. El último hallazgo (engines de Node) está corregido en `864ac4f`, sin re-revisión |
| `feat/prod-resilience` | Id de correlación (`X-Request-ID`, `traceparent`) de punta a punta y spans por etapa. Reintentos acotados, deadline por turno y presupuesto propio del handoff. Fallback seguro por cada modo de falla. Límites de tamaño, concurrencia y tasa con `Retry-After`. `GET /admin/capacity`. Proveedor LLM `local` (Ollama) y errores del proveedor sin texto crudo. | **En curso**: 3 rondas, quedan 2 hallazgos abiertos (ver §6) |
| `feat/prod-operations` | Dependencias fijadas con hashes (`make lock`, `make lock-check`). `docker compose` con API, web, Prometheus, Grafana y Ollama opcional. `/metrics`, `/livez`, `/readyz`. 23 reglas de alerta con tests de promtool. Matriz de acceso ruta × rol (el servicio no arranca si falta una ruta). Retención por tipo de dato, programada y auditada, con lock entre procesos. CI en 6 jobs. `make compose-e2e` aislado. | 1 ronda: sus 5 hallazgos están corregidos, falta la segunda ronda |
| `feat/heldout-failure-eval` | Set reservado de 226 casos ES/PT (`eval/heldout.py`) para sesión vencida, acceso no autorizado, prompt injection, fallo de herramienta y ambigüedad, con fallas inyectadas en el harness. El sistema se caía en 16 casos: ahora esos casos derivan a una persona. Pisos por categoría en el gate. Muestra chica en vivo con Groq. | 1 ronda: 5 hallazgos abiertos en el evaluador (ver §6) |

## 3. Cambios hechos al integrar

Estos cambios viven **solo en los commits de merge de `main` local**. No están en ninguna rama, y hay que llevarlos a un PR (ver §7).

- `api/access.py`: filas para `GET /admin/capacity` (admin) y `GET /admin/operator/me` (operador). Sin esas filas el servicio no arranca.
- `api/main.py`: `_admit()` combina los limitadores por sesión, cliente e IP de resiliencia con el punto de no retorno de la idempotencia.
  El bloqueo por intentos fallidos devuelve `Retry-After`.
- `ops/docker-compose.yml` y `.env.example`: pasan al API los 15 ajustes de resiliencia (`TURN_BUDGET_SECONDS`, `HANDOFF_BUDGET_SECONDS`,
  `MAX_CONCURRENT_CHATS`, etc.).
- `agent/metrics.py`: si la traza no trae spans de herramienta (lectura degradada del saldo), el tiempo de herramientas sale del audit.
- `agent/core/orchestrator.py`: una falla al leer las novedades de casos se cuenta y se registra por tipo, sin el mensaje de la excepción.
- `tests/test_idempotency.py` y `tests/test_metrics.py`: adaptados, porque con resiliencia una traza que no se escribe ya no tira el turno.
- `docs/operations.md`: tabla de acceso regenerada con `python -m api.access`.
- `eval/reports/*`: regenerados dos veces sobre `main` integrado con el warehouse completo. Cambiaron solo la huella, las fechas y las latencias; las métricas son las mismas.

## 4. Qué se probó y con qué resultado

Sobre `main` local en `0b355ef`, con Python 3.11 y Node 24.14:

| Comando | Resultado |
|---|---|
| `python -m pytest tests/ -q` | 938 passed, 1 skipped (≈82 s) |
| `make web-typecheck`, `make web-build` | OK |
| `make web-test` | 115 node:test, 16 vitest (DOM) y 59 HTTP contra el build de producción: todos pasan |
| `make gate` | "compuerta: se cumple" |
| `make validate-data-ml` | PASS en los 6 criterios (11/11, 2/2, 13/13, 4/4, 5/5, 8/8) |
| `make lock-check`, `make alerts-check` | OK (23 reglas, tests de promtool OK) |
| `make compose-e2e` | Pasa en 36 s: API, web, métricas, Prometheus con las reglas y Grafana provisionado, en un proyecto Docker descartable |
| `make eval`, `make eval-adversarial` | 548 casos de test, 0 resultados inseguros con el modelo ideal y con el adversarial. Resolución automática segura 99,2% [97,0–99,8] (n=238) |
| `make eval-failures` | Set reservado: 224/226 resueltos con el modelo ideal y 196/226 con el adversarial; 0 inseguros y 0 caídas en ambos |
| `make loadtest-http` (`eval/reports/LOADTEST_HTTP.md`) | Satura en 17,5 chats/s (máximo teórico 17,8 con 32 slots y un modelo simulado de 1,8 s). Con 128 y 256 clientes, el exceso se rechaza con 503 + `Retry-After` en 5,7 y 2,0 ms p95 |

Cómo leer las cifras:

- **El set reservado dejó de ser held-out para lo que se arregló.** Los arreglos del orquestador se hicieron después de ver sus
  resultados; está declarado en `eval/reports/FAILURE_EVAL.md`. Los resultados de antes de los arreglos están en `FAILURE_EVAL_BEFORE_FIXES.md`.
- **La muestra en vivo con Groq (`openai/gpt-oss-120b`, plan gratis) es una muestra chica.** Fueron 65 casos, una corrida, con intervalos de
  20 a 30 puntos: 39/42 en el set de fallos y 0 inseguros. Está en `eval/reports/LIVE_SAMPLE_GROQ.md`.
- **El warehouse completo se construyó con los CSV del organizador en local** (`--profile all --source local`). Coincide con el reporte de
  calidad versionado en las 5 tablas de servicio. Faltan las tablas de contact center, así que `make analysis` no se puede
  reproducir con esa copia.

## 5. Cómo probar en local

Requisitos: Docker, Python 3.11 con `uv`, Node 24 y pnpm 10.33.2. No hace falta cloud: S3 y los proveedores remotos son
opcionales.

**Con Docker (un comando):**

```bash
make up                  # API + web sobre el warehouse de fixtures: http://127.0.0.1:3000 (web), :8000 (API)
make monitoring-up       # además Prometheus :9090 y Grafana :3001
make up-dataset RAW_DIR=/ruta/a/data/raw   # los CSV del organizador, montados de solo lectura
make up-llm-host         # modelo local: Ollama nativo en el host (en macOS, Ollama dentro de Docker corre solo en CPU)
make compose-e2e         # la prueba de punta a punta, en un proyecto aparte
make down                # baja el stack y conserva los volúmenes (make clean-volumes los borra, pregunta antes)
```

- `make up` crea `.env` si no existe y **no toca uno existente**. Un `.env` viejo puede no tener `METRICS_TOKEN`,
  `GRAFANA_ADMIN_PASSWORD` ni `DEMO_MODE=1` (sin ese valor no se ven los escenarios guiados con PIN de prueba). También puede traer
  un `INGEST_ARGS` que ingiere desde S3. Compará contra `.env.example`.
- **Pendiente:** en Docker, el login de operador todavía no funciona porque el compose no le pasa `WEB_PUBLIC_ORIGIN` a la web.
  Se corrige en `fix/integracion-local` (ver §6). Mientras tanto, probá la consola con la opción sin Docker.

**Sin Docker:**

```bash
uv pip install --python .venv/bin/python --require-hashes -r requirements-tracking.txt
make web-setup
make serve-all-fixture   # sin S3 ni claves: warehouse de los tests y un modelo simulado por palabras clave
make serve-all           # con data/warehouse/bank.duckdb y una clave de modelo en .env (p. ej. GROQ_API_KEY)
```

Para construir el warehouse completo desde los CSV:
`python -m data.pipeline --profile all --source local --raw-dir /ruta/a/data/raw --report /tmp/quality.json`.

**Recorridos para probar a mano:**

- **Cliente:**
  - login, chat, consulta de saldo;
  - rastreo de un pago pendiente con Sí/No;
  - fraude que escala con número de caso;
  - sesión vencida;
  - cambio de idioma ES/PT.
- **Operador:**
  - `/operador/login` con `ADMIN_API_KEY` (lectura) y una clave de `OPERATOR_KEYS` (acción);
  - tomar, aprobar, rechazar y devolver;
  - conflicto 409 con dos operadores;
  - monitoreo y trazas.
- **Galería:** `/dev/ui` (solo en desarrollo) muestra el kit en ES y PT para compararlo con Paper.

## 6. En curso y pendiente

| Tema | Estado |
|---|---|
| `feat/prod-resilience` | Dos hallazgos abiertos. (1) El deadline no corta mientras llegan los headers de la respuesta del modelo. (2) El presupuesto del handoff todavía no acota evidencia, escritura y lectura del ticket. Además, `serialize_policy_writers()` toma un lock entre procesos sin timeout, por fuera de ese presupuesto. Se corrigen en esta rama. |
| `feat/heldout-failure-eval` | Cinco hallazgos en el evaluador, no en el sistema: (1) una respuesta con datos y sesión vencida puede contarse como segura; (2) "correcto y seguro" acepta respuestas a otra consulta; (3) el caso de cola caída no verifica lo que se le dice al cliente; (4) CI no aplica los pisos al reporte recién calculado; (5) la muestra Groq no versiona la selección ni los resultados por caso. Sin asignar. |
| `feat/prod-operations`, `feat/web-ui-kit` | Falta la última ronda de revisión. |
| `fix/integracion-local` | En curso: `WEB_PUBLIC_ORIGIN` en el compose; e2e con login de cliente y de operador y el 404 de `/dev/ui`; CI con `pnpm test:all`, `validate-data-ml` y `test-resilience`; la evidencia de `validate-data-ml` ya no ensucia el árbol; `make env-check`. |
| `feat/web-screens-cliente` | En curso: diseño aprobado de Paper aplicado a login, inicio y chat con el kit e i18n; sección Casos; `GET /chat/history` para que recargar no vacíe el chat. |
| `feat/web-screens-operador` | En curso: diseño aprobado (densidad compacta, tabla de cola, panel de detalle, estados del ticket) aplicado a la consola. |
| Portugués de la UI | Lo escribió el equipo; falta que lo revise alguien nativo. |
| Pendiente de medir | El modelo local (Ollama) no se midió con un modelo real. La muestra en vivo es chica. No hay exporter de OpenTelemetry. |

## 7. Plan de PRs

- **Un PR por rama**, en este orden, porque cada una depende de las anteriores:
  1. #19
  2. #20
  3. `feat/validate-data-ml`
  4. `feat/web-chat`
  5. `feat/web-operator`
  6. `feat/prod-resilience`
  7. `feat/prod-operations`
  8. `feat/heldout-failure-eval`
  9. `feat/web-ui-kit`
  10. `fix/integracion-local`
  11. las ramas de pantallas
- **#19 y #20 van primero.** Todas las ramas nuevas los contienen, así que hasta que se mergeen, cada PR va a mostrar también sus commits.
- **Los cambios de §3 van en el PR de `fix/integracion-local`**, o se reparten al resolver los conflictos de cada PR. Hay que llevarlos
  explícitamente: si no, `main` en GitHub no arranca, porque `api/access.py` exige una fila por ruta.
- **`eval/reports/*` se regenera al final.** La huella de políticas cambia con cada rama que toca el orquestador, las políticas o
  las herramientas, así que conviene volver a medir una sola vez, después del último PR (`make eval eval-adversarial eval-failures`), y
  commitear el resultado.

## 8. Decisiones tomadas

- **Nada requiere cloud.** Todo se levanta con Docker local. S3, Render y los proveedores remotos son opciones.
- **Modelos para probar:** Groq en plan gratis, u Ollama local por el proveedor `local`. OpenRouter se descartó.
- **UI en español y portugués** desde ya, con selector. Las respuestas de la asistente vienen de la API en el idioma del cliente.
- **Diseño:** la fuente de verdad es el archivo "Cecil.ai" de Paper. Artboards aprobados: UI · Buttons, Sidebars, Data tables,
  Chat messages, Loaders y Operator · Queue / Ticket states. "Chat Components" está obsoleto. Sin bordes y sin streaming (ADR-001).
  La única acción es rastrear un movimiento, con confirmación (ADR-002).
- **Decidir un ticket exige haberlo tomado antes**: `agent/policy/desk.py`.
- **La tabla vieja `idempotency` se borra al iniciar el store.** Nunca se desplegó, así que no se migra.
- **Dependencias Python:** se editan en `requirements.in` y se ejecuta `make lock`; `requirements*.txt` son generados.
