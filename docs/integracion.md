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
los atributos vendrían del IdP. `/demo/customers` publica PINs de prueba: solo existe con `DEMO_MODE=1` (404 en cualquier
otro caso) y debe quedar apagado en cualquier entorno real.

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

**Consola web de operador** (`web/`, rutas `/operador/*`). Cola humana, detalle con evidencia y acciones, monitoreo de solo
lectura y trazas. Cómo se configuran las claves:

| Dónde | Qué se configura |
|---|---|
| API | `ADMIN_API_KEY` (lee: cola, tickets, monitoreo, trazas) y `OPERATOR_KEYS=ana=…,beto=…` (actúa: tomar, aprobar, rechazar, devolver). Cada clave de operador de 24 caracteres o más. |
| Web (servidor) | `AGENT_API_URL`, **`WEB_PUBLIC_ORIGIN`** (obligatoria en producción) y `TRUSTED_CLIENT_IP_HEADER` si hay un proxy. **Las claves no van en el entorno de la web**: cada persona escribe las suyas en `/operador/login`. |
| API, detrás del BFF | `CLIENT_IP_HEADER=X-Client-IP`, igual que para el login de clientes. Sin eso, el límite de intentos fallidos (`OPERATOR_AUTH_FAILS_PER_MIN`) cuenta por la IP del BFF y diez claves mal escritas bloquean a todos los operadores. Solo es seguro si nada más que el BFF alcanza la API. |

- *Lectura y acción separadas, como en la API.* El ingreso pide la clave de lectura y, opcionalmente, la de operador. Con
  solo la de lectura la sesión es de **solo lectura**: ve todo y no puede actuar; la consola ofrece agregar la clave de
  operador sin volver a ingresar. La clave de operador se comprueba con `GET /admin/operator/me`, que devuelve el nombre
  al que pertenece sin tocar ningún ticket; ese nombre es el que la consola muestra y el que queda en
  `ticket_events.jsonl`. El ingreso exige la clave de lectura porque un operador sin ella no podría ver ni la cola.
- *Cómo viaja la clave.* Se **tipea en un formulario HTML nativo** (`<form method="post">`, campos `type="password"` sin
  estado de React), va **una sola vez** al BFF por POST (`/operador/sesion` para ingresar, `/operador/clave` para sumar
  la de operador, `/operador/salir`) y **nunca se guarda ni se devuelve al navegador**: el BFF la comprueba contra la API,
  la guarda en su memoria y responde con una redirección 303 (post/redirect/get) que solo lleva un destino y, a lo
  sumo, un código fijo como `operator_401` en una cookie de un solo uso. Como es un formulario nativo, funciona sin
  JavaScript, y ningún estado, store, log ni respuesta del cliente contiene la clave. Un chequeo lo sostiene:
  `make web-test` (`pnpm --dir web test:all`) prueba la lógica del formulario con claves de mentira, comprueba que ni el
  destino ni el código de error las contienen, y falla si un componente de la consola guarda una clave en estado,
  controla un campo de contraseña o pasa una clave a una función de servidor. Además hay pruebas HTTP contra el handler del
  build de producción (`web/tests/http/`, con una API falsa): CSRF, destinos de redirección hostiles y rotación de sesión.
- *Formularios protegidos contra CSRF.* Los tres POST (`/operador/sesion`, `/operador/clave`, `/operador/salir`) se rechazan
  con 403, sin tocar cookies, si no prueban venir de una página de la consola: `Sec-Fetch-Site`, cuando el navegador lo
  manda, tiene que ser `same-origin`; `Origin` (o `Referer` si falta) tiene que ser **exactamente el origen público**
  (esquema, host y puerto); sin ninguna de las dos cabeceras no hay prueba y se rechaza. `SameSite=Strict` no alcanzaba
  para el ingreso porque todavía no hay cookie. El origen público sale de **`WEB_PUBLIC_ORIGIN`** en el servidor de la web
  (por ejemplo `https://console.bank.example`, sin ruta), nunca de cabeceras de proxy: una página `http://` del mismo host
  no puede forzar un ingreso sobre `https://`. **En producción es obligatoria**: sin ella, o con un valor que no sea un
  origen http(s), todos los POST de la consola dan 403 y el servidor escribe en el log qué falta. En desarrollo, si está
  vacía, se usa el origen de la URL de la petición (`http://127.0.0.1:<puerto>`). Está en `web/.env.example`.
