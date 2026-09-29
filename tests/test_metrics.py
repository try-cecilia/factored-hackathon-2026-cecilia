"""Metrics (agent/metrics.py, GET /metrics), liveness and readiness."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from agent import metrics as metrics_module
from agent.metrics import Metrics
from agent.session import identity
from agent.session.identity import derive_test_pin
from agent.tools import account_tools
from agent.tools.audit import default_audit_log
from api import main

ADMIN = {"X-Admin-Key": "test-admin-key"}


def parse(text: str) -> dict[str, list]:
    """metric name (a sample's own, e.g. x_total or x_bucket) -> [(labels, value)]"""
    out: dict[str, list] = {}
    for family in text_string_to_metric_families(text):
        for s in family.samples:
            out.setdefault(s.name, []).append((s.labels, s.value))
    return out


def value(samples: dict, name: str, **labels) -> float | None:
    hits = [v for lab, v in samples.get(name, []) if all(lab.get(k) == x for k, x in labels.items())]
    return sum(hits) if hits else None


@pytest.fixture
def m(monkeypatch):
    """A fresh registry for the test, wired in where the app reads it."""
    fresh = Metrics()
    monkeypatch.setattr(metrics_module, "default", fresh)
    return fresh


@pytest.fixture
def client(m, monkeypatch, tmp_path):
    identity.default_identity._failures.clear()
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(100, 60, "login"))
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(100, 60, "chat"))
    monkeypatch.setenv("RETENTION_STATUS_PATH", str(tmp_path / "retention_status.json"))
    monkeypatch.setenv("TRACE_REQUESTS_PATH", str(tmp_path / "trace_requests.jsonl"))
    return TestClient(main.app)


def login(client, cid="CLI-FIX0001") -> str:
    return client.post("/auth/session", json={"customer_id": cid, "pin": derive_test_pin(cid)}).json()["token"]


def scrape(client) -> tuple[str, dict]:
    r = client.get("/metrics", headers=ADMIN)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain; version=0.0.4")
    return r.text, parse(r.text)


def test_a_turn_is_counted_by_disposition_category_latency_and_stage(client):
    token = login(client)
    theft = client.post("/chat", json={"session_token": token, "message": "Me clonaron la tarjeta"}).json()
    client.post("/chat", json={"session_token": token, "message": "¿Cuál es mi saldo?"})  # no model key here: degraded mode
    text, s = scrape(client)
    assert theft["disposition"] == "ESCALATE"
    assert value(s, "cecilai_turns_total", disposition="ESCALATE", category=theft["category"]) == 1
    assert value(s, "cecilai_escalations_total", category=theft["category"]) == 1
    assert value(s, "cecilai_turn_latency_seconds_count") == 2
    assert value(s, "cecilai_turn_latency_seconds_bucket", le="8.0") == 2  # the p95 alert's threshold is a bucket edge
    for stage in ("llm", "tools", "policy_render"):
        assert value(s, "cecilai_stage_latency_seconds_count", stage=stage) == 2
    assert value(s, "cecilai_degraded_turns_total") >= 1
    # the degraded turn asked the model chain first: no key set, so every provider was skipped and that is visible
    assert value(s, "cecilai_llm_attempts_total", outcome="skipped") >= 1


def test_tool_calls_and_their_time_reach_the_metrics(client):
    token = login(client)
    client.post("/chat", json={"session_token": token, "message": "¿Cuál es mi saldo?"})  # degraded mode reads the balance with a tool
    _, s = scrape(client)
    assert value(s, "cecilai_tool_call_seconds_count", tool="get_account_summary") == 1
    tools = value(s, "cecilai_stage_latency_seconds_sum", stage="tools")  # the turn's own tool span
    assert 0 < tools <= value(s, "cecilai_turn_latency_seconds_sum")
    assert value(s, "cecilai_stage_latency_seconds_sum", stage="policy_render") >= 0


