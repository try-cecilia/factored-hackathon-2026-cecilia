# Identidad por operador: plan de implementación

> **Para quien lo ejecute:** usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans, tarea por tarea. Los pasos usan casillas `- [ ]` para llevar el avance.

**Objetivo:** que cada acción del operador quede atribuida a una persona concreta, con una credencial distinta de la de lectura.

**Arquitectura:** un componente aislado (`OperatorDirectory`) autentica una clave y devuelve el nombre; una dependencia de FastAPI (`require_operator`) lo usa, limita los intentos fallidos por origen y los deja en el registro de auditoría; los endpoints de acción del desk pasan a exigirla y ya no reciben el nombre en el cuerpo.

**Stack:** Python 3.12, FastAPI, pytest. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-29-identidad-operador-design.md`

## Restricciones globales (copiadas del spec)

- Variable `OPERATOR_KEYS`: lista `nombre=clave` separada por comas.
- Nombre de operador: `[a-z0-9_.-]{1,40}`. Clave: mínimo 24 caracteres.
- Un nombre repetido o una clave repetida hace que **el arranque falle**; el mensaje nombra el problema **sin imprimir claves**.
- `OPERATOR_KEYS` vacía o ausente: endpoints de operador **503** (falla cerrado).
- Cabecera de la credencial: `X-Operator-Key`. La clave de admin (`X-Admin-Key`) **solo lee**; la de operador es la única que puede tomar, aprobar, rechazar y devolver, y **no** lee. No se hereda en ningún sentido.
- `DeskAction.operator` **desaparece** del cuerpo: el nombre lo pone el servidor.
- Respuestas: clave ausente o inválida **401** con mensaje genérico; límite superado **429**.
- Límite de fallos: `OPERATOR_AUTH_FAILS_PER_MIN`, defecto 10, por origen (`client_ip`). Solo cuentan los **fallos**; superado el límite, incluso la clave correcta recibe 429.
- Cada intento fallido o bloqueado escribe un evento `operator_auth_failed` en el registro de auditoría, **sin la clave presentada ni su prefijo**.
- Comparar contra **todas** las claves con `hmac.compare_digest`, sin cortar al primer acierto. En memoria solo se guarda el hash SHA-256 de cada clave.
- Textos nuevos (commits, comentarios, docs) en **español**. Sin la línea `Co-Authored-By` en ningún commit.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `agent/session/operators.py` (crear) | `OperatorDirectory`: parsea y valida `OPERATOR_KEYS`, autentica una clave. No depende de FastAPI ni del desk. |
| `agent/tools/audit.py` (modificar) | `AuditLog.event(...)`: un registro que no es una llamada a herramienta. |
| `api/main.py` (modificar) | `RateLimiter.over/record`, `require_operator`, endpoints de acción migrados, validación al arrancar. |
| `tests/test_operators.py` (crear) | Pruebas del componente aislado. |
| `tests/test_operator_auth.py` (crear) | Pruebas del evento de auditoría, del limitador y de los endpoints. |
| `tests/test_desk.py` (modificar) | El test de endpoints pasa al esquema nuevo. |
| `.env.example`, `render.yaml`, `LIMITATIONS.md` (modificar) | Configuración y límites documentados. |

**Rama de trabajo:** crear `feat/operator-identity` desde `docs/specs-cumplimiento` (`git checkout -b feat/operator-identity`), que ya contiene el desk del operador y el spec.

---

### Tarea 1: `OperatorDirectory`

**Archivos:**
- Crear: `agent/session/operators.py`
- Prueba: `tests/test_operators.py`

**Interfaces:**
- Produce: `OperatorConfigError(ValueError)`; `MIN_KEY_LENGTH = 24`; `NAME_RE`; `OperatorDirectory.parse(raw: str) -> OperatorDirectory`; `OperatorDirectory.from_env() -> OperatorDirectory`; `OperatorDirectory.enabled: bool` (propiedad); `OperatorDirectory.authenticate(presented: str | None) -> str | None`.

- [ ] **Paso 1: escribir las pruebas que fallan**

Crear `tests/test_operators.py`:

```python
"""El directorio de operadores: una clave da un nombre, y una configuración mala impide arrancar sin filtrar claves."""
from __future__ import annotations

import pytest

from agent.session.operators import OperatorConfigError, OperatorDirectory

ANA = "ana-key-0123456789-abcdefgh"
BETO = "beto-key-0123456789-abcdefg"


def directory():
    return OperatorDirectory.parse(f"ana={ANA},beto={BETO}")


