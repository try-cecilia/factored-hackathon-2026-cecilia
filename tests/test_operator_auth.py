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


# --- concurrent guesses: the attempt is reserved before the key is compared -------------------------------------------------

import queue  # noqa: E402
import threading  # noqa: E402
from collections import Counter  # noqa: E402

WAIT = 5  # seconds an event may take before a test gives up; no test here measures how long anything takes


def _race(requests: int, send, hold) -> tuple[Counter, int]:
    """`requests` calls at once, the first to reach the comparison held inside it (`hold` installs the gate and returns what to
    release and how many reached the comparison). Returns the statuses and the number of comparisons made."""
    entered, release, compared = threading.Event(), threading.Event(), []
    hold(entered, release, compared)
    statuses: queue.Queue = queue.Queue()
    threads = [threading.Thread(target=lambda: statuses.put(send()), daemon=True) for _ in range(requests)]
    seen: list[int] = []
    try:
        for t in threads:
            t.start()
        assert entered.wait(WAIT), "no request reached the comparison"
        for _ in range(requests - 1):  # the refused ones answer while the first is held; one that was not refused is held too
            try:
                seen.append(statuses.get(timeout=2))
            except queue.Empty:
                break
    finally:
        release.set()
    for t in threads:
        t.join(WAIT)
    while not statuses.empty():
        seen.append(statuses.get_nowait())
    return Counter(seen), len(compared)


@pytest.mark.parametrize("kind", ["admin", "operator"])
def test_with_one_failure_left_only_one_concurrent_guess_is_compared_and_the_rest_are_refused(kind, monkeypatch):
    monkeypatch.setattr(main, "operator_fail_limiter", main.RateLimiter(10, 60))
    for _ in range(9):
        main.operator_fail_limiter.record("testclient")  # nine failures in the window: one place left
    client = TestClient(main.app)
    url, headers = ("/admin/human_queue", {"X-Admin-Key": "wrong"}) if kind == "admin" else ("/admin/operator/me", as_operator("wrong"))

    def hold(entered, release, compared):
        def gate(real):
            def wrapper(*args):
                compared.append(1)
                entered.set()
                assert release.wait(WAIT), "the held comparison was never released"
                return real(*args)
            return wrapper

        if kind == "admin":
            monkeypatch.setattr(main, "constant_time_equals", gate(main.constant_time_equals))
        else:
            monkeypatch.setattr(main.OperatorDirectory, "authenticate", gate(main.OperatorDirectory.authenticate))

    statuses, compared = _race(5, lambda: client.get(url, headers=headers).status_code, hold)
    assert compared == 1  # the single place left was taken before the comparison
    assert statuses == {401: 1, 429: 4}


def test_a_correct_key_gives_its_reserved_place_back(monkeypatch):
    monkeypatch.setattr(main, "operator_fail_limiter", main.RateLimiter(2, 60))
    client = TestClient(main.app)
    for _ in range(5):  # only failures count: any number of right keys leaves the window as it was
        assert client.get("/admin/human_queue", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 200
        assert client.get("/admin/operator/me", headers=as_operator(ANA_KEY)).status_code == 200
    assert client.get("/admin/human_queue", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert client.get("/admin/human_queue", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 200  # one failure of two
    assert client.get("/admin/human_queue", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert client.get("/admin/human_queue", headers={"X-Admin-Key": ADMIN_KEY}).status_code == 429  # two of two: closed


def test_the_limiter_reserves_atomically_and_gives_back_only_what_it_was_given():
    limiter = main.RateLimiter(2, 60)
    first, second = limiter.reserve("a"), limiter.reserve("a")
    assert first is not None and second is not None and limiter.reserve("a") is None and limiter.reserve("b") is not None
    limiter.release("a", first)
    assert limiter.reserve("a") is not None and limiter.reserve("a") is None
    limiter.release("c", 123.0)  # not held: ignored
