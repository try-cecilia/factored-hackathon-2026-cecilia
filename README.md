# LATAM Bank — Consultas de cuentas y pagos con IA como primera línea

Factored AI & Data Hackathon 2026. Un sistema de atención al cliente funcional para un flujo bancario
acotado: **consultas de cuentas y pagos** (saldos, transacciones, estado de pagos y mora, tipos de cambio)
de un banco minorista en México, Colombia y Argentina, en **español y portugués**.

Entiende la consulta, decide con políticas deterministas, actúa mediante herramientas con permisos, responde
solo con datos verificados y deriva a una persona, con evidencia, cuando no debe actuar. **El modelo
interpreta; el código habla**: el sistema nunca le entrega al modelo de lenguaje un registro de cliente, los
identificadores que el cliente escribe se enmascaran antes de salir, y el modelo nunca le escribe al cliente
([ADR-001](docs/decisions/ADR-001-model-interprets-code-speaks.md)). Su única acción, rastrear un
movimiento que sigue pendiente, ocurre solo con el "sí" del propio cliente, juzgado en código, y se anuncia
únicamente después de leerla de vuelta ([ADR-002](docs/decisions/ADR-002-one-action-confirmed-in-code.md)).

## Para quienes evalúan: dónde mirar

1. **Probarlo:** [URL desplegada]. Cada escenario guiado indica qué observar. Presioná **"Why?"** en una
   respuesta para ver qué recibió el modelo (enmascarado), qué eligió y qué verificó el código; abrí la
   **vista del banco** después de una derivación o un rastreo; dejá el modelo caído y volvé a preguntar; y
   abrí **Data quality**.
2. **Verificar un número:** todas las cifras de acá salen de un reporte generado:
   [`SYSTEM_EVAL.md`](eval/reports/SYSTEM_EVAL.md) (offline, 528 casos),
   [`SYSTEM_EVAL_LIVE.md`](eval/reports/SYSTEM_EVAL_LIVE.md) (modelos en vivo),
   [`intent_classifier.md`](eval/reports/intent_classifier.md) y
   [`baseline_metrics.md`](docs/evidence/baseline_metrics.md) (la línea base humana).
   [`EVALUATION.md`](EVALUATION.md) explica cómo se mide cada uno y marca qué es una proyección.
3. **Leer las dos decisiones:** [ADR-001](docs/decisions/ADR-001-model-interprets-code-speaks.md) y
   [ADR-002](docs/decisions/ADR-002-one-action-confirmed-in-code.md).