def test_a_valid_key_gives_its_name_and_anything_else_gives_nothing():
    d = directory()
    assert d.authenticate(ANA) == "ana" and d.authenticate(BETO) == "beto"
    for bad in (None, "", "nope", ANA + "x", ANA[:-1], ANA.upper()):
        assert d.authenticate(bad) is None


def test_an_empty_config_is_a_disabled_directory_that_authenticates_nobody():
    for raw in ("", "   ", " , "):
        d = OperatorDirectory.parse(raw)
        assert not d.enabled and d.authenticate(ANA) is None
    assert directory().enabled


def test_a_key_may_contain_an_equals_sign():
    key = "base64-looking-key-0123456789=="
    assert OperatorDirectory.parse(f"ana={key}").authenticate(key) == "ana"


@pytest.mark.parametrize("raw", [
    f"ana={ANA},ana={BETO}",       # the same name twice
    f"ana={ANA},beto={ANA}",       # two people, one key
    "ana=short",                   # key under 24 characters
    f"Ana={ANA}",                  # name outside [a-z0-9_.-]
    f"{'a' * 41}={ANA}",           # name over 40 characters
    f"={ANA}",                     # no name
    f"ana{ANA}",                   # no name=key form
])
def test_a_bad_config_stops_the_start_and_never_prints_a_key(raw):
    with pytest.raises(OperatorConfigError) as err:
        OperatorDirectory.parse(raw)
    assert ANA not in str(err.value) and BETO not in str(err.value) and "short" not in str(err.value)


def test_from_env_reads_operator_keys(monkeypatch):
    monkeypatch.setenv("OPERATOR_KEYS", f"ana={ANA}")
    assert OperatorDirectory.from_env().authenticate(ANA) == "ana"
    monkeypatch.delenv("OPERATOR_KEYS")
    assert not OperatorDirectory.from_env().enabled