def test_llm_attempts_refusals_tokens_and_cost_come_from_the_trace_record(m):
    m.observe_turn({
        "trace_id": "t1", "disposition": "AUTO_RESOLVE", "category": "resolved", "policy_rule": "verified_tool_results",
        "latency_ms": 1500, "provider": "anthropic", "model": "claude-sonnet-5", "llm_calls": 1, "cost_usd": 0.0014,
        "usage": {"prompt_tokens": 400, "completion_tokens": 50, "cache_read_tokens": 1700, "cache_write_tokens": 0},
        "llm_steps": [{"latency_ms": 1200, "attempts": [
            {"provider": "groq", "outcome": "error", "kind": "transient", "error": "Timeout: slow"},
            {"provider": "anthropic", "outcome": "error", "kind": "permanent", "error": "ModelRefusal: declined"},
            {"provider": "together", "outcome": "skipped", "reason": "circuit_open"},
            {"provider": "anthropic", "outcome": "ok"}]}],
        "tool_calls": [{"tool": "get_account_summary", "success": True},
                       {"tool": "list_transactions", "success": False, "error_type": "MissingSlot"}]})
    r = m.registry.get_sample_value
    assert r("cecilai_llm_attempts_total", {"provider": "groq", "outcome": "error", "reason": "transient"}) == 1
    assert r("cecilai_llm_attempts_total", {"provider": "together", "outcome": "skipped", "reason": "circuit_open"}) == 1
    assert r("cecilai_model_refusals_total", {"provider": "anthropic"}) == 1
    assert r("cecilai_llm_tokens_total", {"provider": "anthropic", "model": "claude-sonnet-5", "kind": "cache_read"}) == 1700
    assert r("cecilai_llm_cost_usd_total", {"provider": "anthropic", "model": "claude-sonnet-5"}) == pytest.approx(0.0014)
    assert r("cecilai_tool_calls_total", {"tool": "list_transactions", "outcome": "error", "error_type": "MissingSlot"}) == 1
    assert r("cecilai_stage_latency_seconds_sum", {"stage": "llm"}) == pytest.approx(1.2)
    assert r("cecilai_stage_latency_seconds_sum", {"stage": "policy_render"}) == pytest.approx(0.3)


def test_an_unpriced_call_is_counted_and_a_free_turn_costs_nothing(m):
    m.observe_turn({"trace_id": "a", "disposition": "AUTO_RESOLVE", "category": "resolved", "latency_ms": 5, "llm_calls": 1,
                    "provider": "groq", "model": "unknown-model", "cost_usd": None, "usage": {"prompt_tokens": 10}})
    m.observe_turn({"trace_id": "b", "disposition": "ESCALATE", "category": "fraud", "latency_ms": 5, "llm_calls": 0, "cost_usd": 0.0})
    assert m.registry.get_sample_value("cecilai_llm_unpriced_calls_total", {"provider": "groq", "model": "unknown-model"}) == 1
    assert m.registry.get_sample_value("cecilai_llm_cost_usd_total", {"provider": "groq", "model": "unknown-model"}) is None


def test_the_signals_the_runbook_alerts_on_are_counted(m):
    for rule in ("reference_to_foreign_product", "llm_unavailable", "degraded:deterministic_balance",
                 "lexicon:fraud|handoff_unverified"):
        m.observe_turn({"trace_id": rule, "disposition": "ESCALATE", "category": "x", "policy_rule": rule, "latency_ms": 1})
    r = m.registry.get_sample_value
    assert (r("cecilai_foreign_product_references_total"), r("cecilai_llm_unavailable_turns_total"),
            r("cecilai_degraded_turns_total"), r("cecilai_handoff_unverified_total")) == (1, 1, 1, 1)


def test_http_requests_are_counted_by_route_template_never_by_concrete_path(client):
    token = login(client)
    client.get("/case/T-0123456789", headers={"X-Session-Token": token})
    client.get("/case/T-9999999999", headers={"X-Session-Token": token})
    client.get("/wp-login.php")
    client.get("/admin/tickets/T-1", headers=ADMIN)
    _, s = scrape(client)
    assert value(s, "cecilai_http_requests_total", route="/case/{ticket_id}", status="404") == 2
    assert value(s, "cecilai_http_requests_total", route="unmatched", status="404") == 1
    assert value(s, "cecilai_http_requests_total", route="/admin/tickets/{ticket_id}") == 1
    assert not [lab for lab, _ in s["cecilai_http_requests_total"] if "T-0" in lab["route"] or "wp-login" in lab["route"]]


