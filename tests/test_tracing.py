"""One id per turn from the HTTP request to the ticket, per-stage timings, and logs that carry no customer data."""
from __future__ import annotations

import json
import logging
import os
import re

import pytest
from fastapi.testclient import TestClient

from agent import observability
from agent.policy import escalation
from agent.session import identity
from agent.session.identity import derive_test_pin
from api import main

HEX32 = re.compile(r"^[0-9a-f]{32}$")
TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-01$")


@pytest.fixture
def client(monkeypatch):
    identity.default_identity._failures.clear()
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(50, 60))
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(50, 60))
    return TestClient(main.app)


def token(client, cid="CLI-FIX0001") -> str:
    return client.post("/auth/session", json={"customer_id": cid, "pin": derive_test_pin(cid)}).json()["token"]


def say(client, tok, text, **headers):
    return client.post("/chat", json={"session_token": tok, "message": text}, headers=headers)


def rows(env: str) -> list[dict]:
    path = os.environ[env]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def test_every_response_carries_the_trace_id_and_it_is_the_one_in_the_body(client):
    r = say(client, token(client), "Me clonaron la tarjeta")
    rid = r.headers["X-Request-ID"]
    assert HEX32.match(rid) and r.json()["trace_id"] == rid
    m = TRACEPARENT.match(r.headers["traceparent"])
    assert m and m.group(1) == rid  # the W3C trace id is ours, so a tracing backend can join on it


def test_the_same_id_is_in_the_trace_record_the_ticket_and_the_tool_audit(client):
    tok = token(client)
    threat = say(client, tok, "Me clonaron la tarjeta")
    balance = say(client, tok, "¿Cuál es mi saldo?")  # no model key here: the deterministic balance path runs a tool
    for r in (threat, balance):
        assert any(t["trace_id"] == r.headers["X-Request-ID"] for t in rows("TRACE_LOG_PATH"))
    ticket = escalation.default_queue.get(threat.json()["ticket_id"])
    assert ticket["trace_id"] == threat.headers["X-Request-ID"]
    tool_calls = [a for a in rows("AUDIT_LOG_PATH") if a.get("tool_name") == "get_account_summary"
                  and a.get("trace_id") == balance.headers["X-Request-ID"]]
    assert tool_calls, "the tool's audit record must carry the turn's trace id"


def test_two_requests_never_share_an_id_even_when_the_caller_reuses_its_own(client):
    tok = token(client)
    same = {"traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01", "X-Request-ID": "client-42"}
    ids = {say(client, tok, "Me clonaron la tarjeta", **same).headers["X-Request-ID"] for _ in range(3)}
    assert len(ids) == 3 and "a" * 32 not in ids


def test_a_callers_own_ids_are_kept_beside_ours_and_only_when_valid(client):
    tok = token(client)
    say(client, tok, "Me clonaron la tarjeta", traceparent="00-" + "a" * 32 + "-" + "b" * 16 + "-01", **{"X-Request-ID": "web-bff-7"})
    record = rows("TRACE_LOG_PATH")[-1]
    assert (record["upstream_trace_id"], record["upstream_span_id"], record["client_request_id"]) == ("a" * 32, "b" * 16, "web-bff-7")
    assert record["trace_id"] != "a" * 32
    for bad in ({"traceparent": "garbage"}, {"traceparent": "00-" + "0" * 32 + "-" + "b" * 16 + "-01"},
                {"X-Request-ID": "has spaces and <script>"}, {"X-Request-ID": "x" * 65}):
        say(client, tok, "Me clonaron la tarjeta", **bad)
        record = rows("TRACE_LOG_PATH")[-1]
        assert not ({"upstream_trace_id", "client_request_id"} & set(record))


def test_errors_and_refusals_carry_the_id_too(client, monkeypatch):
    for r in (client.get("/admin/ops"), client.get("/nope"), client.post("/chat", json={"session_token": "x", "message": ""})):
        assert HEX32.match(r.headers["X-Request-ID"]) and TRACEPARENT.match(r.headers["traceparent"])
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(1, 60))
    tok = token(client)
    say(client, tok, "hola")
    limited = say(client, tok, "hola")
    assert limited.status_code == 429 and HEX32.match(limited.headers["X-Request-ID"])


