# Trazabilidad de requisitos

Cada requisito de la consigna (*Problem Statement*) y del kickoff del 25/09, dónde se cumple en este repositorio y
cómo verificarlo. Estado: ✅ cumplido · 🟡 parcial (la brecha está dicha) · ⬜ pendiente.

Las cifras no se repiten acá: viven en los reportes generados que se citan. Todo lo medido es offline y sobre datos
sintéticos; nada de esto es una medición en producción.

## Alcance

| Requisito | Estado | Evidencia | Cómo verificarlo |
|---|---|---|---|
| Un flujo coherente | ✅ | Consultas de cuentas y pagos (saldos, transacciones, estado de pago y mora, cambio de moneda); una sola acción, rastrear un movimiento pendiente ([ADR-002](decisions/ADR-002-one-action-confirmed-in-code.md)) | [README](../README.md#por-qué-este-flujo-medido-sobre-los-datos-provistos) |
| Camino normal de resolución | ✅ | Tipos de caso `balance_*`, `payment_ok`, `fx`, `transactions` | [`SYSTEM_EVAL.md`](../eval/reports/SYSTEM_EVAL.md), tabla "By case type" |
| Pedido ambiguo o no soportado | ✅ | Disposiciones `CLARIFY` y `ABSTAIN` en [`agent/policy/router.py`](../agent/policy/router.py); tipos `ambiguous_type`, `out_of_scope`, `code_switch` | Ídem |
| Caso que requiere una persona | ✅ | Tipos `fraud`, `suspended`, `trace_review`; traspaso estructurado en [`agent/policy/escalation.py`](../agent/policy/escalation.py) | Ídem; consola de operador en `web/` |
| Español y portugués | 🟡 | Los 548 casos de test van en ES y PT; la web tiene i18n ES/PT | Portugués escrito por el equipo: el dataset no lo trae ([LIMITATIONS](../LIMITATIONS.md#data-and-ml)) |
| Limitaciones de datos y de idioma | ✅ | [LIMITATIONS.md](../LIMITATIONS.md), [data_quality.md](data_quality.md) | Leer |
| Prototipo funcional, evidencia de camino a producción y relato honesto de lo que falta | ✅ | [operations.md](operations.md), [LIMITATIONS.md](../LIMITATIONS.md) | Demo desplegada: https://cecil-ai.onrender.com |

## 1. Un problema respaldado por datos

| Requisito | Estado | Evidencia | Cómo verificarlo |
|---|---|---|---|
| Motivos de contacto, demanda, calidad de datos, restricciones operativas | ✅ | Participación, tiempos, resolución en primer contacto y CSAT por motivo ([README](../README.md#por-qué-este-flujo-medido-sobre-los-datos-provistos), [EVALUATION §1](../EVALUATION.md)); [dataset-audit.md](dataset-audit.md), [data_evidence.md](data_evidence.md), [data_quality.md](data_quality.md) | `make baseline` regenera [`baseline_metrics.md`](evidence/baseline_metrics.md) |
| Línea base humana para medir la mejora | ✅ | [`baseline_metrics.md`](evidence/baseline_metrics.md): ≈341 s por consulta (120 s de cola + 221 s de llamada) | Ídem |
| Límite de la evidencia | 🟡 | Las 171 mil transcripciones repiten 42 textos de cliente: sirven para medir la demanda por motivo, no para entrenar ni evaluar lenguaje | [LIMITATIONS](../LIMITATIONS.md#data-and-ml) |

## 2. Un sistema de IA que funciona

| Requisito | Estado | Evidencia | Cómo verificarlo |
|---|---|---|---|
| Contexto conversacional | ✅ | Estado de sesión por turno (`agent/session/`, `agent/core/orchestrator.py`); tipo de caso `multi_turn` | `tests/test_orchestrator.py` |
| Aclarar la ambigüedad | ✅ | Disposición `CLARIFY` con las opciones del cliente | Escenario guiado "ambiguo" en la demo |
| Respuestas ancladas en información permitida | ✅ | El modelo no recibe registros del cliente y no le escribe al cliente: cada respuesta es una plantilla o datos verificados ([ADR-001](decisions/ADR-001-model-interprets-code-speaks.md), [`agent/core/render.py`](../agent/core/render.py)) | Métrica "casos que enviaron un registro de cliente al modelo" en los reportes; `tests/test_privacy.py` |
| Herramientas al servicio del flujo | ✅ | [`agent/tools/`](../agent/tools/) | `tests/test_tools.py` |
| Reportar solo acciones verificadas | ✅ | La acción se anuncia después de leerla de vuelta; si no coincide, se deriva ([ADR-002](decisions/ADR-002-one-action-confirmed-in-code.md), regla `action:trace_unverified`) | `tests/test_trace.py` |

## 3. Automatización controlada

| Requisito | Estado | Evidencia | Cómo verificarlo |
|---|---|---|---|
| Qué se responde, qué necesita confirmación, cuándo abstenerse o derivar | ✅ | Política determinista con precedencia fija ([`agent/policy/router.py`](../agent/policy/router.py), [`escalation.py`](../agent/policy/escalation.py)); la única acción exige el "sí" del cliente juzgado en código | Cada decisión lleva su `rule` en el trace; botón **Why?** en la demo |
| Permisos y políticas fuera de la prosa del modelo | ✅ | Autorización por cliente en la capa de herramientas; matriz ruta × rol que impide arrancar si falta una ruta ([`api/access.py`](../api/access.py)) | `tests/test_access_matrix.py` |
| El traspaso trae solicitud, hechos verificados, acciones, evidencia y preguntas abiertas | ✅ | `Ticket` en [`agent/policy/escalation.py`](../agent/policy/escalation.py) | Métrica "completitud del handoff" en [`SYSTEM_EVAL.md`](../eval/reports/SYSTEM_EVAL.md) |
| Identidad: un documento o número de cliente no prueba identidad | ✅ | Sesión con token firmado emitido por un IdP de prueba ([`agent/session/identity.py`](../agent/session/identity.py)) | `tests/test_privacy.py`, `tests/test_api.py`; el IdP de prueba figura en [LIMITATIONS](../LIMITATIONS.md#security-and-privacy) |

## 4. Datos y ML

| Requisito | Estado | Evidencia | Cómo verificarlo |
|---|---|---|---|
| Preparación repetible con contratos | ✅ | [`data/contracts.py`](../data/contracts.py), [`data/pipeline.py`](../data/pipeline.py), [data-validation-catalog.md](data-validation-catalog.md) | `make ingest-demo`; `tests/test_pipeline.py` |
| Controles de calidad y linaje | ✅ | [`data/quality.py`](../data/quality.py), [`data/lineage.py`](../data/lineage.py); vista **Data quality** en la demo | [data_quality.md](data_quality.md) |
| Política de actualización y frescura | ✅ | [data_quality.md, "Update and freshness policy"](data_quality.md) | Ídem |
| Corrección de la actualización con un fixture rotulado (datos estáticos) | ✅ | Prueba de llegada tardía: se re-entrega una partición y el último `last_updated` gana | `tests/test_pipeline.py` |
| Un componente aprendido contra una línea base apropiada | ✅ | Clasificador de intención frente a palabras clave, en texto que no vio | [`intent_classifier.md`](../eval/reports/intent_classifier.md); [EVALUATION §2](../EVALUATION.md) |
| Etiquetas válidas | 🟡 | Los textos de entrenamiento y de evaluación los escribió el equipo; hay sesgo de mismo autor. Set de mensajes de personas reales en curso ([human_set.md](human_set.md), [preregistro](preregistration.md)). Las etiquetas de fraude del organizador se midieron y no se usan para decidir: `is_fraud` no se aprende de la transacción (AUC 0,506) ([label_signal.md](evidence/label_signal.md), [ADR-005](decisions/ADR-005-no-fraud-or-risk-model.md)) | [LIMITATIONS](../LIMITATIONS.md#data-and-ml); [`pendientes.md`](pendientes.md) punto 4 |
| Validación automática de contratos, calidad, linaje, frescura, clasificador contra línea base y fuga | ✅ | Todos en PASS, con lo que no cierran declarado | `make validate-data-ml`; [`data_ml_validation.md`](evidence/data_ml_validation.md) |
| Sin fuga de datos | ✅ | Chequeo de casi-duplicados entre entrenamiento y evaluación ([`eval/leakage.py`](../eval/leakage.py)); splits dev (seed 7) y test (seed 11) con clientes y frases distintos | `tests/test_leakage.py` |
| Métricas, umbrales y splits justificados | ✅ | [EVALUATION §2 y §3](../EVALUATION.md); intervalos de Wilson ([`eval/stats.py`](../eval/stats.py)) | Reportes en `eval/reports/` |
| Seguimiento de experimentos | ✅ | MLflow ([`eval/tracking.py`](../eval/tracking.py)), huella del código evaluado ([`eval/fingerprint.py`](../eval/fingerprint.py)) | [EVALUATION §5](../EVALUATION.md) |

## 5. Calidad medida y manejo de fallas

| Requisito | Estado | Evidencia | Cómo verificarlo |
|---|---|---|---|
| Evaluar en casos held-out, línea base y sistema sobre la misma carga | ✅ | 548 casos de test; línea base de palabras clave ([`eval/baseline_bot.py`](../eval/baseline_bot.py)) | `make eval` → [`SYSTEM_EVAL.md`](../eval/reports/SYSTEM_EVAL.md) |
| Datos incorrectos o faltantes, sesión vencida, acceso no autorizado, inyección, falla de herramientas, ambigüedad multilingüe | ✅ | Tipos `hallucination_guard`, `expired_session`, `injection`, `tool_failure`, `code_switch`; set reservado de fallas ([`eval/heldout/`](../eval/heldout/)) con fallas inyectadas | [`FAILURE_EVAL.md`](../eval/reports/FAILURE_EVAL.md); [`SYSTEM_EVAL_ADVERSARIAL.md`](../eval/reports/SYSTEM_EVAL_ADVERSARIAL.md) |
| Resolución segura, containment, calidad de escalamiento, resultados inseguros con conteos y denominadores | ✅ | Definidos y reportados por separado en cada reporte; los omitidos y los innecesarios se cuentan | [EVALUATION §3](../EVALUATION.md) |
| Latencia p50/p95 y costo por caso y por resolución segura | ✅ | Con modelos en vivo | [`SYSTEM_EVAL_LIVE.md`](../eval/reports/SYSTEM_EVAL_LIVE.md); capacidad en [EVALUATION §6](../EVALUATION.md) |
| Resultados por idioma y segmento, con las limitaciones de muestra chica | ✅ | Por celda país·segmento y por idioma | [EVALUATION, "Fairness and coverage"](../EVALUATION.md) |
| Versiones de modelo y prompt, y variabilidad entre corridas | ✅ | `prompt_sha256`, versión de prompt, tres corridas con modelos en vivo | [`SYSTEM_EVAL_LIVE.md`](../eval/reports/SYSTEM_EVAL_LIVE.md) |
| Juez de respuestas con rúbrica validada | ✅ | No se usa un LLM como juez: el juez reconstruye determinísticamente las respuestas que el sistema podía enviar | [LIMITATIONS](../LIMITATIONS.md), ítem 5 de "Not yet measured" |
| Modelos en vivo sobre toda la carga | 🟡 | Solo una muestra estratificada de 132 de 548 casos; las cotas de seguridad son ≈2,3%, no cero | [LIMITATIONS](../LIMITATIONS.md#not-yet-measured) |
| Qué aporta cada capa de seguridad (contrafactual) | ✅ | Los mismos modelos, ideal y malo, con las capas quitadas de a una: sin capas, el modelo malo produce resultados inseguros en la mayoría de los casos; con todas, 0 | `make eval-ablation` → [`ABLATION.md`](../eval/reports/ABLATION.md) |
| Medición offline etiquetada como tal | ✅ | Todos los reportes lo declaran; nada se presenta como mejora medida en producción | [EVALUATION](../EVALUATION.md) |
| Sesión de red team sobre la demo desplegada | ⬜ | Protocolo listo ([red_team.md](red_team.md)); falta correr la sesión y generar `eval/reports/RED_TEAM.md` | Pendiente |

## 6. Un camino creíble a la operación

| Requisito | Estado | Evidencia | Cómo verificarlo |
|---|---|---|---|
| Trazas y registros de ejecución | ✅ | Id de correlación de punta a punta, un trace por turno con la regla que decidió ([operations.md, "Resilience and traces"](operations.md)) | `tests/test_trace.py`; `/admin/trace_log` |
| Reintentos acotados y fallback seguro | ✅ | Presupuesto por turno y por paso; modo degradado si el modelo no responde ([operations.md](operations.md)) | `tests/test_resilience.py`; botón "simular caída del modelo" en la demo |
| Setup reproducible | ✅ | `make up`, dependencias con hashes, CI que construye y arranca la imagen como Render | [operations.md, "Setup, reproducibly"](operations.md) |
| Límites de capacidad | ✅ | `make loadtest`, `GET /admin/capacity` | [EVALUATION §6](../EVALUATION.md) |
| Monitoreo | ✅ | `/metrics`, Prometheus, 23 reglas de alerta con pruebas | [`ops/alerts.yml`](../ops/alerts.yml); [operations.md, "Monitoring"](operations.md) |
| Controles de acceso | ✅ | Claves de operador con nombre; lectura separada de acción | [operations.md, "Access control"](operations.md); `tests/test_access_matrix.py` |
| Retención de datos | ✅ | Retención programada y auditada ([`ops/retention.py`](../ops/retention.py)) | `tests/test_retention.py` |
| Explicaciones basadas en fuentes, reglas y registros de ejecución (no en cadena de pensamiento) | ✅ | **Why?**: qué recibió el modelo (enmascarado), qué eligió y qué verificó el código, con la regla | Demo desplegada |
| Trabajo restante para desplegar de verdad | ✅ | [LIMITATIONS.md](../LIMITATIONS.md) | Leer |

## Límites de datos y de ejecución

| Requisito | Estado | Evidencia | Cómo verificarlo |
|---|---|---|---|
| Rotular si cada insumo es real, desidentificado, sintético o del equipo | ✅ | Tabla de procedencia de cada insumo de evaluación (suministrado sintético, generado por el equipo, inyectado, fixture de prueba, personas reales) | [EVALUATION, "Provenance of every evaluation input"](../EVALUATION.md) |
| Sin credenciales ni datos restringidos en el repositorio público | 🟡 | Procedimiento de copia pública con escaneo de todo el historial ([operations.md, "Public repository"](operations.md), [`ops/export_public.py`](../ops/export_public.py)). **Este repositorio es privado y su historial contiene los PDF del organizador**: no debe publicarse tal cual | Ver "Entrega" abajo |
| Servicios sandbox documentados con sus contratos y límites | ✅ | Servicio de trazas simulado ([ARCHITECTURE.md](../ARCHITECTURE.md)); IdP de prueba y PIN públicos de la demo, declarados en [LIMITATIONS](../LIMITATIONS.md#security-and-privacy) | Leer |

## Entrega (kickoff, "Submission Details")

| Requisito | Estado | Evidencia | Cómo verificarlo |
|---|---|---|---|
| Repositorio GitHub **público**, con nombre `factored-hackathon-2026-[equipo]` | ⬜ | `cecilai-hack/factored-hackathon-2026-cecilai` existe pero es **privado** | Publicar la copia limpia generada con `ops/export_public.py` como repositorio **nuevo** |
| Enlace a la herramienta desplegada | ✅ | Web: https://cecil-ai.onrender.com · API: https://x-payments-agent.onrender.com | Abrir `/login`; la API responde en `/health` |
| 4 a 6 diapositivas | 🟡 | Mazo v3 de 6 diapositivas, construido desde [slides_outline.md](slides_outline.md); faltan el nombre del equipo, la URL desplegada y la URL del repositorio público ([docs/demo/README.md](demo/README.md)) | Completar y exportar |
| Video de presentación obligatorio | 🟡 | Guion ([video_pitch_script.md](video_pitch_script.md)) y segmento de demo grabable con `ops.record_demo`; falta la voz sobre la demo | Grabar y editar |
| Enviar todo a hackathon.admin@factored.ai | ⬜ | Sin enviar | Enviar |

## Criterios de evaluación (kickoff)

| Criterio | Dónde mirar |
|---|---|
| Justificación del proyecto y documentación | [README](../README.md), [ADR-001](decisions/ADR-001-model-interprets-code-speaks.md), [ADR-002](decisions/ADR-002-one-action-confirmed-in-code.md), [LIMITATIONS](../LIMITATIONS.md) |
| Ingeniería de IA (backend, frontend, despliegue) | [ARCHITECTURE.md](../ARCHITECTURE.md), `agent/`, `api/`, `web/`, [operations.md](operations.md) |
| Analítica de datos (calidad e insights) | [data_quality.md](data_quality.md), [data_evidence.md](data_evidence.md), [`baseline_metrics.md`](evidence/baseline_metrics.md) |
| Ingeniería de datos (extracción y transformación) | [`data/`](../data/), [data-validation-catalog.md](data-validation-catalog.md) |
| Machine learning (selección, optimización, implementación, seguimiento) | [EVALUATION §2 y §5](../EVALUATION.md), [`eval/models/`](../eval/models/) |
