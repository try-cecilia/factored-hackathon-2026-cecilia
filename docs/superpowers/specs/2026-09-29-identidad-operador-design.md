# Identidad por operador: diseño

- **Estado:** propuesto, 2026-09-29
- **Sub-proyecto 1 de 3** de "cumplimiento" (orden acordado: identidad del operador → registro de auditoría encadenado → documento de puntos de integración).
- **Depende de:** el desk del operador (PR #8). **Lo necesita:** el registro encadenado, que solo prueba "quién hizo qué" si la identidad es real.

## Problema

Hoy los endpoints de admin comparten una clave (`ADMIN_API_KEY`, `require_admin` en `api/main.py`) y el operador es un texto que viaja en el cuerpo de la petición (`DeskAction.operator`). Consecuencias:

1. **Cualquiera con la clave puede firmar como cualquier operador.** El nombre en `ticket_events.jsonl` es una declaración, no una identidad.
2. **Quien puede leer la cola también puede aprobar y rechazar.** No hay separación entre observar y actuar sobre dinero del cliente.
3. **Un intento fallido no deja rastro** y no hay límite de intentos: la clave se puede adivinar sin freno.

## Objetivo

Que cada acción del operador quede atribuida a una persona concreta, que actuar exija una credencial distinta de la de leer, y que adivinar credenciales tenga costo. Sin infraestructura nueva.

## Fuera de alcance

MFA, un proveedor de identidad (SSO/OIDC), rotación automática de claves, permisos por cola o por monto, y regla de dos personas. Se documentan como el camino a producción, no se construyen.

## Decisiones (aprobadas)

| Decisión | Elegido | Descartado y por qué |
|---|---|---|
| Mecanismo | Claves con nombre en el entorno, comparadas en tiempo constante; el nombre del operador **sale de la clave** | Tokens firmados de un IdP o login con PIN como los clientes: infraestructura que no entra antes del 7/10 |
| Roles | La clave de admin **solo lee**; la clave de operador puede tomar, aprobar, rechazar y devolver | Una clave para todo: no separa observar de actuar |
| Auditoría | Cada acción **y cada intento fallido** se registra | Solo el desk: un ataque de adivinación no dejaría rastro |
| Intentos inválidos | Límite por origen, como el login de clientes | Sin límite: la clave se adivina |

## Diseño

### Configuración

`OPERATOR_KEYS` es una lista `nombre=clave` separada por comas, por ejemplo `ana=…,beto=…`. Reglas al cargarla:

- Un nombre es `[a-z0-9_.-]{1,40}`. Un nombre repetido o una clave repetida hace que **el arranque falle**: dos personas con la misma clave romperían la atribución.
- Una clave debe tener al menos 24 caracteres. Más corta, el arranque falla.
- Vacía o ausente: los endpoints de operador quedan **deshabilitados** (503), igual que hoy los de admin sin `ADMIN_API_KEY`. Falla cerrado.

### Componente nuevo: `agent/session/operators.py`

Una unidad con un propósito: dada una clave presentada, devolver el nombre del operador o nada.

- `OperatorDirectory.from_env()` construye el directorio y valida las reglas de arriba.
- `authenticate(presented: str | None) -> str | None`. Compara contra **todas** las claves con `hmac.compare_digest` y no corta al primer acierto, para que el tiempo de respuesta no revele cuántas claves probó ni cuál coincidió.
- No guarda ni imprime claves. Solo conserva su hash SHA-256 en memoria, para que un volcado del proceso no las muestre en claro.

No depende de FastAPI ni del desk. Se prueba sola.

### Cambios en la API (`api/main.py`)

- Nuevo `require_operator`: lee la cabecera `X-Operator-Key`, aplica el límite de intentos, autentica, y entrega el nombre al endpoint.
- Los endpoints `POST /admin/tickets/{id}/{claim|approve|reject|release}` pasan de `require_admin` a `require_operator`. **`DeskAction.operator` desaparece del cuerpo**: el nombre lo pone el servidor. `expected_version` y `reason` se mantienen.
- Los endpoints de lectura siguen con `require_admin`. Un operador **no** hereda acceso de lectura de admin ni al revés; si una persona necesita ambos, tiene las dos claves.
- Límite de intentos: `RateLimiter` existente, con clave por origen (`client_ip`), variable `OPERATOR_AUTH_FAILS_PER_MIN` (defecto 10). Solo cuentan los **fallos**; superado el límite, 429.

### Registro de los intentos fallidos

Un intento con clave inválida o ausente, o bloqueado por el límite, se escribe en el registro de auditoría (`agent/tools/audit.py`) como un evento `operator_auth_failed` con origen y momento, **sin la clave presentada** (ni su prefijo). Cuando llegue el sub-proyecto 2, ese registro estará encadenado y esos intentos quedarán dentro de la cadena.

### Qué queda en `ticket_events.jsonl`

`operator` deja de ser texto libre: es el nombre autenticado. El desk (`TicketDesk.act`) sigue recibiendo un nombre, y no cambia. La garantía nueva vive en la frontera: solo `require_operator` puede producirlo.

## Manejo de errores

| Situación | Respuesta |
|---|---|
| `OPERATOR_KEYS` vacía | 503, "operator endpoints disabled" |
| Sin cabecera o clave inválida | 401, mensaje genérico (no distingue "clave inexistente" de "clave incorrecta") |
| Demasiados fallos desde un origen | 429 |
| Configuración inválida (repetidos, claves cortas, nombres mal formados) | El proceso no arranca, con un mensaje que nombra el problema sin imprimir claves |

## Pruebas (criterios de aceptación)

1. Una clave válida devuelve su nombre; una inválida o ausente, nada.
2. **El nombre en el evento del desk es el de la clave**, aunque el cuerpo intente enviar otro (el campo ya no existe: un `operator` extra en el cuerpo se ignora y nunca llega al desk).
3. La clave de admin **no** puede aprobar, y la de operador **no** puede leer la cola.
4. Nombres repetidos, claves repetidas o claves cortas hacen fallar la carga de la configuración.
5. Sin `OPERATOR_KEYS`, los endpoints devuelven 503.
6. Tras N fallos desde un origen, el siguiente intento, incluso con clave correcta, da 429. Otro origen no se ve afectado.
7. Cada intento fallido deja un evento en el registro de auditoría que **no contiene la clave presentada**.
8. Dos operadores distintos no pueden actuar sobre el ticket que tomó el otro (el desk ya lo garantiza; se prueba de punta a punta con dos claves).

## Riesgos y límites que se documentan

- Las claves viven en variables de entorno y se rotan a mano; un operador que se va exige cambiar su clave y reiniciar.
- Sin MFA, y una clave filtrada permite actuar como esa persona hasta que se rote.
- El límite de intentos está en memoria del proceso y se reinicia con él.
- El camino a producción es SSO corporativo (OIDC) con roles del banco, y las claves con nombre son un puente honesto, no el destino.

## Decisiones abiertas

Ninguna: las cuatro decisiones de diseño están aprobadas arriba.
