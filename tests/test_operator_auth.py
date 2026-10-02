"""Autenticación del operador: eventos de auditoría, limitador de fallos y endpoints de acción del desk."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent.policy import router
from agent.policy.desk import default_desk
from agent.policy.escalation import escalate
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


def test_the_operator_key_identifies_its_owner_without_acting_and_the_admin_key_does_not():
    client = TestClient(main.app)
    assert client.get("/admin/operator/me", headers=as_operator(BETO_KEY)).json() == {"operator": "beto"}
    assert client.get("/admin/operator/me", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 401
    assert client.get("/admin/operator/me").status_code == 401


def test_behind_the_bff_one_users_wrong_keys_do_not_lock_out_another_and_a_direct_caller_cannot_choose_a_bucket(monkeypatch):
    shared = "bff-secret-0123456789-abcdefgh"
    monkeypatch.setenv("BFF_CLIENT_IP_SECRET", shared)
    monkeypatch.setenv("CLIENT_IP_HEADER", "CF-Connecting-IP")  # Render: every call from the web arrives from its one address
    tid, client = ticket(), TestClient(main.app)
    url = f"/admin/tickets/{tid}/claim"
    web_edge = {"CF-Connecting-IP": "10.0.0.1"}  # the web service, as the API's edge sees it
    via_bff = lambda ip: {**web_edge, "X-Client-IP": ip, "X-BFF-Secret": shared}  # noqa: E731
    for _ in range(3):
        assert client.post(url, json={}, headers={**via_bff("1.1.1.1"), **as_operator("wrong")}).status_code == 401
    assert client.post(url, json={}, headers={**via_bff("1.1.1.1"), **as_operator(ANA_KEY)}).status_code == 429  # A is locked out
    assert client.post(url, json={}, headers={**via_bff("2.2.2.2"), **as_operator(ANA_KEY)}).status_code == 200  # B is not
    # Not through the BFF: a made-up X-Client-IP changes nothing, so a guesser cannot spread its attempts over fresh buckets.
    direct = {"CF-Connecting-IP": "7.7.7.7"}
    for n in range(3):
        headers = {**direct, "X-Client-IP": f"3.3.3.{n}", **as_operator("wrong")}
        assert client.post(url, json={}, headers=headers).status_code == 401
    assert client.post(url, json={}, headers={**direct, "X-Client-IP": "3.3.3.99", **as_operator(ANA_KEY)}).status_code == 429