- *Sesión nueva en cada ingreso y en cada elevación.* Un ingreso siempre crea un identificador nuevo y termina la sesión
  que ese navegador tuviera; agregar la clave de operador también cambia el identificador y el anterior deja de valer, así
  que una cookie de solo lectura copiada no gana permisos de acción. El tope de 8 horas sigue contando desde el ingreso original. La sesión anterior se consume en un solo paso
  (tomar y borrar): de dos ingresos simultáneos con la misma cookie solo uno crea sesión; el otro vuelve al ingreso con un
  aviso y **sin tocar la cookie de sesión** (un borrado que llegara después del Set-Cookie del ganador dejaría esa sesión
  huérfana). Si el navegador perdió la respuesta ganadora, la cookie vieja se rechaza durante 30 segundos y luego se trata
  como una cookie desconocida. Ninguna respuesta a un identificador muerto (vencido, reemplazado o desconocido) borra la cookie de
  sesión: solo la borra el cierre de sesión explícito, y un ingreso nuevo la sobrescribe; así una respuesta lenta a un GET no
  puede borrar la sesión que otro ingreso acaba de fijar.
- *Destino tras el ingreso.* Se decodifica y normaliza como lo haría un navegador (puntos, `%2f`, `%5c`, tabuladores,
  barras invertidas) y solo se acepta una ruta propia que no empiece con `//`; ante la duda va a `/operador/cola`.
- *Dónde viven las claves.* Nunca en el JavaScript del navegador, en `localStorage` ni en una cookie. El servidor de la web
  (BFF) las guarda **en memoria**, atadas a un identificador aleatorio de 256 bits que viaja en una cookie
  `httpOnly` + `SameSite=Strict` (y `Secure` con prefijo `__Host-` en producción). La sesión vence a los 30 minutos sin
  actividad de la persona (el refresco automático de la cola y del monitoreo **no** cuenta como actividad) o a las 8
  horas, y se descarta si la API rechaza la clave (rotada o revocada). Al vencer, la consola vuelve al ingreso con un aviso.
  `OPERATOR_IDLE_SECONDS` (en el servidor de la web, por defecto 1800, mínimo 10) acorta esa ventana para probar el vencimiento.
- *Alternativa descartada y por qué.* Una cookie sellada con las claves adentro evita el estado en el servidor, pero
  pone las claves (cifradas) en el navegador, exige un secreto de sellado que rotar y no permite cerrar una sesión robada
  desde el servidor. **Costo de la elección:** las sesiones viven en la memoria de un solo proceso, así que un reinicio
  o una segunda réplica sin afinidad de sesión obliga a volver a ingresar. Para un puñado de operadores es aceptable; con
  varias réplicas hace falta un almacén compartido (Redis) o pasar al SSO.
- *`SameSite=Strict`.* Frena el envío de la cookie desde otro sitio, que es la defensa contra CSRF de las acciones; el
  costo es que un enlace a la consola desde otra app (un chat, un correo) abre primero el ingreso.
- *Errores.* 401 (clave rotada) cierra la sesión o pide de nuevo la clave de operador; 403 en la web significa "sesión
  de solo lectura"; 409 (otra persona movió el caso, o la pantalla estaba vieja: cada acción envía la `version` que se
  vio) recarga el estado y muestra el panel de conflicto ("No se aplicó: el caso cambió", de `v3` a `v4`, con quién lo movió); mientras ese aviso está
  visible no se puede decidir hasta usar "Recargar caso". 429 y 503 se explican en pantalla. Tomar, aprobar, rechazar y devolver actúan con
  un clic (como en el artboard aprobado), sin diálogo de confirmación: la protección es `expected_version` más el nombre de la clave en el historial.
- *Datos del cliente.* La consola muestra lo que la API ya devuelve a la clave de lectura: el ticket (con su
  `customer_id`, el pedido recortado y la evidencia). De las trazas **no** muestra el texto de la respuesta, lo que vio el
  modelo ni los argumentos de las herramientas: el BFF deja pasar solo un conjunto fijo de campos (`loadTraceLog` y
  `loadTrace` en `web/src/server/operator.functions.ts`).
- *Probarlo sin datos reales ni claves de modelo:* `python -m ops.seed_operator_demo --dir /tmp/cecilai-operator-demo`
  arma un warehouse mínimo, genera claves nuevas y llena la cola y las trazas con turnos de verdad; imprime las claves y
  deja `operator-demo.env` para cargar antes de `uvicorn`. Las capturas del recorrido están en `docs/demo/operador-kit-*.png`.