def test_logins_and_rate_limits_are_counted(client, monkeypatch):
    login(client)
    client.post("/auth/session", json={"customer_id": "CLI-FIX0001", "pin": "000000"})
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(1, 60, "chat"))
    token = login(client)
    for _ in range(3):
        client.post("/chat", json={"session_token": token, "message": "hola"})
    for i in range(3):  # failed admin keys count against their own limiter
        client.get("/admin/ops", headers={"X-Admin-Key": f"guess-{i}"})
    _, s = scrape(client)
    assert value(s, "cecilai_logins_total", result="ok") == 2 and value(s, "cecilai_logins_total", result="invalid") == 1
    assert value(s, "cecilai_rate_limit_hits_total", limiter="chat") == 2


def test_state_gauges_report_budget_breakers_freshness_and_the_pipeline(client, monkeypatch):
    from agent.llm.budget import default_budget
    from agent.llm.client import get_default_client

    monkeypatch.setattr(default_budget, "limit_usd", 5.0)
    default_budget.add(6.0)
    client_llm = get_default_client()
    monkeypatch.setitem(client_llm._down_until, "groq", time.time() + 60)
    monkeypatch.setitem(client_llm._failures, "groq", 2)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "set")
    try:
        _, s = scrape(client)
    finally:
        default_budget._spent = 0.0
    assert value(s, "cecilai_llm_budget_exhausted") == 1 and value(s, "cecilai_llm_budget_limit_usd") == 5
    assert value(s, "cecilai_llm_circuit_open", provider="groq") == 1
    assert value(s, "cecilai_llm_circuit_open", provider="anthropic") == 0
    assert value(s, "cecilai_llm_consecutive_failures", provider="groq") == 2
    assert value(s, "cecilai_llm_provider_configured", provider="anthropic") == 1
    assert value(s, "cecilai_data_freshness_slo_hours") == 36 and value(s, "cecilai_data_freshness_enforced") == 0
    age = value(s, "cecilai_data_age_hours")
    assert age == pytest.approx((time.time() - value(s, "cecilai_data_as_of_timestamp_seconds")) / 3600, abs=0.1) and age > 0
    assert value(s, "cecilai_dq_failed_error_checks") == 0 and value(s, "cecilai_ingestion_failed_tables") == 0
    assert value(s, "cecilai_active_sessions") >= 0 and value(s, "cecilai_intent_classifier_loaded") in (0, 1)
    assert value(s, "cecilai_build_info") == 1


def test_retention_gauges_read_the_purge_status_file(client, tmp_path):
    _, s = scrape(client)
    assert value(s, "cecilai_retention_last_run_timestamp_seconds") == 0  # never ran here
    (tmp_path / "retention_status.json").write_text(json.dumps({
        "last_run": 1234.0, "failed": ["traces"], "outcomes": [{"name": "traces", "dropped": 7}, {"name": "audit", "dropped": 0}]}))
    _, s = scrape(client)
    assert value(s, "cecilai_retention_last_run_timestamp_seconds") == 1234
    assert value(s, "cecilai_retention_failed_stores") == 1
    assert value(s, "cecilai_retention_last_dropped_records", store="traces") == 7
    assert value(s, "cecilai_retention_enabled") == 1


def test_one_failing_source_does_not_fail_the_scrape_and_is_itself_counted(client, monkeypatch):
    def broken():
        raise RuntimeError("warehouse gone")

    monkeypatch.setattr(account_tools, "data_as_of", broken)
    scrape(client)  # the failure is counted while this scrape runs, so it shows in the next one
    _, s = scrape(client)
    assert value(s, "cecilai_scrape_errors_total", source="data") == 1
    assert value(s, "cecilai_llm_budget_exhausted") is not None  # the other sources still answered


