"""HTTP-level tests: auth factor, admin fail-closed, limits, no token leakage."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent.session import identity
from agent.session.identity import derive_test_pin
from api import main


@pytest.fixture
def client(monkeypatch):
    identity.default_identity._failures.clear()
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(10, 60))
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(20, 60))
    return TestClient(main.app)


def test_login_rate_limit_per_client(client, monkeypatch):
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(2, 60))
    codes = [login(client, cid="CLI-FIX0004").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def login(client, cid="CLI-FIX0001", pin=None):
    return client.post("/auth/session", json={"customer_id": cid, "pin": pin or derive_test_pin(cid)})


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["data_as_of"] == "2024-01-16"


def test_customer_id_alone_is_not_enough(client):
    assert client.post("/auth/session", json={"customer_id": "CLI-FIX0001"}).status_code == 422
    assert login(client, pin="000000" if derive_test_pin("CLI-FIX0001") != "000000" else "111111").status_code == 401
    ok = login(client)
    assert ok.status_code == 200 and "token" in ok.json()


def test_unknown_customer_gets_the_same_generic_error(client):
    r = login(client, cid="CLI-NOPE", pin=derive_test_pin("CLI-NOPE"))
    assert r.status_code == 401 and r.json()["detail"] == "invalid credentials"


def test_lockout_after_repeated_failures(client):
    wrong = "000000" if derive_test_pin("CLI-FIX0003") != "000000" else "111111"
    codes = [login(client, cid="CLI-FIX0003", pin=wrong).status_code for _ in range(5)]
    assert codes == [401] * 5
    assert login(client, cid="CLI-FIX0003").status_code == 429  # even the right PIN is refused while locked


def test_identity_fails_closed_without_secret(client, monkeypatch):
    monkeypatch.delenv("DEMO_IDP_SECRET")
    assert login(client, pin="123456").status_code == 503


def test_chat_limits_and_reauth(client, monkeypatch):
    assert client.post("/chat", json={"session_token": "x" * 20, "message": "a" * 1001}).status_code == 422
    r = client.post("/chat", json={"session_token": "not-a-real-token", "message": "¿Cuál es mi saldo?"})
    assert r.json()["disposition"] == "REAUTH_REQUIRED"
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(2, 60))
    codes = [client.post("/chat", json={"session_token": "rate-limit-tok", "message": "hola"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_admin_fails_closed_and_requires_key(client, monkeypatch):
    assert client.get("/admin/human_queue").status_code == 401
    assert client.get("/admin/human_queue", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert client.get("/admin/human_queue", headers={"X-Admin-Key": "test-admin-key"}).status_code == 200
    monkeypatch.delenv("ADMIN_API_KEY")
    assert client.get("/admin/human_queue", headers={"X-Admin-Key": "test-admin-key"}).status_code == 503


def test_escalation_ticket_and_trace_never_expose_the_token(client):
    token = login(client).json()["token"]
    r = client.post("/chat", json={"session_token": token, "message": "Me clonaron la tarjeta"}).json()
    assert r["disposition"] == "ESCALATE" and r["ticket_id"]
    headers = {"X-Admin-Key": "test-admin-key"}
    tickets = client.get("/admin/human_queue", headers=headers).text
    trace = client.get(f"/admin/traces/{r['trace_id']}", headers=headers)
    assert token not in tickets and token not in trace.text
    assert trace.status_code == 200 and trace.json()["policy_rule"] == "lexicon:theft"
    assert any(a["tool_name"] == "recent_activity_for_review" for a in trace.json()["tool_audit"])


def test_the_8_character_code_a_customer_quotes_finds_the_trace(client):
    token = login(client).json()["token"]
    r = client.post("/chat", json={"session_token": token, "message": "Me clonaron la tarjeta"}).json()
    headers = {"X-Admin-Key": "test-admin-key"}
    found = client.get(f"/admin/traces/{r['trace_id'][:8]}", headers=headers)
    assert found.status_code == 200 and found.json()["trace_id"] == r["trace_id"]
    assert client.get(f"/admin/traces/{r['trace_id'][:7]}", headers=headers).status_code == 404  # too short to be a code


def test_demo_customers_only_lists_configured_sandbox_accounts(client, monkeypatch):
    assert client.get("/demo/customers").json() == []
    monkeypatch.setenv("DEMO_PUBLIC_CUSTOMERS", "CLI-FIX0001")
    body = client.get("/demo/customers").json()
    assert body == [{"customer_id": "CLI-FIX0001", "test_pin": derive_test_pin("CLI-FIX0001")}]
