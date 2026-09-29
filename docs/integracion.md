# Puntos de integración y contratos de los sistemas simulados

La consigna acepta servicios de prueba y herramientas bancarias simuladas "cuando sus contratos y limitaciones están
documentados", y pide identificar qué entradas son reales, de-identificadas, sintéticas o generadas por el equipo.
Este documento hace las dos cosas: dice qué es simulado hoy, qué contrato cumple cada simulación y **dónde exactamente**
se enchufaría el sistema real.

Cómo leerlo:

- **Contrato actual** es lo que el código hace hoy y un test comprueba. **En producción** es lo que proponemos, no algo
  ya acordado con un banco. Donde depende del banco y no lo sabemos, dice **por definir con el banco**.
- Cada frontera usa la misma plantilla: *Hoy*, *Contrato*, *Punto de sustitución*, *En producción* y *Cómo se verifica*.
- Nada en este prototipo mueve dinero real, ni toma decisiones de crédito: la consigna no lo exige ni lo autoriza.

## Qué es real y qué es simulado

| Elemento | Naturaleza | Detalle |
|---|---|---|
| Clientes, productos y transacciones | **Sintéticos**, provistos por el organizador | Se leen de un bucket de solo lectura y se cargan al warehouse. Los límites de estos datos están en `docs/data_quality.md` y `docs/dataset-audit.md`. |
| Casos de evaluación en español | **Generados por el equipo** | Salen del warehouse con etiquetas de referencia calculadas (`eval/workload.py`), no escritas a mano. |
| Turnos en portugués | **Escritos por el equipo** | El dataset no tiene portugués; es una limitación declarada en los reportes. |
| Set de mensajes humanos | **Reales**, de personas ajenas al equipo | Con consentimiento, sin datos personales (`docs/human_set.md`). Está en recolección. |
| Identidad del cliente | **Simulada** | IdP de prueba, ver frontera 1. |
| Identidad del operador | **Simulada** | Claves con nombre, ver frontera 2. |
| Servicio de rastreo | **Simulado** | Archivo JSONL, con un SLA de 2 días hábiles que es una política sintética. |
| Cola de casos | **Simulada** | Archivo JSONL. |
| Regla de revisión de rastreos (90 días) | **Política sintética** | Constante `TRACE_REVIEW_AFTER_DAYS`; la decisión final es de una persona. |
| Modelos de lenguaje | **Servicios externos reales** | Solo reciben texto enmascarado, ver frontera 6. |

---

## 1. Identidad del cliente

**Hoy.** `agent/session/identity.py`, `IdentityService.login(customer_id, pin) -> Session`. Es el "servicio de sesión de
prueba confiable" que pide la consigna: un número de cliente solo no prueba identidad.

**Contrato actual.**

- *Entrada:* `customer_id` y un segundo factor. El factor es un PIN de 6 dígitos derivado como
  `HMAC-SHA256(DEMO_IDP_SECRET, customer_id)`; el secreto vive solo en el servidor.
- *Salida:* una sesión con token opaco (24 bytes aleatorios, TTL de 15 minutos, `SESSION_TTL_SECONDS`) y los atributos
  `segment`, `country` y `customer_status`. Con `STATE_DB_PATH` la sesión sobrevive a un reinicio y en disco queda solo el hash del token.
- *Errores:* `AuthError` genérico a propósito (quien llama no aprende qué verificación falló), `LockedOut` tras 5 fallos
  en 15 minutos para ese cliente, e `IdentityUnavailable` si falta `DEMO_IDP_SECRET`: sin secreto no se emite ninguna
  sesión (falla cerrado). Un cliente desconocido o con la cuenta cerrada no puede abrir sesión.
- *Seguridad:* comparación en tiempo constante; el endpoint `POST /auth/session` además limita intentos por origen.
- *Consulta y cierre:* `GET /auth/session` con la cabecera `X-Session-Token` devuelve `customer_id`, `session_ref`, los
  atributos y el tiempo restante, sin extender la sesión (401 si no está viva). `DELETE /auth/session` la revoca y
  responde siempre 204, aunque el token no exista o ya esté revocado.