def test_no_label_carries_a_customer_a_session_a_ticket_or_a_message(client):
    token = login(client)
    client.post("/chat", json={"session_token": token, "message": "Me clonaron la tarjeta 4111111111111111"})
    client.get("/case/T-abcdef", headers={"X-Session-Token": token})
    text, _ = scrape(client)
    for secret in ("CLI-FIX0001", token, "4111", "clonaron", "T-abcdef"):
        assert secret not in text


def test_metrics_need_credentials(client):
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-Admin-Key": "wrong"}).status_code == 401


def test_liveness_needs_nothing_and_readiness_says_which_dependency_is_down(client, monkeypatch):
    assert client.get("/livez").json() == {"status": "alive"}
    ready = client.get("/readyz")
    assert ready.status_code == 200 and ready.json() == {"status": "ready", "checks": {
        "warehouse": True, "state_store": True, "data_dir_writable": True}}

    def down():
        raise RuntimeError("io error /secret/path")

    import api.observability as observability

    monkeypatch.setattr(observability, "_query_warehouse", down)
    not_ready = client.get("/readyz")
    assert not_ready.status_code == 503
    assert not_ready.json() == {"status": "not_ready", "checks": {"warehouse": False, "state_store": True, "data_dir_writable": True}}
    assert "secret" not in not_ready.text  # the reason stays in the logs: this answer is public
    assert client.get("/livez").status_code == 200  # a broken warehouse is a reason to withhold traffic, not to restart


def test_readiness_notices_a_warehouse_that_disappears_or_breaks_after_it_was_first_read(client, monkeypatch, tmp_path):
    """data_as_of() is cached and a cached connection keeps reading a deleted file, so neither can be the probe."""
    import shutil

    from agent.tools import db
    from agent.tools.db import duckdb_path

    copy = tmp_path / "bank.duckdb"
    shutil.copy(duckdb_path(), copy)
    monkeypatch.setenv("DUCKDB_PATH", str(copy))
    db.close_all()
    try:
        assert client.get("/readyz").status_code == 200
        assert client.get("/health").json()["data_as_of"] == "2024-01-16"  # the read that fills the caches
        copy.unlink()
        gone = client.get("/readyz")
        assert gone.status_code == 503 and gone.json()["checks"]["warehouse"] is False
        copy.write_bytes(b"this is not a duckdb file" * 100)  # present but unreadable
        assert client.get("/readyz").status_code == 503
        assert client.get("/livez").status_code == 200
    finally:
        db.close_all()


def test_readiness_gives_up_on_a_warehouse_that_does_not_answer_in_time(client, monkeypatch):
    import time as time_module

    import api.observability as observability

    monkeypatch.setattr(observability, "_pools", {})
    monkeypatch.setattr(observability, "PROBE_TIMEOUT_S", 0.2)
    monkeypatch.setattr(observability, "_query_warehouse", lambda: time_module.sleep(2))
    started = time_module.perf_counter()
    r = client.get("/readyz")
    assert r.status_code == 503 and r.json()["checks"]["warehouse"] is False
    assert time_module.perf_counter() - started < 1.5


class _EveryProviderFails:
    """A model chain that spends its time and then gives up, as LLMClient does when every provider fails."""

    def chat(self, *args, **kwargs):
        import time as time_module

        from agent.llm.client import LLMUnavailable

        time_module.sleep(0.3)
        raise LLMUnavailable("all LLM providers failed", [
            {"provider": "groq", "outcome": "error", "kind": "transient", "error": "Timeout: slow", "ms": 200.0},
            {"provider": "anthropic", "outcome": "error", "kind": "transient", "error": "Timeout: slow", "ms": 100.0}])