- *Cómo está armada la pantalla.* Es el diseño aprobado de Paper (artboards "Operator · Queue" y "Operator · Ticket states", copias en
  `docs/demo/paper-operator-*.jpg`) sobre el kit: sidebar compacto con las vistas (Todos abiertos, Míos, Sin asignar), las siete colas
  con su cantidad de casos pendientes y los registros (monitoreo y trazas); tabla compacta (`DataTable`) con orden por columna, pestañas
  de estado, filtros de prioridad, país e idioma, búsqueda (`Ctrl`/`Cmd` + `K`) y paginación de 25; y el detalle del caso en un panel
  tonal a la derecha. Los filtros viven en la URL de `/operador/cola` (`vista=mias|sin-asignar`, `cola`, `estado=abiertos|tomados|decididos`,
  `prioridad`, `pais`, `idioma`) y se validan en `web/src/routes/-operator/queue.ts`. La cola se lee en el layout `/_operator` (no en la
  ruta de la cola) para que el sidebar tenga sus conteos en todas las páginas; el sondeo cada 30 s también se mudó ahí y sigue pasando
  por `refreshQuietly`. La evidencia marca como riesgo los movimientos que la API marcó o cuyo score llega a 70
  (`FRAUD_SCORE_FLAG` en `agent/policy/escalation.py`). Los textos de la consola están en `web/src/i18n/dict/{es,pt}/operator.ts` y
  `monitor.ts`; lo que viene de la API (pedido del cliente, motivos, próximos pasos) se muestra tal cual, sin traducir.

**Cómo se verifica.** `tests/test_operators.py`, `tests/test_operator_auth.py` (incluye `/admin/operator/me`) y, para la consola,
`make web-test web-typecheck web-build` más el recorrido con capturas de `docs/demo/operador-kit-*.png` (`LIMITATIONS.md` dice qué
no cubre).

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
| `audit_log.jsonl` | Una línea por llamada a una herramienta, los intentos fallidos de clave y cada purga de retención | 30 días |
| `traces.jsonl` | Una línea por turno: intentos al modelo y su uso, política aplicada, latencia, costo y cohorte | 30 días |
| `ticket_events.jsonl` | Cada decisión del operador, con su nombre | con el ticket (se borran juntos, ya fuera de la cola y con el último evento de más de 90 días) |
| `human_queue.jsonl` | Los tickets | 90 días (sustituto) |
| `trace_requests.jsonl` | Los pedidos de rastreo | 90 días |
| sesiones y conversaciones (SQLite) | Solo el hash del token; el historial enmascarado | vencidas al purgar; 1 día |

La retención la aplica `python -m ops.retention` (una política para todos los almacenes, cada período en una variable
`RETENTION_*_DAYS`); el contenedor la corre en un bucle diario, es idempotente y cada corrida queda registrada como evento
`retention_purge` en la auditoría. Los endpoints de solo lectura (clave de admin) son `/admin/human_queue`, `audit_log`,
`trace_log`, `traces/{id}`, `ops`, `llm_budget`, `data_quality`, `drift` y `experiments`. `GET /metrics` (formato Prometheus,
con `METRICS_TOKEN` o la clave de admin), `/livez` y `/readyz` completan la observabilidad, y `ops/alerts.yml` trae las reglas de
alerta. Las reglas y un dashboard de Grafana corren en el compose local (`make monitoring-up`); **no hay un Alertmanager ni un
canal de notificación conectado**. Detalle y comandos: `docs/operations.md` (Monitoring, Access control, Data retention).

**Punto de sustitución.** `_JsonlSink.write(record)` en `audit.py`: es donde un SIEM o una canalización de logs recibiría
cada registro.

**En producción.** Un destino de solo escritura (a prueba de manipulación), con retención por política de la plataforma y
alertas cableadas. Hoy **no hay evidencia de manipulación** (un encadenamiento por hash está pensado, no hecho), y las
ventanas en memoria son de 1000 registros de auditoría y 500 de trazas.

**Cómo se verifica.** `tests/test_api.py` (el registro de trazas y que ningún registro exponga el token), `tests/test_drift.py`,
`tests/test_retention.py`, `tests/test_metrics.py` y `tests/test_alerts.py`.

---

## 8. Frontend web del cliente

