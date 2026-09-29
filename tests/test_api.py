"""HTTP-level tests: auth factor, admin fail-closed, limits, no token leakage."""
from __future__ import annotations

import json

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


def test_behind_render_each_client_has_its_own_login_limit_and_nobody_can_pick_it_elsewhere(client, monkeypatch):
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(1, 60))
    as_ip = lambda ip: {"CF-Connecting-IP": ip}  # noqa: E731
    body = {"customer_id": "CLI-FIX0004", "pin": derive_test_pin("CLI-FIX0004")}
    # Anywhere else the header is the client's own words: ignored, one bucket for this connection.
    assert [client.post("/auth/session", json=body, headers=as_ip(ip)).status_code for ip in ("1.1.1.1", "2.2.2.2")] == [200, 429]
    # On Render the edge sets it and no client can forge it: one bucket per real client.
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(1, 60))
    monkeypatch.setenv("CLIENT_IP_HEADER", "CF-Connecting-IP")
    codes = [client.post("/auth/session", json=body, headers=as_ip(ip)).status_code for ip in ("1.1.1.1", "2.2.2.2", "1.1.1.1")]
    assert codes == [200, 200, 429]


def test_behind_the_bff_each_user_has_its_own_login_limit_only_when_configured(client, monkeypatch):
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(1, 60))
    as_ip = lambda ip: {"X-Client-IP": ip}  # noqa: E731
    body = {"customer_id": "CLI-FIX0004", "pin": derive_test_pin("CLI-FIX0004")}
    assert [client.post("/auth/session", json=body, headers=as_ip(ip)).status_code for ip in ("1.1.1.1", "2.2.2.2")] == [200, 429]
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(1, 60))
    monkeypatch.setenv("CLIENT_IP_HEADER", "X-Client-IP")
    codes = [client.post("/auth/session", json=body, headers=as_ip(ip)).status_code for ip in ("1.1.1.1", "2.2.2.2", "1.1.1.1")]
    assert codes == [200, 200, 429]


def login(client, cid="CLI-FIX0001", pin=None):
    return client.post("/auth/session", json={"customer_id": cid, "pin": pin or derive_test_pin(cid)})


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["data_as_of"] == "2024-01-16"
    assert body["llm_budget_exhausted"] is False  # a monitor can alert on it; the amounts stay behind the admin key


def test_the_operations_summary_counts_what_an_operator_watches(client):
    token = login(client).json()["token"]
    client.post("/chat", json={"session_token": token, "message": "Me clonaron la tarjeta"})  # theft, before any model
    client.post("/chat", json={"session_token": token, "message": "¿Cuál es mi saldo?"})  # no model key here: degraded mode
    assert client.get("/admin/ops").status_code == 401
    s = client.get("/admin/ops", headers={"X-Admin-Key": "test-admin-key"}).json()
    assert s["turns"] >= 2 and s["dispositions"]["ESCALATE"] >= 1 and s["escalations_by_category"]["theft"] >= 1
    assert s["degraded_turns"] >= 1 and s["handoff_unverified"] == 0
    assert {"latency_ms_p50", "latency_ms_p95", "cost_usd", "models", "traces_opened", "llm_budget", "top_rules"} <= set(s)


def test_the_trace_log_gives_operators_the_last_turns_in_order_and_no_token(client):
    token = login(client).json()["token"]
    for message in ("Me clonaron la tarjeta", "¿Cuál es mi saldo?"):
        client.post("/chat", json={"session_token": token, "message": message})
    assert client.get("/admin/trace_log").status_code == 401
    rows = client.get("/admin/trace_log?limit=2", headers={"X-Admin-Key": "test-admin-key"}).json()
    assert len(rows) == 2 and rows[0]["ts"] <= rows[1]["ts"]
    assert (rows[0]["disposition"], rows[0]["category"]) == ("ESCALATE", "theft")
    assert token not in json.dumps(rows)


def test_the_daily_model_budget_is_reported_to_operators_only(client, monkeypatch):
    from agent.llm.budget import DailyBudget

    monkeypatch.setattr(main, "default_budget", DailyBudget(limit_usd=5.0))
    main.default_budget.add(1.25)
    assert client.get("/admin/llm_budget").status_code == 401
    body = client.get("/admin/llm_budget", headers={"X-Admin-Key": "test-admin-key"}).json()
    assert body == {"limit_usd": 5.0, "spent_today_usd": 1.25, "exhausted": False}


def test_customer_id_alone_is_not_enough(client):
    assert client.post("/auth/session", json={"customer_id": "CLI-FIX0001"}).status_code == 422
    assert login(client, pin="000000" if derive_test_pin("CLI-FIX0001") != "000000" else "111111").status_code == 401
    ok = login(client)
    assert ok.status_code == 200 and "token" in ok.json()
    assert ok.json()["expires_in"] == 900  # seconds, so a client clock that is off does not matter


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
    monkeypatch.setenv("DEMO_MODE", "1")  # a demo surface: outside the sandbox it does not exist (tests/test_access_matrix.py)
    assert client.get("/demo/customers").json() == []
    monkeypatch.setenv("DEMO_PUBLIC_CUSTOMERS", "CLI-FIX0001")
    body = client.get("/demo/customers").json()
    assert body == [{"customer_id": "CLI-FIX0001", "test_pin": derive_test_pin("CLI-FIX0001")}]


def test_the_session_can_be_read_back_without_extending_it(client):
    s = login(client).json()
    headers = {"X-Session-Token": s["token"]}
    first, second = client.get("/auth/session", headers=headers), client.get("/auth/session", headers=headers)
    assert first.status_code == 200 and first.json()["expires_at"] == second.json()["expires_at"] == s["expires_at"]
    body = first.json()
    assert set(body) == {"customer_id", "session_ref", "segment", "country", "customer_status", "expires_at", "expires_in"}
    assert body["customer_id"] == "CLI-FIX0001" and body["session_ref"] == s["session_ref"]
    assert body["segment"] and body["country"] and body["customer_status"]
    assert 0 < body["expires_in"] <= 900
    assert s["token"] not in json.dumps(body)


@pytest.mark.parametrize("case", ["missing", "garbage", "revoked", "expired"])
def test_reading_a_session_that_is_not_live_is_a_401(client, case):
    from agent.session.auth import default_store

    token = login(client).json()["token"]
    if case == "revoked":
        default_store.revoke(token)
    if case == "expired":
        default_store.expire(token)
    headers = {} if case == "missing" else {"X-Session-Token": "not-a-real-token" if case == "garbage" else token}
    r = client.get("/auth/session", headers=headers)
    assert r.status_code == 401 and r.json() == {"detail": "invalid or expired session"}


def test_logout_ends_the_session_and_never_fails(client):
    token = login(client).json()["token"]
    headers = {"X-Session-Token": token}
    assert client.delete("/auth/session", headers=headers).status_code == 204
    assert client.get("/auth/session", headers=headers).status_code == 401
    r = client.post("/chat", json={"session_token": token, "message": "¿Cuál es mi saldo?"})
    assert r.status_code == 200 and r.json()["disposition"] == "REAUTH_REQUIRED"
    assert client.delete("/auth/session", headers=headers).status_code == 204  # already revoked
    assert client.delete("/auth/session", headers={"X-Session-Token": "not-a-real-token"}).status_code == 204
    assert client.delete("/auth/session").status_code == 204
    admin = {"X-Admin-Key": "test-admin-key"}
    logs = client.get("/admin/audit_log?limit=500", headers=admin).text + client.get("/admin/trace_log", headers=admin).text
    assert token not in logs
