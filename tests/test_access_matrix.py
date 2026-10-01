"""Access control: every route, called as every role, answers as api/access.py says it should.

The table (api/access.py POLICY) is the source of truth. Three things keep it honest:
- the service refuses to start when a route has no row (access.check_app), and a test proves it does;
- every row is called as anonymous, customer, operator and admin, each with only its own credential, and the answer at the door
  (refused or let through) is compared with the row;
- the admin key, the operator key and a session token are not interchangeable.
"""
from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from agent.policy import router as policy_router
from agent.policy.escalation import escalate
from agent.session import identity
from agent.session.identity import derive_test_pin
from api import access, main
from api.access import POLICY, Role

ADMIN_KEY = "admin-key-0123456789-abcdefgh"
OPERATOR_KEY = "ana-key-0123456789-abcdefgh"
METRICS_TOKEN = "metrics-token-0123456789-abcdefgh"
CUSTOMER = "CLI-FIX0001"
ROLES = list(Role)
DEAD_TOKEN = "0" * 24  # well formed, and nobody's

ROWS = [(key, row) for key, row in sorted(POLICY.items()) if not row.optional]


@pytest.fixture
def world(tmp_path, monkeypatch):
    for var, name in (("HUMAN_QUEUE_PATH", "queue"), ("HUMAN_DESK_PATH", "desk"), ("TRACE_REQUESTS_PATH", "traces"),
                      ("AUDIT_LOG_PATH", "audit"), ("TRACE_LOG_PATH", "trace_log"), ("SHADOW_LOG_PATH", "shadow")):
        monkeypatch.setenv(var, str(tmp_path / f"{name}.jsonl"))
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("OPERATOR_KEYS", f"ana={OPERATOR_KEY}")
    monkeypatch.setenv("DEMO_PUBLIC_CUSTOMERS", CUSTOMER)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    identity.default_identity._failures.clear()
    for limiter in ("login_limiter", "chat_limiter", "operator_fail_limiter"):
        monkeypatch.setattr(main, limiter, main.RateLimiter(1000, 60))
    client = TestClient(main.app)
    token = client.post("/auth/session", json={"customer_id": CUSTOMER, "pin": derive_test_pin(CUSTOMER)}).json()["token"]
    ticket = escalate(policy_router.foreign_reference(["PRD-FIX0006"]), CUSTOMER, "ref", "hola", "es", [], [], [], {}, None).ticket_id
    return client, token, ticket


def call(world, role: Role, method: str, template: str):
    """The route called with the credential of `role` and nothing else. Returns the response."""
    client, token, ticket = world
    path = (template.replace("{ticket_id}", ticket).replace("{action}", "claim").replace("{trace_id}", "a" * 32)
            .replace("{customer_id}", CUSTOMER))
    session = token if role is Role.CUSTOMER else DEAD_TOKEN
    headers = {Role.CUSTOMER: {"X-Session-Token": token}, Role.OPERATOR: {"X-Operator-Key": OPERATOR_KEY},
               Role.ADMIN: {"X-Admin-Key": ADMIN_KEY}, Role.ANONYMOUS: {}}[role]
    body = {
        "/auth/session": {"customer_id": CUSTOMER, "pin": derive_test_pin(CUSTOMER)},
        "/chat": {"session_token": session, "message": "hola"},
        "/demo/fault": {"session_token": session, "fault": "llm_restore"},
        "/demo/tickets": {"session_token": session},
        "/demo/traces": {"session_token": session},
        "/admin/tickets/{ticket_id}/{action}": {},
    }.get(template)
    if method == "GET" and template == "/auth/session" and role is not Role.CUSTOMER:
        headers = {**headers, "X-Session-Token": DEAD_TOKEN}
    return client.request(method, path, headers=headers, json=body)


def refused(template: str, response) -> bool:
    """Whether the door stayed shut. A dead session on /chat is not an HTTP error: the customer is asked to sign in again."""
    if response.status_code in (401, 403, 429, 503):
        return True
    return template == "/chat" and response.json().get("disposition") == "REAUTH_REQUIRED"


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("key,row", ROWS, ids=[f"{m} {p}" for (m, p), _ in ROWS])
def test_each_route_lets_in_exactly_the_roles_the_matrix_says(world, monkeypatch, key, row, role):
    method, template = key
    if row.demo_only:
        monkeypatch.setenv("DEMO_MODE", "1")
    response = call(world, role, method, template)
    assert refused(template, response) == (role not in row.roles), (
        f"{method} {template} as {role.value}: HTTP {response.status_code} {response.text[:120]}; matrix allows {sorted(r.value for r in row.roles)}")


DEMO_ROWS = [(k, r) for k, r in ROWS if r.demo_only]


@pytest.mark.parametrize("key,row", DEMO_ROWS, ids=[f"{m} {p}" for (m, p), _ in DEMO_ROWS])
def test_demo_surfaces_do_not_exist_without_demo_mode(world, key, row):
    method, template = key
    for role in ROLES:  # not even the right credential finds them
        response = call(world, role, method, template)
        assert response.status_code == 404 and response.json() == {"detail": "Not Found"}, f"{method} {template} as {role.value}"


def test_every_route_of_the_app_has_a_row_and_every_row_a_route():
    assert access.problems(main.app) == []