**Hoy.** `web/` (TanStack Start, React 19). El navegador nunca habla con la API de Python: lo hace un BFF, con
funciones de servidor en `web/src/server/`, y el token de sesión vive en una cookie httpOnly (ver frontera 1). La ruta
`/chat` (`web/src/chat/`) es el chat del cliente; el shell y los estilos siguen el diseño "Cecil.ai" de Paper, y sus
tokens están en `web/src/tokens.css` con los mismos nombres que en Paper (`--color-cecil-blue`, `--color-gray-500`,
`--radius-app`...). La consola del operador debe reutilizar esas variables, no redefinirlas. Nada depende de la nube: Inter y DM Mono salen
de paquetes npm (`@fontsource`) y quedan dentro del build, y el avatar de Cecilia está en `web/public`; no hay CDN ni
Google Fonts.

**Cómo correrlo.**

```bash
make web-setup                 # Node 24, pnpm 10.33.2, dependencias fijadas
make serve-all                 # con el warehouse real (make ingest o ingest-demo) y una clave de modelo
make serve-all-fixture         # sin S3 ni claves: warehouse de los tests y un modelo simulado
```

Web en `http://127.0.0.1:3000`, API en `http://127.0.0.1:8000`. Variables del frontend (o `web/.env`):
`AGENT_API_URL` (por defecto `http://127.0.0.1:8000`) y `TRUSTED_CLIENT_IP_HEADER` (ver frontera 1). Con `DEMO_MODE=1`
en la API el chat muestra, aparte y marcado como **Demo**, los escenarios guiados, las fallas (vencer la sesión,
modelo caído), "¿Por qué?" en cada respuesta y la vista del banco de la sesión; sin `DEMO_MODE` nada de eso se dibuja.
`make serve-fixture` deja `DEMO_MODE=1` salvo que lo pises (`DEMO_MODE=0 make serve-fixture`).

`ops/serve_fixture.py` es una **simulación offline**: el código posterior al modelo (políticas, herramientas, plantillas,
tickets, rastreos, sesiones) es el real, pero qué herramienta pedir lo decide una coincidencia de palabras, no un modelo.
Sirve para desarrollar y mostrar el front; no dice nada de cómo se comporta un modelo real.

**Contrato que usa el BFF.**

| Función de servidor | Llamada a la API | Qué devuelve al navegador |
|---|---|---|
| `sendMessage` | `POST /chat` con `session_token` (lo agrega el servidor) y `Idempotency-Key` (un UUID por mensaje, que el cliente conserva en los reintentos), plazo de 35 s | La respuesta (`disposition`, texto, idioma, `category`, `ticket_id`, y `why` solo en demo) o un motivo de fallo |
| `getCase` | `GET /case/{ticket_id}` | Estado del caso y el texto de novedad, o `not_found` |
| `getDemoKit`, `startScenario`, `applyDemoFault`, `getDemoTickets` | `/demo/*` | Solo con `DEMO_MODE=1`; los PIN de prueba se quedan en el servidor |

La propuesta de rastreo se reconoce por `disposition=CLARIFY` y `category=confirm_action`, y se responde con un "Sí" o "No"
que el código de la API evalúa (nunca el modelo). Una aclaración se dibuja como lista de opciones cuando el texto trae
`1) ...; 2) ...`; si no calza con ese formato se muestra el texto tal cual.

**Fallas, y qué ve el cliente.**

| Situación | Qué pasa |
|---|---|
| Sesión vencida (`REAUTH_REQUIRED`, HTTP 401 o cookie ausente) | El BFF borra la cookie y el chat va a `/login?redirect=/chat&motivo=expired`, con aviso; al ingresar vuelve al chat (la conversación empieza de cero) |
| 429 | Aviso en la conversación y botón "Reintentar"; no se reenvía solo |
| API caída, conexión cortada o plazo agotado | Resultado incierto: "No pude confirmar si el servicio recibió tu mensaje", con "Reintentar" manual. El reintento es seguro porque viaja con la misma clave: si la API ya lo procesó, devuelve la misma respuesta y no crea otro ticket ni confirma dos veces |
| Respuesta que no calza con el contrato | "Recibí una respuesta que no pude mostrar" y "Reintentar" |
| Doble envío | Un turno a la vez: el compositor se bloquea mientras envía, y el BFF rechaza un segundo envío de la misma sesión mientras el primero corre |