def test_a_turn_where_every_provider_fails_counts_its_wait_as_model_time_not_as_policy(client, monkeypatch):
    """No step of a failed chain has a latency_ms; the time still went to the model, through the orchestrator's real trace."""
    from agent.core.orchestrator import default_orchestrator

    monkeypatch.setattr(default_orchestrator, "_llm", lambda: _EveryProviderFails())
    token = login(client)
    reply = client.post("/chat", json={"session_token": token, "message": "¿Cuál es mi saldo?"}).json()
    _, s = scrape(client)
    assert reply["latency_ms"] >= 300
    llm = value(s, "cecilai_stage_latency_seconds_sum", stage="llm")
    policy = value(s, "cecilai_stage_latency_seconds_sum", stage="policy_render")
    assert llm == pytest.approx(0.3, abs=0.05)  # the llm stage: the chain's 0.3 s plus its own bookkeeping
    assert policy < 0.25  # the rest of the turn (the 0.3 s the chain spent is not in it)


def test_stage_spans_of_the_trace_are_the_preferred_source(m):
    """The orchestrator's `stages` (one span per step) win over anything derived from attempts or the audit log."""
    m.observe_turn({"trace_id": "s1", "disposition": "AUTO_RESOLVE", "category": "resolved", "latency_ms": 2000,
                    "llm_steps": [{"latency_ms": 9999, "attempts": [{"provider": "x", "outcome": "ok", "ms": 9999}]}],
                    "stages": [{"stage": "session", "ms": 3.0}, {"stage": "llm", "ms": 1200.0}, {"stage": "tool:get_account_summary", "ms": 300.0},
                               {"stage": "tool:list_transactions", "ms": 100.0}, {"stage": "render", "ms": 5.0}]})
    r = m.registry.get_sample_value
    assert r("cecilai_stage_latency_seconds_sum", {"stage": "llm"}) == pytest.approx(1.2)
    assert r("cecilai_stage_latency_seconds_sum", {"stage": "tools"}) == pytest.approx(0.4)
    assert r("cecilai_stage_latency_seconds_sum", {"stage": "policy_render"}) == pytest.approx(0.4)


def test_without_stage_spans_a_failed_chain_is_the_sum_of_its_attempts_and_their_waits(m):
    m.observe_turn({"trace_id": "s2", "disposition": "ESCALATE", "category": "llm_unavailable", "latency_ms": 1000,
                    "llm_steps": [{"outcome": "unavailable", "attempts": [
                        {"provider": "groq", "outcome": "error", "kind": "transient", "ms": 300.0, "wait_ms": 200.0},
                        {"provider": "anthropic", "outcome": "error", "kind": "transient", "ms": 100.0}]}]})
    r = m.registry.get_sample_value
    assert r("cecilai_stage_latency_seconds_sum", {"stage": "llm"}) == pytest.approx(0.6)
    assert r("cecilai_stage_latency_seconds_sum", {"stage": "policy_render"}) == pytest.approx(0.4)


def test_probes_that_hang_never_pile_up_threads_and_the_next_probes_answer_at_once(client, monkeypatch):
    """/readyz is public: a hung warehouse must cost at most one stuck thread however often it is probed."""
    import threading
    import time as time_module

    import api.observability as observability

    release = threading.Event()
    monkeypatch.setattr(observability, "_pools", {})  # slots held by an earlier test's stuck probe are not this test's
    monkeypatch.setattr(observability, "PROBE_TIMEOUT_S", 0.1)
    monkeypatch.setattr(observability, "_query_warehouse", lambda: release.wait(20))
    before = threading.active_count()
    durations = []
    try:
        for _ in range(12):
            started = time_module.perf_counter()
            r = client.get("/readyz")
            durations.append(time_module.perf_counter() - started)
            assert r.status_code == 503 and r.json()["checks"]["warehouse"] is False
        assert threading.active_count() - before <= 1, "hung probes accumulated threads"
        assert max(durations[1:]) < 0.05  # once one is stuck the rest are refused without waiting, and without a queue
    finally:
        release.set()
    deadline = time_module.time() + 5
    while threading.active_count() > before and time_module.time() < deadline:
        time_module.sleep(0.02)
    monkeypatch.setattr(observability, "_query_warehouse", lambda: True)
    assert client.get("/readyz").status_code == 200  # the slot came back when the stuck probe ended