- *Frontend web:* un BFF guarda el token en una cookie httpOnly y el navegador nunca lo ve. Envía la IP del usuario en
  `X-Client-IP`; con `CLIENT_IP_HEADER=X-Client-IP` el límite de intentos es por usuario. Solo es seguro si nada más que
  el BFF puede alcanzar la API (servicio privado); si no, cualquiera elige su propia IP.
- *Datos:* aguas abajo solo circula el token; los tickets y logs llevan `session_ref`, un hash de un solo sentido.

**Punto de sustitución.** La verificación dentro de `IdentityService.login` (`derive_test_pin`). Lo que sigue igual: quien
emite la sesión siempre termina en `SessionStore.issue(customer_id, atributos)`, y el resto del sistema solo conoce el token.

**En producción.** El IdP del banco (inicio de sesión en la app, OTP o PIN de IVR), con MFA y vinculación de dispositivo;
los atributos vendrían del IdP. `/demo/customers` publica PINs de prueba y debe estar vacío (`DEMO_PUBLIC_CUSTOMERS=`)
en cualquier entorno real.

**Cómo se verifica.** `tests/test_api.py` (inicio de sesión, consulta y cierre, límite de intentos detrás del BFF),
`tests/test_durable_state.py` (sesiones tras un reinicio, solo el hash en disco).

---

## 2. Identidad del operador

**Hoy.** `agent/session/operators.py`, `OperatorDirectory`. Diseño en
`docs/superpowers/specs/2026-09-29-identidad-operador-design.md`.

**Contrato actual.**

- *Entrada:* la cabecera `X-Operator-Key`. Las claves se configuran en `OPERATOR_KEYS` (`nombre=clave`).
- *Salida:* el nombre del operador, que **sale de la clave y nunca de lo que el operador envíe**.
- *Roles:* la clave de admin solo lee; la de operador es la única que puede tomar, aprobar, rechazar y devolver.
- *Errores:* 503 si no hay claves configuradas, 401 con clave ausente o inválida, 429 tras demasiados fallos desde un origen.
  Cada intento fallido queda en el registro de auditoría sin la clave presentada. Nombres o claves repetidos, o claves
  de menos de 24 caracteres, impiden que el servicio arranque.

**Punto de sustitución.** `require_operator` en `api/main.py`: hoy consulta `OperatorDirectory`; con SSO consultaría al
proveedor de identidad y devolvería el mismo nombre.

**En producción.** SSO corporativo (OIDC) con los roles del banco y MFA. Las claves con nombre son un puente honesto,
no el destino: viven en variables de entorno y se rotan a mano.

**Cómo se verifica.** `tests/test_operators.py`, `tests/test_operator_auth.py`.

---

## 3. Datos del core bancario

**Hoy.** Un warehouse DuckDB de **solo lectura** para la capa de servicio (`agent/tools/db.py`); solo la ingesta
(`data/pipeline.py`) escribe. Sobre él hay funciones deterministas, sin modelo, en `agent/tools/account_tools.py`.

**Contrato actual.** Toda función recibe `customer_id` como primer argumento, tomado de la sesión y **nunca de lo que
dijo el modelo**.

| Función | Devuelve |
|---|---|
| `get_customer_profile` | Segmento, estado y catálogo de productos enmascarado |
| `get_account_summary` | Saldos por producto |
| `list_transactions` | Movimientos con filtros (máximo 50) |
| `get_payment_status` | Atraso y crédito disponible; solo tarjetas y préstamos |
| `get_exchange_rate` | Tipo de cambio; si falta la fecha, usa hasta 7 días antes y lo marca, o el inverso |
| `request_trace` | Movimientos pendientes candidatos a rastreo; **no abre nada** |
| `recent_activity_for_review` | Solo para el traspaso a un humano: movimientos recientes con señales de fraude |

Reglas que aplica cada función, en código:

1. **Propiedad.** Si el cliente de la sesión no es dueño del producto, se lanza `PermissionDenied` (un evento de
   seguridad, no un resultado vacío). Sale de una consulta a la base, jamás de la redacción del usuario ni del modelo.