**Idempotencia de `POST /chat`.** Con la cabecera `Idempotency-Key` (8 a 64 caracteres: letras, dígitos, `-` o `_`), la API
(`api/idempotency.py`) guarda la respuesta por (sesión, clave) mientras viva la sesión (`SESSION_TTL_SECONDS`, 900 por
defecto), en el mismo SQLite de sesiones y conversaciones (`STATE_DB_PATH`, o memoria). La misma clave devuelve la misma
respuesta con `Idempotent-Replayed: true`, sin volver a correr el turno y sin gastar cupo del límite de mensajes; un
reintento que llega mientras el primero corre espera su respuesta. Antes de entregar un replay se comprueba que la
sesión siga viva (también después de esperar): con la sesión cerrada o vencida la respuesta es `REAUTH_REQUIRED`, como en
un turno normal. La misma clave con otro texto es un 422. No se guardan las respuestas de sesión vencida ni los errores. Un turno que falla después de empezar (por ejemplo, el ticket
ya se creó y falla el log de trazas) deja la clave marcada: el reintento recibe 409 y nunca un segundo turno; el lugar solo
se devuelve si el turno se rechazó antes de empezar (429, sesión terminada).
Pasadas 50 000 respuestas guardadas, las más viejas pierden la respuesta pero conservan una marca (hash de la clave):
un reintento de esa clave recibe un 409 "already processed" en vez de volver a ejecutarse, y la UI dice "Ya lo
recibimos, pero la respuesta ya no está guardada". Las marcas de sesiones vivas no se expulsan nunca: con 500 000 claves
retenidas, un turno nuevo se rechaza antes de ejecutarse (503 con `Retry-After`, sin efectos), y cada turno toma su lugar
en la misma transacción que comprueba el tope. Sin la cabecera, el comportamiento es el de siempre. Con
`DEMO_MODE=1` la respuesta guardada incluye `why` y `policy_rule`, y un replay los filtra según el modo vigente.

**Punto de sustitución.** El BFF solo conoce `POST /chat` y `GET /case/{id}`; con el core real el contrato no cambia.

**En producción.** Falta un `POST /auth/session/refresh` para ofrecer "Seguir conectado" antes de que venza.

**Cómo se verifica.** `make web-typecheck`, `make web-test` (formato de las aclaraciones, envío, 401, clave de idempotencia),
`tests/test_idempotency.py` (API) y `make web-build`; el flujo
completo se probó en el navegador con `make serve-all-fixture`, y las capturas están en `docs/demo/web-*.png`
(login, chat vacío, propuesta de rastreo, escalamiento con número de caso, sesión vencida y su aviso previo, aclaración,
límite de tasa, API caída, plazo agotado, escenario en portugués, móvil, respuesta inesperada, chat sin `DEMO_MODE`).

### UI kit, i18n y galería

**Cómo usar el kit.** Los componentes viven en `web/src/ui/` y salen de un solo punto:
`import { Button, DataTable, Sidebar, AnswerMessage, Toast } from '../ui'`. Son presentacionales (reciben props, no llaman a
la API), no dibujan bordes (solo el botón `outline` y el anillo de foco) y consumen únicamente variables de
`web/src/tokens.css`; cada uno trae su CSS al lado, con clases `ui-*` que no chocan con las de `styles.css`. Las áreas son
`Button` e `IconButton`; `loaders/` (`Spinner`, `ThinkingDots`, `CheckingSteps`, `Skeleton`, `Progress`, `DeliveryStatus`,
`PageLoader`, `Toast`); `sidebar/` (cliente, rail, operador, menú de fila, vacío y cargando); `table/` (`DataTable` cómoda
de 48 px y compacta de 32 px, selección con `BulkActionBar`, orden, `Pagination`); `messages/` (un componente por
variante del chat, y `resolveMessage` que traduce la disposición de la API a una variante: AUTO_RESOLVE es respuesta,
CLARIFY aclaración, ABSTAIN rechazo, ESCALATE pase a una persona, REAUTH_REQUIRED ingresar de nuevo). Las respuestas de la
asistente llegan por props ya en el idioma del cliente y no se traducen. La lógica con reglas (orden, selección,
paginación, estados de entrega, mapeo de disposiciones) está en archivos `.ts` puros con tests.