def test_a_turn_records_each_stage_with_its_start_duration_and_outcome(client):
    say(client, token(client), "¿Cuál es mi saldo?")
    record = rows("TRACE_LOG_PATH")[-1]
    stages = record["stages"]
    names = [s["stage"] for s in stages]
    assert names[:3] == ["session", "pre_llm", "ownership_check"] and "catalog" in names and "llm" in names
    assert all({"span_id", "stage", "start_ms", "ms", "outcome"} <= set(s) for s in stages)
    assert all(re.fullmatch(r"[0-9a-f]{16}", s["span_id"]) and s["ms"] >= 0 for s in stages)
    assert [s["start_ms"] for s in stages] == sorted(s["start_ms"] for s in stages)
    assert next(s for s in stages if s["stage"] == "llm")["outcome"] == "LLMUnavailable"  # no key configured: the failure is the outcome
    assert record["turn_budget_left_ms"] > 0 and record["span_id"]  # the request's root span id


def test_the_stages_of_a_turn_that_answers_from_data_include_the_tool_and_the_rendering(client, monkeypatch):
    from agent.core import orchestrator as orch_mod
    from eval.fake_llm import FakeLLMClient, tool_call_response

    fake = FakeLLMClient([tool_call_response("get_account_summary", {"product_id": "PRD-FIX0001"})])
    monkeypatch.setattr(orch_mod.default_orchestrator, "_llm", lambda: fake)
    say(client, token(client), "¿saldo de mi ahorro 0001?")
    names = [s["stage"] for s in rows("TRACE_LOG_PATH")[-1]["stages"]]
    assert names[-3:] == ["llm", "tool:get_account_summary", "render"] and "ticket" not in names


def test_a_handoff_times_the_ticket_write_as_a_stage(client):
    say(client, token(client), "Me clonaron la tarjeta")
    stages = {s["stage"]: s for s in rows("TRACE_LOG_PATH")[-1]["stages"]}
    assert stages["ticket"]["outcome"] == "ok" and stages["ticket"]["category"] == "theft" and "llm" not in stages


def test_the_turn_log_line_has_the_id_and_the_outcome_and_nothing_the_customer_wrote(client, caplog):
    tok = token(client)
    with caplog.at_level(logging.INFO):
        r = say(client, tok, "Me clonaron la tarjeta 5000000001, soy Ana Pérez, mi saldo era 12,345.67")
    turn = [rec for rec in caplog.records if rec.name == "cecilai.turn"]
    assert len(turn) == 1 and turn[0].fields["trace_id"] == r.headers["X-Request-ID"]
    assert turn[0].fields["disposition"] == "ESCALATE" and turn[0].fields["category"] == "theft"
    everything = "\n".join(f"{rec.getMessage()} {getattr(rec, 'fields', '')}" for rec in caplog.records)
    for secret in ("5000000001", "Ana", "Pérez", "12,345.67", "CLI-FIX0001", tok, r.json()["response_text"]):
        assert secret not in everything


def test_json_logs_are_one_object_per_line_with_the_trace_id():
    record = logging.LogRecord("cecilai.turn", logging.INFO, __file__, 1, "turn disposition=%s", ("ESCALATE",), None)
    record.trace_id, record.fields = "a" * 32, {"latency_ms": 12.5}
    out = json.loads(observability.JsonFormatter().format(record))
    assert out["trace_id"] == "a" * 32 and out["latency_ms"] == 12.5 and out["msg"] == "turn disposition=ESCALATE"


def test_the_trace_id_filter_stamps_records_only_inside_a_turn():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "m", (), None)
    observability.TraceIdFilter().filter(rec)
    assert rec.trace_id == "-"
    token_ = observability.current_trace_id.set("c" * 32)
    try:
        observability.TraceIdFilter().filter(rec)
        assert rec.trace_id == "c" * 32
    finally:
        observability.current_trace_id.reset(token_)


def test_a_failed_operator_login_is_audited_with_the_requests_trace_id(client, monkeypatch):
    monkeypatch.setenv("OPERATOR_KEYS", "ana=s3cret-operator-key-123456-abcdefghij")
    r = client.post("/admin/tickets/none/claim", json={}, headers={"X-Operator-Key": "wrong"})
    assert r.status_code == 401
    event = [a for a in rows("AUDIT_LOG_PATH") if a.get("event") == "operator_auth_failed"][-1]
    assert event["trace_id"] == r.headers["X-Request-ID"]


def test_the_last_resort_500_says_nothing_of_the_exception_and_carries_the_id(client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("customer CLI-FIX0001 secret detail")

    monkeypatch.setattr(main, "account_tools", type("T", (), {"data_as_of": staticmethod(boom)}))
    monkeypatch.setattr(main, "default_providers", boom)
    r = TestClient(main.app, raise_server_exceptions=False).get("/health")
    assert r.status_code == 500 and r.json()["detail"] == "internal error" and "secret" not in r.text
    assert r.json()["request_id"] == r.headers["X-Request-ID"]