4. **Ejecutarlo:** `make test` no necesita claves ni red; `make ingest-demo && make serve` corre la app en
   tu máquina; `make all` reconstruye cada número ([Inicio rápido](#inicio-rápido)).
5. **Qué falta todavía:** [`LIMITATIONS.md`](LIMITATIONS.md).

## Por qué este flujo (medido sobre los datos provistos)

| | Cuentas y pagos ("Transaccional") | Todos los demás motivos |
|---|---|---|
| Participación en 686 mil contactos | **35,0%** (la mayor) | 65,0% |
| Tiempo medio de atención / espera | 221 s / 120 s | 266–540 s / 120 s |
| Resolución en el primer contacto | 91,5% | 44–90% |
| CSAT (1–5) | 2,91 | 2,43–2,90 |

Alto volumen, simple y ya resoluble; sin embargo, los clientes esperan dos minutos para una llamada de
3,7 minutos y aun así la califican por debajo de 3/5. La mediana es de 6.701 contactos de este tipo al mes,
unas 411 horas de agente. Fuente: [`docs/evidence/baseline_metrics.md`](docs/evidence/baseline_metrics.md)
(generado automáticamente por `make analysis`).

## Resultados (workload de test held-out, ES + PT)

Offline, sobre los 528 casos de test (22 tipos de caso × 12 celdas país·segmento × ES/PT), diseño v3 sobre el
warehouse del organizador:

| | Bot de palabras clave (línea base) | Este sistema, modelo ideal¹ | Este sistema, modelo adversarial² |
|---|---|---|---|
| Resolución automática segura | 69,6% [63,5–75,1] | 98,8% [96,4–99,6] | 60,8% [54,5–66,8] |
| Recall de escalamiento | 66,7% | 100% | 100% |
| Escalamientos omitidos | 48 | 0 | 0 |
| Completitud del handoff | 50,0% | 100% | 100% |
| **Resultados inseguros** | 0 / 528 | **0 / 528** | **0 / 528** |
| Casos que enviaron un registro de cliente al modelo | n/a | 0 / 528 | 0 / 528 |

¹ Modelo ideal guionado: mide de verdad todas las capas deterministas y es un techo para la comprensión del
propio LLM. Sus 3 omisiones y 6 derivaciones innecesarias vienen de un único pedido de rastreo en español,
"hice un pago que sigue pendiente", que la guarda de disputas previa al LLM entrega a una persona: se reporta,
no se ajusta ([`LIMITATIONS.md`](LIMITATIONS.md#the-action)). ² Un modelo guionado deliberadamente malo, que
obedece inyecciones, consulta productos de otros clientes e inventa cifras: la automatización baja y las
derivaciones suben, **pero nada inseguro pasa**. La seguridad no depende del modelo.

Con modelos en vivo, sobre una muestra estratificada de 132 de esos casos (todos los tipos de caso en ambos
idiomas, 11 por celda), tres corridas cada uno
([`eval/reports/SYSTEM_EVAL_LIVE.md`](eval/reports/SYSTEM_EVAL_LIVE.md)):

| | Claude Sonnet 5 | Claude Haiku 4.5 |
|---|---|---|
| Resolución automática segura | **95,0%** [86,3–98,3] | 78,3% [66,4–86,9] |
| Recall de escalamiento | 100% | 88,9% (4 omitidos) |
| **Resultados inseguros** | **0 / 132 en cada corrida** | **0 / 132 en cada corrida** |
| Casos que enviaron un registro de cliente al modelo | 0 / 132 | 0 / 132 |
| Latencia por caso, p50 / p95 | 1,8 s / 3,9 s | 1,2 s / 3,8 s |
| Costo de modelo por resolución segura | USD 0,0029 | USD 0,0057 |
| Casos cuyo resultado cambió entre corridas | 3,0% (4 de 132) | 4,5% (6 de 132) |

La tabla muestra la corrida 1; en las tres corridas, la resolución automática segura fue de 95,0–96,7% con
Sonnet 5 y de 78,3–81,7% con Haiku 4.5. Las 3 omisiones de Sonnet 5 no son inseguras: dos veces consultó el
estado de pago del producto cuyo saldo se preguntó, y una vez hizo una pregunta aclaratoria ante una consulta
de tipo de cambio. Sonnet 5 es el modelo que usa el despliegue ([`render.yaml`](render.yaml)): de los dos
medidos, el de mayor resolución segura y menor costo por resolución segura. `gpt-oss-120b` de Groq no se
corrió: necesita una clave. Los intervalos son Wilson 95%. Cero eventos observados acota la tasa real por
debajo de ≈3/n: ≈0,6% con 528 casos, ≈2,3% con 132.

**Frente a agentes humanos:** una consulta atendida por una persona toma ≈341 s (120 s de cola + 221 s de
llamada, medidos). Este sistema responde sin cola: 1,8 s por caso en la mediana con Sonnet 5 (p95 3,9 s).
Ver la [tabla resumen](EVALUATION.md#summary-human-agents-vs-keyword-bot-vs-this-system).

Componente aprendido: el clasificador de intención supera a la línea base de palabras clave en texto que
nunca vio (**84,9% vs 62,8%** de exactitud en el split de test held-out). Como guarda previa al LLM, sube el
recall de fraude/disputa de 80% a **93,3%** con **0%** de escalamientos falsos:
[`eval/reports/intent_classifier.md`](eval/reports/intent_classifier.md).

Diapositivas de la entrega y video de demo: [`docs/demo/`](docs/demo/README.md).

Reportes completos: [`EVALUATION.md`](EVALUATION.md) (método) ·
[`eval/reports/SYSTEM_EVAL.md`](eval/reports/SYSTEM_EVAL.md) ·
[`eval/reports/SYSTEM_EVAL_ADVERSARIAL.md`](eval/reports/SYSTEM_EVAL_ADVERSARIAL.md) ·
[`eval/reports/SYSTEM_EVAL_LIVE.md`](eval/reports/SYSTEM_EVAL_LIVE.md).

## Cómo funciona

```
texto del cliente ─► chequeo de sesión ─► política pre-LLM ──────────────► escalar (bloqueo de compliance,
   (ES/PT)            (solo token)        (léxico + guarda del clasificador +   fraude, robo, legal, producto
                                           referencia a producto ajeno)         de otro cliente)
                                        │
                                        ▼  texto enmascarado + alias de productos + historial sin cifras
                 LLM, una llamada (Claude / Groq gpt-oss-120b / Together): elige herramientas y argumentos
                                        │   nunca ve registros, nunca escribe la respuesta
                                        ▼
                 herramientas (DuckDB): chequeo de propiedad, enmascarado, as-of, freshness ─► la política
                                        │                                 asigna una disposición a cada resultado
                                        ▼
                 respuesta armada con los resultados verificados (plantillas ES/PT)
                                        │
                                        ▼
                 AUTO_RESOLVE · CLARIFY · ABSTAIN · ESCALATE (ticket leído de vuelta, con evidencia) · rastreo
```

Detalles: [`ARCHITECTURE.md`](ARCHITECTURE.md). Pipeline de datos, contratos y hallazgos de calidad:
[`docs/data_quality.md`](docs/data_quality.md). Cómo operarlo: [`docs/operations.md`](docs/operations.md).
Qué falta todavía: [`LIMITATIONS.md`](LIMITATIONS.md).

## Inicio rápido

```bash
python3.11 -m venv .venv && source .venv/bin/activate   # Python 3.11 (el modelo de intención versionado fija scikit-learn 1.9.1); o: uv venv --python 3.11 --seed
cp .env.example .env        # completar AWS_* + DATASET_BUCKET (dataset), DEMO_IDP_SECRET, ADMIN_API_KEY, y ANTHROPIC_API_KEY o GROQ_API_KEY
make setup
make ingest                 # warehouse completo desde S3 (~6 min: 1,1 GB de archivos diarios en ~80 s, luego la carga; o `make ingest-demo`, ~1 min)
make serve                  # http://localhost:8000 — chat web con logins de prueba del sandbox
make test                   # 346 tests herméticos: warehouse de fixtures, sin S3, sin claves de API
make all                    # reconstruye cada número de los docs
make mlflow-ui              # cada selección y evaluación del clasificador, registrada en MLflow
```

Los comandos asumen Linux o macOS con `make`. En Windows, usá WSL o ejecutá el comando de cada target del
`Makefile` con el `python` del venv.

Se inicia sesión con un id de cliente y su **PIN de prueba** (un número de cliente solo no se acepta). La
interfaz web lista las cuentas del sandbox desde `DEMO_PUBLIC_CUSTOMERS`. Quienes operan pueden obtener
cualquier PIN de prueba con `X-Admin-Key` en `/admin/demo_pin/{id}`. Los traces, tickets, el registro de
auditoría y el reporte de calidad de datos están bajo `/admin/*`.

**Demo para el jurado (`DEMO_MODE=1`).** La misma app web se convierte en un recorrido guiado por los caminos
requeridos, sobre el warehouse que esté cargado (los clientes de cada escenario los elige de él
`ops/demo_customers.py`):
- hasta 13 escenarios guiados (un comportamiento para el que el warehouse cargado no tiene cliente pierde su
  escenario): normal (saldo, mora en portugués, tipo de cambio), ambiguo (dos turnos), fuera de alcance, la
  acción verificada (rastrear una transferencia pendiente, dos turnos), necesita una persona (fraude, cuenta
  suspendida, datos faltantes), ataque (producto de otro cliente, jailbreak) y falla (modelo caído, sesión
  vencida). Cada uno indica qué observar y verifica el resultado que promete;
- un **"Why?"** en cada respuesta: la regla de política que decidió, qué recibió el modelo (enmascarado) y qué
  eligió, qué verificó el código y el costo;
- la **vista del banco**: lo que la sesión envió a los equipos del banco, tal como lo reciben: pedidos de
  rastreo para operaciones de pagos, y tickets con evidencia y preguntas abiertas, sin transcripción ni token;
- botones para **vencer la sesión** y para **tirar el modelo** solo en esa sesión;
- una vista de **Data quality**: el warehouse cargado según sus propias tablas de lineage (filas, particiones
  diarias y última carga de cada tabla, los checks que no pasaron, freshness), la corrida sobre el dataset
  completo, los desvíos documentados del contrato y la política de actualización. Solo agregados.

Debe permanecer apagada en cualquier entorno real (`LIMITATIONS.md`).

## Mapa del repositorio

```
data/        pipeline (S3/local → DuckDB), contratos, checks de calidad, lineage, reports/
agent/       core/ orquestador, render · policy/ router, señales, guarda del clasificador, escalamiento
             tools/ herramientas de cuenta con permisos, logs de auditoría y traces · llm/ cliente, prompts, enmascarado de privacidad, precios, clasificadores
             session/ almacén de sesiones, proveedor de identidad de la demo
api/         FastAPI + chat web estático; demo.py: la demo para el jurado (DEMO_MODE=1)
analysis/    evidencia del problema y línea base humana a partir de los datos provistos
eval/        sets held-out, generador de workload, bot base, runners de evaluación, tracking en MLflow, reports/
ops/         Dockerfile, entrypoint, selector de clientes de demo, prueba de carga, corrida smoke en vivo, retención
docs/        decisiones de arquitectura (decisions/), calidad de datos, operaciones, evidencia, demo
tests/       346 tests herméticos + fixtures
```

## Estado

- Construido y evaluado de punta a punta, offline y con modelos en vivo, sobre el warehouse del organizador.
  CI corre la suite hermética y verifica el reporte del clasificador. Cada selección y evaluación del
  clasificador queda registrada en MLflow: modelo, esfuerzo, hash del prompt, hashes de los datos, versión del
  código y métricas ([`EVALUATION.md`](EVALUATION.md#5-experiment-tracking-mlflow)).
- Reproducido desde cero el 2026-09-28: `make all` sobre un clon limpio del repositorio público, en un
  entorno nuevo de Python 3.11, reconstruyó los casos de evaluación y el clasificador byte por byte, los
  mismos checks de calidad con los mismos resultados (238 entonces; se agregaron 8 después, ver
  [`docs/data_quality.md`](docs/data_quality.md)), y cada métrica offline caso por caso (salvo las latencias,
  que dependen de la máquina).
- **Modelo en vivo: medido sobre el workload held-out** (arriba). Antes de eso, una corrida smoke sobre los
  fixtures sintéticos también cubrió Claude Opus 5: 13/13 turnos calificados contra su resultado previsto,
  p50 de 3,0 s por turno y unos USD 0,005 por llamada al modelo
  ([`eval/reports/LIVE_SMOKE.md`](eval/reports/LIVE_SMOKE.md)). Cuando no hay ningún modelo accesible, la app
  se degrada de forma segura:
  - responde de forma determinista las preguntas simples de saldo;
  - se abstiene ante pedidos claramente fuera de alcance;
  - escala el resto.
- Todavía sin desplegar: necesita la cuenta de hosting. `render.yaml` es el Blueprint de Render (instancia
  paga de 512 MB, disco de 1 GB, modo demo, presupuesto diario de modelo). El contenedor ingiere una muestra
  de 5 mil clientes en el primer arranque: esa carga midió 20 s y 14 MB con DuckDB limitado a 400 MB. CI
  construye la imagen en cada push y la levanta como lo hace Render, y luego le hace un smoke test
  ([`docs/operations.md`](docs/operations.md#deploy-on-render-the-jury-demo)).

Todos los datos de clientes de este repositorio son sintéticos (dataset del organizador y fixtures hechos a
mano). El texto de prueba en portugués fue escrito por el equipo; el dataset no tiene ninguno.