**Idioma.** Español (`es`) y portugués de Brasil (`pt`). El servidor lo resuelve en este orden: cookie `cecilai_lang`,
después `Accept-Language`, después `es` (`web/src/i18n/resolve.ts`); el loader de la ruta raíz lo entrega, así el HTML sale
en el idioma correcto y `<html lang>` es `es` o `pt-BR`. `LanguageSwitcher` guarda la cookie (un año, no es un secreto) y
recarga los datos de la ruta sin recargar la página. El español de la interfaz es neutro para Argentina, México y
Colombia: sin voseo ni tuteo imperativo (infinitivos y construcciones nominales: "Reintentar", "Intentar de nuevo").

**Cómo agregar un texto.**

1. Escribirlo en el diccionario español del área, en `web/src/i18n/dict/es/<área>.ts` (objeto anidado; los valores
   dinámicos van como `{nombre}`).
2. Escribir su traducción en `web/src/i18n/dict/pt/<área>.ts`. Está tipado contra el español: si falta una clave o sobra
   una, `make web-typecheck` falla.
3. Usarlo: `const t = useT()` y `t('shell.customer', { id })`. Fuera de React, `translate(locale, clave, params)`. El título
   de una ruta usa `headTitle(matches, clave)`. Una clave inexistente no compila.

`make web-test` comprueba además que las dos lenguas tengan las mismas claves y los mismos marcadores, y que el español no
tenga voseo. Un área nueva se agrega como un archivo en cada `dict/` y una línea en `es.ts` y `pt.ts`.

**Galería.** `/dev/ui` muestra cada componente en todas sus variantes y estados, para cotejarlos contra los artboards de
Paper; con `?both=1` dibuja el kit entero en español y en portugués. Existe con `make serve-web` (desarrollo) o con un
build arrancado con `UI_GALLERY=1`; en cualquier otro build responde 404 y su código va en un chunk aparte que el
cliente nunca descarga. Los estados que solo se alcanzan con el puntero o el teclado (hover, pressed, focus) se dibujan
con la prop `forceState`. Las capturas de la galería contra Paper están en `docs/demo/ui-kit-*.png`.

---

## Levantar todo con un comando

Todo se levanta y se prueba en Docker local, sin cuentas, sin S3 y sin claves de API; los servicios en la nube (S3, Render,
proveedores de modelos) son opciones, nunca requisitos.

```bash
make up                 # API + web sobre el warehouse de fixtures; escribe .env con secretos nuevos; http://127.0.0.1:3000 y :8000
make monitoring-up      # además Prometheus (con las reglas de alerta) y Grafana con su dashboard: :9090 y :3001
make up-dataset RAW_DIR=/ruta/a/data/raw   # tus CSV locales, montados de solo lectura, ingeridos en el primer arranque
make up-llm-local       # además un modelo local (Ollama en Docker); make up-llm-host usa el Ollama del host
make compose-e2e        # levanta todo desde cero en un proyecto aparte y descartable, lo comprueba de punta a punta y lo baja (es el job `compose` del CI)
make down               # baja el stack; sus volúmenes se conservan
make clean-volumes      # además borra los volúmenes (pregunta antes)
```

Sin clave de modelo el asistente corre en modo degradado seguro: saldos simples desde datos verificados y todo lo demás a una
persona. Requisitos de RAM y disco de los modelos locales, y por qué en macOS conviene el Ollama del host: `docs/operations.md`
("Local development").

## Trabajo restante antes de desplegar

Es la lista consolidada de lo que separa este prototipo de un servicio real. El detalle de cada punto está en la
frontera correspondiente y en `LIMITATIONS.md`.

1. **Identidad:** IdP del banco con MFA para clientes y SSO con roles para operadores.
2. **Core:** API o réplica con la propiedad de recursos verificada en el servicio, e ingesta programada.
3. **Rastreo:** API de operaciones de pagos con clave de idempotencia y lectura tras escritura.
4. **Casos:** integración con el sistema de casos del banco y su retención regulatoria.
5. **Modelos:** un modelo dentro del perímetro del banco, con acuerdo de tratamiento de datos.
6. **Observabilidad:** un destino a prueba de manipulación, las alertas de `ops/alerts.yml` conectadas a un canal de notificación, y cifrado en reposo.
7. **Escala:** el estado en SQLite tiene un solo escritor; varias réplicas necesitan Redis o Postgres.
8. **Evaluación:** repetir la medición con datos y tráfico reales. Las cifras actuales son offline y de simulador, y
   **no son una mejora medida en producción**.