2. **Verificación.** Solo devuelve un resultado si existen los campos que la respuesta necesita; si no, `DataUnavailable`.
   Una pregunta válida que no aplica al producto lanza `NotApplicable`, y se responde en vez de transferir.
3. **Minimización.** Números de cuenta y tarjeta salen solo con los últimos 4 dígitos.
4. **Frescura.** Todo resultado lleva `as_of`. Con `FRESHNESS_ENFORCE=1`, un warehouse más viejo que
   `FRESHNESS_SLO_HOURS` (36 por defecto) responde `DataUnavailable` en vez de un dato viejo en silencio. En el dataset
   estático la política queda apagada y toda respuesta declara su fecha.
5. **Auditoría.** Cada llamada se escribe en el registro de auditoría con el identificador de la traza.

*Taxonomía de errores* (`agent/tools/errors.py`), cada uno mapeado a una sola decisión de `agent/policy/router.py`; el
modelo nunca decide qué significa un fallo:

| Error | Decisión |
|---|---|
| `MissingSlot`, `InvalidArgument`, `ResourceNotFound` | Pedir aclaración |
| `NotApplicable` | Responder |
| `PermissionDenied` | Escalar (seguridad) |
| `DataUnavailable` | Escalar (datos) |
| Cualquier otro error | Escalar (falla de herramienta) |

**Punto de sustitución.** Estas siete funciones. Su firma y su taxonomía de errores son el contrato; la fuente puede cambiar.

**En producción.** Una API o réplica del core, con la propiedad **verificada en el servicio** (la consigna pide aplicar los
permisos en la capa de servicio o de herramientas). La ingesta pasaría de "una vez al arrancar" a una programada. Los
límites del dataset actual están en `docs/data_quality.md`. Latencia, disponibilidad y volumen: **por definir con el banco**.

**Cómo se verifica.** `tests/test_tools.py`, `tests/test_pipeline.py`, `tests/test_cross_checks.py`.

---

## 4. Servicio de rastreo (operaciones de pagos)

**Hoy.** `agent/tools/traces.py`, `TraceService`: un archivo JSONL (`TRACE_REQUESTS_PATH`). Es la **única acción** del
sistema (ADR-002) y simula el servicio de operaciones de pagos.

**Contrato actual.**

- *Abrir:* `open(customer_id, transaction_id, product_id, session_ref)` devuelve el pedido existente o uno nuevo, con
  `trace_id`, `status: "open"`, `sla_business_days: 2` (política **sintética**) y `queue: "payments_ops"`.
- *Idempotencia:* el `trace_id` es `TR-` más 16 hex de `sha256(cliente|movimiento)`: pedir lo mismo dos veces devuelve el
  mismo pedido, sin duplicar. `find` compara campo por campo y no confía en que un identificador sea único.
- *Relectura:* el orquestador vuelve a leer el pedido antes de decirle al cliente que existe. Si no se puede leer, no lo
  anuncia y lo deriva a una persona (`trace_unverified`).
- *Elegibilidad:* solo movimientos que siguen pendientes de tipo Transfer, Payment o Deposit. Uno de más de 90 días, o
  con fecha anterior a la apertura del producto o al registro del cliente, no se abre con el "sí" del cliente: lo decide
  una persona.

**Punto de sustitución.** `TraceService.open`, `find` y `get`.

**En producción.** La API de operaciones de pagos. Necesita: una **clave de idempotencia** (cliente más movimiento) que
ante un reintento devuelva el pedido ya creado; lectura inmediata tras la escritura o un estado explícito de "recibido";
y que un tiempo de espera agotado se trate como no verificado y pase a una persona, sin reintentar a ciegas. El SLA real:
**por definir con el banco**.

**Cómo se verifica.** `tests/test_trace.py` (incluye movimientos que se liquidan tras la propuesta, colisión de
identificadores y una traza que no se relee), y la revisión del juez de evaluación contra los registros del servicio.

---