def test_a_route_without_a_row_stops_the_service_from_starting():
    scratch = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @scratch.get("/new-endpoint")
    def new_endpoint():  # pragma: no cover
        return {}

    with pytest.raises(RuntimeError, match=r"GET /new-endpoint: no access policy"):
        access.check_app(scratch, {})


def test_a_row_declared_admin_but_not_guarded_is_caught():
    scratch = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @scratch.get("/secret")
    def secret():  # pragma: no cover
        return {}

    row = {("GET", "/secret"): access.Policy(access.ADMIN, "admin")}
    assert any("does not depend on require_admin" in p for p in access.problems(scratch, row))
    guarded = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    guarded.get("/secret", dependencies=[Depends(main.require_admin)])(lambda: {})
    assert access.problems(guarded, row) == []


def test_a_row_for_a_route_that_is_gone_is_caught():
    assert any("does not exist" in p for p in access.problems(FastAPI(docs_url=None, redoc_url=None, openapi_url=None), {("GET", "/old"): access.Policy(access.ANYONE)}))


def test_the_matrix_separates_reading_from_acting(world):
    """Admin reads, operator acts, and neither key opens the other's door."""
    client, _, ticket = world
    assert client.get(f"/admin/tickets/{ticket}", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 200
    assert client.get(f"/admin/tickets/{ticket}", headers={"X-Operator-Key": OPERATOR_KEY}).status_code == 401
    assert client.post(f"/admin/tickets/{ticket}/claim", headers={"X-Admin-Key": ADMIN_KEY}, json={}).status_code == 401
    assert client.post(f"/admin/tickets/{ticket}/claim", headers={"X-Operator-Key": OPERATOR_KEY}, json={}).status_code == 200


def test_a_session_token_is_not_an_admin_or_operator_credential(world):
    client, token, ticket = world
    assert client.get("/admin/ops", headers={"X-Admin-Key": token}).status_code == 401
    assert client.get("/admin/ops", headers={"X-Session-Token": token}).status_code == 401
    assert client.post(f"/admin/tickets/{ticket}/claim", headers={"X-Operator-Key": token}, json={}).status_code == 401


def test_metrics_open_to_the_admin_key_or_the_scrapers_token_and_the_token_opens_nothing_else(world, monkeypatch):
    client, _, _ = world
    monkeypatch.setenv("METRICS_TOKEN", METRICS_TOKEN)
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": f"Bearer {METRICS_TOKEN}"}).status_code == 200
    assert client.get("/metrics", headers={"Authorization": f"Bearer {ADMIN_KEY}"}).status_code == 200
    assert client.get("/metrics", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 200
    assert client.get("/metrics", headers={"Authorization": f"Basic {METRICS_TOKEN}"}).status_code == 401
    assert client.get("/admin/ops", headers={"Authorization": f"Bearer {METRICS_TOKEN}"}).status_code == 401
    assert client.get("/admin/ops", headers={"X-Admin-Key": METRICS_TOKEN}).status_code == 401


def test_admin_and_metrics_fail_closed_when_no_key_is_configured(world, monkeypatch):
    client, _, _ = world
    monkeypatch.delenv("ADMIN_API_KEY")
    assert client.get("/admin/ops", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 503
    assert client.get("/metrics", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 503


def test_guessing_an_admin_key_is_limited_and_audited(world, monkeypatch):
    client, _, _ = world
    monkeypatch.setattr(main, "operator_fail_limiter", main.RateLimiter(3, 60))
    codes = [client.get("/admin/ops", headers={"X-Admin-Key": f"guess-{i}"}).status_code for i in range(3)]
    assert codes == [401, 401, 401]
    assert client.get("/admin/ops", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 429  # even the right key, until the window passes
    audit = [line for line in (main.default_audit_log.path).read_text(encoding="utf-8").splitlines() if "admin_auth_failed" in line]
    assert len(audit) == 4 and '"reason": "blocked"' in audit[-1] and "guess-" not in "".join(audit)


def test_a_key_with_non_ascii_characters_is_refused_not_a_server_error(world):
    client, _, _ = world
    for key in ("clavé-ñ".encode("latin-1"), "Ω".encode("utf-8")):
        assert client.get("/admin/ops", headers={"X-Admin-Key": key}).status_code == 401
    # a PIN of non-ASCII digits is refused by the schema (the pattern is [0-9]{6}, not a Unicode-aware \d), never a server error
    r = client.post("/auth/session", json={"customer_id": CUSTOMER, "pin": "١٢٣٤٥٦"})
    assert r.status_code == 422


def test_secrets_are_compared_with_a_constant_time_function(world, monkeypatch):
    """The comparison of the admin key and of the PIN goes through hmac.compare_digest, not ==."""
    import hmac

    client, _, _ = world
    seen = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: seen.append((type(a), type(b))) or real(a, b))
    client.get("/admin/ops", headers={"X-Admin-Key": "x" * 10})
    client.post("/auth/session", json={"customer_id": CUSTOMER, "pin": "000000"})
    assert len(seen) >= 2 and all(a is bytes and b is bytes for a, b in seen)


def test_the_matrix_in_the_docs_is_the_one_the_service_enforces():
    from pathlib import Path

    docs = (Path(__file__).resolve().parent.parent / "docs" / "operations.md").read_text(encoding="utf-8")
    assert access.matrix_markdown() in docs, "docs/operations.md, \"Access control\": paste the output of `python -m api.access`"