```

- [ ] **Paso 2: correrlas y ver que fallan**

Ejecutar: `python -m pytest tests/test_operators.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'agent.session.operators'`.

- [ ] **Paso 3: implementar**

Crear `agent/session/operators.py`:

```python
"""Identidad por operador: cada acción sobre un caso queda atribuida a una persona, no a una clave compartida.

`OPERATOR_KEYS` es una lista `nombre=clave` separada por comas. El nombre de quien actúa sale de la clave que presentó,
nunca de un campo que él mismo envíe. Un nombre o una clave repetidos, una clave corta o un nombre mal formado hacen
que la configuración se rechace (el servicio no arranca): dos personas con la misma clave romperían la atribución.
Vacía, el directorio queda deshabilitado y los endpoints de operador fallan cerrados.

Solo se guarda el hash de cada clave, y los mensajes de error nombran el problema sin imprimir ninguna clave.
Límites: sin MFA, claves en el entorno y rotación manual; en producción esto es SSO corporativo (OIDC).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

MIN_KEY_LENGTH = 24
NAME_RE = re.compile(r"[a-z0-9_.-]{1,40}")


class OperatorConfigError(ValueError):
    pass


def _digest(key: str) -> bytes:
    return hashlib.sha256(key.encode()).digest()


class OperatorDirectory:
    def __init__(self, hashes: dict[str, bytes]):
        self._hashes = hashes

    @classmethod
    def parse(cls, raw: str) -> "OperatorDirectory":
        hashes: dict[str, bytes] = {}
        for position, entry in enumerate((e.strip() for e in raw.split(",")), start=1):
            if not entry:
                continue
            name, sep, key = entry.partition("=")
            if not sep:
                raise OperatorConfigError(f"OPERATOR_KEYS: la entrada {position} no tiene la forma nombre=clave")
            if not NAME_RE.fullmatch(name):
                raise OperatorConfigError(f"OPERATOR_KEYS: nombre inválido {name!r} (permitido: [a-z0-9_.-], 1 a 40 caracteres)")
            if len(key) < MIN_KEY_LENGTH:
                raise OperatorConfigError(f"OPERATOR_KEYS: la clave de {name!r} tiene menos de {MIN_KEY_LENGTH} caracteres")
            if name in hashes:
                raise OperatorConfigError(f"OPERATOR_KEYS: el nombre {name!r} está repetido")
            clash = next((other for other, h in hashes.items() if h == _digest(key)), None)
            if clash:
                raise OperatorConfigError(f"OPERATOR_KEYS: {clash!r} y {name!r} comparten la misma clave")
            hashes[name] = _digest(key)
        return cls(hashes)

    @classmethod
    def from_env(cls) -> "OperatorDirectory":
        return cls.parse(os.environ.get("OPERATOR_KEYS", ""))

    @property
    def enabled(self) -> bool:
        return bool(self._hashes)

    def authenticate(self, presented: str | None) -> str | None:
        """The operator this key belongs to, or None. Every key is compared, with no early exit, so the time taken
        does not say how many were tried or which one matched."""
        if not presented:
            return None
        digest, found = _digest(presented), None
        for name, known in self._hashes.items():
            if hmac.compare_digest(digest, known):
                found = name
        return found
```

- [ ] **Paso 4: correrlas y ver que pasan**

Ejecutar: `python -m pytest tests/test_operators.py -q`
Esperado: `11 passed` (1 + 1 + 1 + 7 parametrizados + 1).

- [ ] **Paso 5: commit**

```bash
git add agent/session/operators.py tests/test_operators.py
git commit -m "Agregar el directorio de operadores que autentica una clave y devuelve su nombre"
```

---

### Tarea 2: eventos de auditoría y limitador de fallos

**Archivos:**
- Modificar: `agent/tools/audit.py` (clase `AuditLog`, junto a `finish`)
- Modificar: `api/main.py` (clase `RateLimiter`, líneas ~49-66)
- Prueba: `tests/test_operator_auth.py` (se crea aquí y se amplía en la Tarea 3)

**Interfaces:**
- Produce: `AuditLog.event(kind: str, **fields) -> None`; `RateLimiter.over(key: str) -> bool`; `RateLimiter.record(key: str) -> None`. `over` es de solo lectura (poda y compara con el límite), `record` suma un golpe.

- [ ] **Paso 1: escribir las pruebas que fallan**

Crear `tests/test_operator_auth.py`:

```python
"""Autenticación del operador: eventos de auditoría, limitador de fallos y endpoints de acción del desk."""
from __future__ import annotations

import json

from agent.tools.audit import AuditLog
from api import main


def test_an_audit_event_carries_a_timestamp_so_retention_can_prune_it(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    AuditLog().event("operator_auth_failed", origin="1.2.3.4", reason="invalid")
    row = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["event"] == "operator_auth_failed" and row["origin"] == "1.2.3.4" and isinstance(row["started_at"], float)


def test_the_failure_limiter_counts_only_recorded_failures_and_per_origin():
    limiter = main.RateLimiter(2, 60)
    assert not limiter.over("a")          # looking never counts
    assert not limiter.over("a")
    limiter.record("a")
    assert not limiter.over("a")
    limiter.record("a")
    assert limiter.over("a") and not limiter.over("b")
```

- [ ] **Paso 2: correrlas y ver que fallan**

Ejecutar: `python -m pytest tests/test_operator_auth.py -q`
Esperado: FALLA con `AttributeError: 'AuditLog' object has no attribute 'event'`.

- [ ] **Paso 3: implementar**

En `agent/tools/audit.py`, dentro de `AuditLog`, después del método `finish`, agregar:

```python
    def event(self, kind: str, **fields: Any) -> None:
        """A record that is not a tool call (a failed operator login). `started_at` lets ops/retention.py prune it."""
        self._sink.write({"event": kind, "started_at": time.time(), **fields})
```

En `api/main.py`, dentro de `RateLimiter`, después del método `allow` (termina en `return True`), agregar:

```python
    def over(self, key: str) -> bool:
        """Whether this key has used up its hits in the window. Looking does not count as a hit."""
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            return len(q) >= self.limit

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.time())
```

- [ ] **Paso 4: correrlas y ver que pasan**

Ejecutar: `python -m pytest tests/test_operator_auth.py tests/test_api.py -q`
Esperado: todo pasa (`test_api.py` confirma que `allow` no cambió).

- [ ] **Paso 5: commit**

```bash
git add agent/tools/audit.py api/main.py tests/test_operator_auth.py
git commit -m "Agregar eventos al registro de auditoría y un limitador que cuenta solo los fallos"
```

---

### Tarea 3: `require_operator` y los endpoints de acción

**Archivos:**
- Modificar: `api/main.py` (import, `require_operator` junto a `require_admin`, `DeskAction`, `ticket_action`, validación al arrancar)
- Modificar: `tests/test_desk.py` (el test de endpoints)
- Prueba: `tests/test_operator_auth.py` (ampliar)

**Interfaces:**
- Consume: `OperatorDirectory.from_env()`, `.enabled`, `.authenticate(...)` (Tarea 1); `AuditLog.event(...)`, `RateLimiter.over/record` (Tarea 2); `client_ip(request)` y `RateLimiter` ya existentes en `api/main.py`.
- Produce: `operator_fail_limiter: RateLimiter`; `require_operator(request, x_operator_key) -> str` (el nombre autenticado).

- [ ] **Paso 1: escribir las pruebas que fallan**

Agregar al final de `tests/test_operator_auth.py` (y los imports que falten arriba: `import pytest`, `from fastapi.testclient import TestClient`, `from agent.policy import router`, `from agent.policy.desk import default_desk`, `from agent.policy.escalation import escalate`):

```python
ANA_KEY = "ana-key-0123456789-abcdefgh"
BETO_KEY = "beto-key-0123456789-abcdefg"
ADMIN_KEY = "admin-key-0123456789-abcdefgh"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for var, name in (("HUMAN_QUEUE_PATH", "queue"), ("HUMAN_DESK_PATH", "desk"), ("TRACE_REQUESTS_PATH", "traces"),
                      ("AUDIT_LOG_PATH", "audit")):
        monkeypatch.setenv(var, str(tmp_path / f"{name}.jsonl"))
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("OPERATOR_KEYS", f"ana={ANA_KEY},beto={BETO_KEY}")
    monkeypatch.setattr(main, "operator_fail_limiter", main.RateLimiter(3, 60))
    return tmp_path


def ticket() -> str:
    """A ticket that carries an action (tracing the fixture's one pending transfer)."""
    action = {"tool": "request_trace", "transaction_id": "TXN-FIX0006", "product_id": "PRD-FIX0010",
              "review_reason": "older_than_review_threshold", "age_days": 100,
              "movement": {"transaction_type": "Transfer", "amount": 40, "currency": "USD"}}
    return escalate(router.trace_review("older_than_review_threshold"), "CLI-FIX0004", "ref", "no llegó", "es",
                    [], [], [], {}, None, action).ticket_id


def as_operator(key):
    return {"X-Operator-Key": key}


def test_the_name_in_the_desk_event_is_the_one_of_the_key_never_one_sent_in_the_body():
    tid, client = ticket(), TestClient(main.app)
    r = client.post(f"/admin/tickets/{tid}/claim", json={"operator": "beto"}, headers=as_operator(ANA_KEY))
    assert r.status_code == 200 and r.json()["operator"] == "ana"
    assert default_desk.state(tid)["history"][0]["operator"] == "ana"


def test_the_admin_key_cannot_act_and_the_operator_key_cannot_read():
    tid, client = ticket(), TestClient(main.app)
    assert client.post(f"/admin/tickets/{tid}/claim", json={}, headers={"X-Admin-Key": ADMIN_KEY}).status_code == 401
    assert client.get(f"/admin/tickets/{tid}", headers=as_operator(ANA_KEY)).status_code == 401
    assert client.get(f"/admin/tickets/{tid}", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 200


def test_without_operator_keys_the_action_endpoints_are_off(monkeypatch):
    monkeypatch.delenv("OPERATOR_KEYS")
    tid = ticket()
    assert TestClient(main.app).post(f"/admin/tickets/{tid}/claim", json={}, headers=as_operator(ANA_KEY)).status_code == 503


def test_after_too_many_failures_from_one_origin_even_the_right_key_gets_429_and_others_are_unaffected(monkeypatch):
    monkeypatch.setenv("CLIENT_IP_HEADER", "X-Test-Ip")
    tid, client = ticket(), TestClient(main.app)
    url, here = f"/admin/tickets/{tid}/claim", {"X-Test-Ip": "1.1.1.1"}
    for _ in range(3):
        assert client.post(url, json={}, headers={**here, **as_operator("wrong")}).status_code == 401
    assert client.post(url, json={}, headers={**here, **as_operator(ANA_KEY)}).status_code == 429
    elsewhere = {"X-Test-Ip": "2.2.2.2", **as_operator(ANA_KEY)}
    assert client.post(url, json={}, headers=elsewhere).status_code == 200


def test_a_failed_attempt_is_audited_without_the_key_that_was_presented(env):
    tid, client = ticket(), TestClient(main.app)
    client.post(f"/admin/tickets/{tid}/claim", json={}, headers=as_operator("SECRET-PRESENTED-KEY-0123456789"))
    text = (env / "audit.jsonl").read_text(encoding="utf-8")
    assert "operator_auth_failed" in text and "SECRET" not in text


def test_two_operators_cannot_act_on_each_others_ticket_end_to_end():
    tid, client = ticket(), TestClient(main.app)
    assert client.post(f"/admin/tickets/{tid}/claim", json={}, headers=as_operator(ANA_KEY)).status_code == 200
    assert client.post(f"/admin/tickets/{tid}/approve", json={}, headers=as_operator(BETO_KEY)).status_code == 409
    assert client.post(f"/admin/tickets/{tid}/approve", json={}, headers=as_operator(ANA_KEY)).json()["status"] == "approved"
```

Y **reemplazar** en `tests/test_desk.py` el test `test_the_operator_endpoints_need_the_admin_key_and_map_conflicts_to_409` completo por:

```python
def test_the_operator_endpoints_need_the_operator_key_and_map_conflicts_to_409(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "admin-key-0123456789-abcdefgh")
    monkeypatch.setenv("OPERATOR_KEYS", "ana=ana-key-0123456789-abcdefgh")
    client = TestClient(main.app)
    admin, ana = {"X-Admin-Key": "admin-key-0123456789-abcdefgh"}, {"X-Operator-Key": "ana-key-0123456789-abcdefgh"}
    ticket_id = file_ticket()
    body = {}
    assert client.post(f"/admin/tickets/{ticket_id}/claim", json=body).status_code == 401
    assert client.post(f"/admin/tickets/{ticket_id}/approve", json=body, headers=ana).status_code == 409  # not claimed
    assert client.post(f"/admin/tickets/{ticket_id}/claim", json=body, headers=ana).json()["status"] == "claimed"
    assert client.get(f"/admin/tickets/{ticket_id}", headers=admin).json()["desk"]["operator"] == "ana"
    assert client.post(f"/admin/tickets/{ticket_id}/approve", json=body, headers=ana).json()["status"] == "approved"
    assert client.post(f"/admin/tickets/{ticket_id}/approve", json=body, headers=ana).status_code == 200  # idempotent
    assert client.post("/admin/tickets/none/claim", json=body, headers=ana).status_code == 404
    listed = client.get("/admin/human_queue", headers=admin).json()
    assert listed[-1]["desk"]["status"] == "approved"
```

- [ ] **Paso 2: correrlas y ver que fallan**

Ejecutar: `python -m pytest tests/test_operator_auth.py tests/test_desk.py -q`
Esperado: FALLAN los tests nuevos (los endpoints todavía usan `require_admin` y esperan `operator` en el cuerpo).

- [ ] **Paso 3: implementar**

En `api/main.py`:

1. Agregar el import junto a los otros de `agent.session`:

```python
from agent.session.operators import OperatorDirectory
```

2. Justo después de `require_admin`, agregar:

```python
OperatorDirectory.from_env()  # a bad OPERATOR_KEYS stops the service from starting, rather than failing at the first request

operator_fail_limiter = RateLimiter(int(os.environ.get("OPERATOR_AUTH_FAILS_PER_MIN", "10")), 60)


def require_operator(request: Request, x_operator_key: str | None = Header(default=None)) -> str:
    """The authenticated operator's name, from the key they present: never from anything they send. Only failures
    count against the limit; once over it, even the right key is refused until the window passes."""
    directory = OperatorDirectory.from_env()
    if not directory.enabled:
        raise HTTPException(503, "operator endpoints disabled: OPERATOR_KEYS not configured")
    origin = client_ip(request)
    if operator_fail_limiter.over(origin):
        default_audit_log.event("operator_auth_failed", origin=origin, reason="blocked")
        raise HTTPException(429, "too many failed attempts")
    name = directory.authenticate(x_operator_key)
    if name is None:
        operator_fail_limiter.record(origin)
        default_audit_log.event("operator_auth_failed", origin=origin, reason="invalid")
        raise HTTPException(401, "invalid operator key")
    return name
```

3. Reemplazar `DeskAction` y `ticket_action`:

```python
class DeskAction(BaseModel):
    expected_version: int | None = None  # the version the operator saw; a newer one refuses the decision
    reason: str | None = Field(default=None, max_length=300)
```

```python
@app.post("/admin/tickets/{ticket_id}/{action}")
def ticket_action(ticket_id: str, action: Literal["claim", "approve", "reject", "release"], body: DeskAction,
                  operator: str = Depends(require_operator)) -> dict:
    """An operator takes a ticket, approves or rejects the action it carries, or hands the conversation back.
    Who acted is the name of the key they presented; the body cannot say otherwise."""
    try:
        return default_desk.act(ticket_id, action, operator, body.expected_version, body.reason)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except DeskError as exc:
        raise HTTPException(400, str(exc)) from None
```

(Se quita `dependencies=[Depends(require_admin)]` del decorador: la autenticación va en `require_operator`.)

- [ ] **Paso 4: correrlas y ver que pasan**

Ejecutar: `python -m pytest tests/test_operator_auth.py tests/test_desk.py tests/test_operators.py tests/test_api.py -q`
Esperado: todo pasa.

- [ ] **Paso 5: commit**

```bash
git add api/main.py tests/test_operator_auth.py tests/test_desk.py
git commit -m "Exigir la clave del operador para actuar sobre un ticket y tomar el nombre de la clave"
```

---

### Tarea 4: configuración, límites documentados y verificación final

**Archivos:**
- Modificar: `.env.example`, `render.yaml`, `LIMITATIONS.md`

- [ ] **Paso 1: `.env.example`**

Reemplazar la línea de admin:

```
# --- Admin endpoints (disabled if empty) ---
ADMIN_API_KEY=
```

por:

```
# --- Admin endpoints (disabled if empty) ---
# ADMIN_API_KEY solo LEE (cola, trazas, drift...). Actuar sobre un ticket exige la clave de un operador.
ADMIN_API_KEY=
# Operadores: lista nombre=clave separada por comas (clave de al menos 24 caracteres, nombre [a-z0-9_.-]).
# El nombre en el registro sale de la clave. Vacía = los endpoints de acción quedan deshabilitados (503).
# Repetidos o claves cortas: el servicio no arranca. Generar una: python -c "import secrets;print(secrets.token_urlsafe(32))"
OPERATOR_KEYS=
OPERATOR_AUTH_FAILS_PER_MIN=10
```

- [ ] **Paso 2: `render.yaml`**

Junto a `ADMIN_API_KEY` agregar:

```yaml
      - key: OPERATOR_KEYS
        sync: false           # nombre=clave,nombre=clave (se pide al crear el Blueprint)
```

- [ ] **Paso 3: `LIMITATIONS.md`**

Agregar, en la sección de identidad (junto a la nota del IdP de prueba), este punto:

```markdown
- **Identidad de operadores.** Los operadores se autentican con claves con nombre (`OPERATOR_KEYS`); el
  nombre en el registro sale de la clave, no de lo que envíe el operador, y leer (clave de admin) está
  separado de actuar (clave de operador). Sigue sin haber MFA, las claves viven en variables de entorno
  y se rotan a mano, y el límite de intentos fallidos está en memoria y se reinicia con el proceso. El
  camino a producción es SSO corporativo (OIDC) con los roles del banco.
```

- [ ] **Paso 4: suite completa**

Ejecutar: `python -m pytest tests -q`
Esperado: todo pasa (más de 389 pruebas, ninguna fallando).

- [ ] **Paso 5: commit, push y PR**

```bash
git add .env.example render.yaml LIMITATIONS.md
git commit -m "Documentar la configuración y los límites de la identidad por operador"
git push -u origin feat/operator-identity
git push -u origin docs/specs-cumplimiento
gh pr create --base docs/specs-cumplimiento --title "Identidad por operador en lugar de la clave compartida" --body "$(cat <<'EOF'
## Qué
Cada acción sobre un ticket (tomar, aprobar, rechazar, devolver) queda atribuida a la persona dueña de la clave, y actuar exige una credencial distinta de la de leer.

- `OPERATOR_KEYS` (`nombre=clave`) y la cabecera `X-Operator-Key`. El nombre en `ticket_events.jsonl` sale de la clave; el campo `operator` desaparece del cuerpo.
- La clave de admin solo lee; la de operador solo actúa. Ninguna hereda a la otra.
- Configuración inválida (nombres o claves repetidos, claves de menos de 24 caracteres): el servicio no arranca, sin imprimir claves. Sin `OPERATOR_KEYS`, los endpoints de acción responden 503.
- Los intentos fallidos o bloqueados quedan en el registro de auditoría sin la clave presentada, y superado el límite por origen (`OPERATOR_AUTH_FAILS_PER_MIN`) incluso la clave correcta recibe 429.

## Verificación
Suite completa en verde, más los criterios de aceptación del spec (`docs/superpowers/specs/2026-09-29-identidad-operador-design.md`), cada uno como test.

## Límites
Sin MFA, claves en variables de entorno con rotación manual, y limitador en memoria que se reinicia con el proceso. El camino a producción es SSO corporativo (OIDC).
EOF
)"
```