## 5. Cola de casos y trabajo del operador

**Hoy.** `agent/policy/escalation.py` (`HumanQueue`, `EscalationTicket`) y `agent/policy/desk.py` (`TicketDesk`), sobre
archivos JSONL.

**Contrato actual: el ticket.** Es lo que la consigna pide entregar al agente humano: el pedido, los hechos verificados,
las acciones realizadas, la evidencia y las preguntas abiertas. Campos: `ticket_id`, `trace_id`, `category`, `priority`,
`queue`, `customer_id`, `session_ref`, `segment`, `country`, `language`, `request` (máximo 500 caracteres),
`prior_requests` (las últimas 3, cortadas a 160), `reason`, `policy_rule`, `verified_facts`, `evidence`,
`actions_taken`, `open_questions`, `suggested_next_step` y, si hay una acción que aprobar, `pending_action`.
**Nunca lleva el token de sesión**, solo `session_ref`. Las colas son `fraud_ops`, `priority_care`, `complaints`,
`security_review`, `compliance`, `payments_ops` y `account_payments_l2` por defecto.

**Contrato actual: el desk.** `TicketDesk.act(ticket_id, action, operator, expected_version, reason)` con las acciones
`claim`, `approve`, `reject` y `release`. Los estados son `open → claimed → approved | rejected | handed_back | stale`.
El estado es la reproducción de un registro de eventos que solo se agrega, bajo un lock. Repetir un resultado ya
alcanzado no hace nada; cualquier otro movimiento sobre un ticket cerrado es un conflicto (409); una decisión tomada
desde una versión vieja se rechaza; aprobar vuelve a comprobar que el movimiento siga pendiente y relee la traza. Que el
cliente se entere del resultado se cubre con `GET /case/{id}` y con un aviso en su próximo mensaje.

**Punto de sustitución.** `HumanQueue.enqueue/get` y `TicketDesk.act/state`.

**En producción.** El sistema de casos del banco. Necesita: alta idempotente por `ticket_id`; transiciones con
concurrencia optimista por versión; adjuntar evidencia; y la retención que fije el banco (aquí 90 días es un sustituto).
Cómo se asignan colas y prioridades reales: **por definir con el banco**.

**Cómo se verifica.** `tests/test_desk.py` (transiciones, aprobación desactualizada, doble aprobación, reintentos),
`tests/test_operator_labels.py`, y los tests de traspaso de `tests/test_orchestrator.py`.

---

## 6. Proveedores de modelos de lenguaje

**Hoy.** `agent/llm/client.py`, `LLMClient`: Anthropic, Groq y Together, en el orden de `LLM_PROVIDERS`. Uno sin su clave
se omite.

**Contrato actual de confiabilidad.**

- Cada pedido tiene un plazo (`LLM_TIMEOUT_SECONDS`, 12 s) y cada turno un presupuesto total de tiempo
  (`LLM_TOTAL_BUDGET_SECONDS`, 25 s).
- Solo se reintentan fallas transitorias (tiempos de espera, conexión, 429, 5xx), con espera exponencial con
  variación aleatoria y sin dormir tras el último intento. Las permanentes (autenticación, pedido inválido) pasan al
  siguiente proveedor.
- Un cortacircuitos por proveedor lo saltea si acaba de fallar varias veces: una caída cuesta un plazo, no uno por pedido.
- Si todos fallan se lanza `LLMUnavailable` y el orquestador escala o corre en modo degradado. Nunca responde por su cuenta.
- Un tope diario de gasto (`LLM_DAILY_BUDGET_USD`) hace que, superado, el sistema corra como si el modelo estuviera caído.
- Una llamada a una herramienta que Groq rechaza por un campo `null` se recupera del propio mensaje de error.

**Contrato de privacidad** (la consigna prohíbe registros privados en pedidos externos a modelos).

- Al modelo solo llega lo que el cliente escribió, **enmascarado** por `agent/llm/privacy.py`: identificadores internos,
  CURP y RFC, tarjetas y números largos, correos. El orquestador nunca agrega un registro al contexto del modelo.
- El modelo **solo propone qué herramienta usar**. Su texto nunca se le muestra al cliente: la respuesta la arma el código
  a partir de resultados verificados (ADR-001).
- La evidencia es la métrica `records_sent_to_model`, que la evaluación mide en cada corrida.
- Límites conocidos: nombres, direcciones y números de menos de 8 dígitos escritos en texto libre no se detectan
  (`LIMITATIONS.md`).

**Punto de sustitución.** `default_providers` y `candidate_client` en `client.py`. Además, `agent/core/experiments.py` deja preparados shadow y canary, para
comparar un modelo candidato con tráfico real antes de cambiarlo.

**En producción.** Un modelo dentro del perímetro del banco o una pasarela aprobada, con acuerdo de tratamiento de
datos, residencia de datos y gestión de claves. Cuotas, latencia y costo reales: **por definir con el banco**.

**Cómo se verifica.** `tests/test_llm_client.py`, `tests/test_privacy.py`, `tests/test_experiments.py`, la evaluación
adversarial (`make eval-adversarial`, con un modelo deliberadamente malo) y la compuerta de calidad del CI.

---

## 7. Observabilidad, auditoría y retención

**Hoy.** `agent/tools/audit.py` y archivos JSONL bajo `data/warehouse/`.

**Contrato actual.** Los registros se correlacionan por `trace_id`; lo que se guarda son **registros de ejecución**, no el
razonamiento oculto del modelo, que la consigna no acepta como artefacto de auditoría.

| Registro | Contenido | Retención |
|---|---|---|
| `audit_log.jsonl` | Una línea por llamada a una herramienta, y los intentos fallidos de operador | 30 días |
| `traces.jsonl` | Una línea por turno: intentos al modelo y su uso, política aplicada, latencia, costo y cohorte | 30 días |
| `ticket_events.jsonl` | Cada decisión del operador, con su nombre | Sin política de retención definida |
| `human_queue.jsonl` | Los tickets | 90 días (sustituto) |

La retención corre a diario con `python -m ops.retention`. Los endpoints de solo lectura (clave de admin) son
`/admin/human_queue`, `audit_log`, `trace_log`, `traces/{id}`, `ops`, `llm_budget`, `data_quality`, `drift` y
`experiments`. Los umbrales de alerta están especificados en `docs/operations.md` pero **no están conectados a un stack
de métricas**.

**Punto de sustitución.** `_JsonlSink.write(record)` en `audit.py`: es donde un SIEM o una canalización de logs recibiría
cada registro.

**En producción.** Un destino de solo escritura (a prueba de manipulación), con retención por política de la plataforma y
alertas cableadas. Hoy **no hay evidencia de manipulación** (un encadenamiento por hash está pensado, no hecho), y las
ventanas en memoria son de 1000 registros de auditoría y 500 de trazas.

**Cómo se verifica.** `tests/test_api.py` (el registro de trazas y que ningún registro exponga el token) y `tests/test_drift.py`.

---

## Trabajo restante antes de desplegar

Es la lista consolidada de lo que separa este prototipo de un servicio real. El detalle de cada punto está en la
frontera correspondiente y en `LIMITATIONS.md`.

1. **Identidad:** IdP del banco con MFA para clientes y SSO con roles para operadores.
2. **Core:** API o réplica con la propiedad de recursos verificada en el servicio, e ingesta programada.
3. **Rastreo:** API de operaciones de pagos con clave de idempotencia y lectura tras escritura.
4. **Casos:** integración con el sistema de casos del banco y su retención regulatoria.
5. **Modelos:** un modelo dentro del perímetro del banco, con acuerdo de tratamiento de datos.
6. **Observabilidad:** un destino a prueba de manipulación, alertas cableadas al stack de métricas y cifrado en reposo.
7. **Escala:** el estado en SQLite tiene un solo escritor; varias réplicas necesitan Redis o Postgres.
8. **Evaluación:** repetir la medición con datos y tráfico reales. Las cifras actuales son offline y de simulador, y
   **no son una mejora medida en producción**.
