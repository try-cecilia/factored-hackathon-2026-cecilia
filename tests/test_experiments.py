"""Shadow y canary: un candidato se prueba con tráfico real sin que el cliente lo note ni lo pague."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent.core.experiments import Experiments, bucket, cohorts, summarize_shadow
from agent.core.orchestrator import Orchestrator
from agent.llm.client import LLMUnavailable
from agent.session.auth import SessionStore
from agent.tools.audit import default_trace_log
from api import main
from eval.fake_llm import FakeLLMClient, tool_call_response

BALANCE = tool_call_response("get_account_summary", {})
ATTRS = {"segment": "Student", "country": "México", "customer_status": "Active"}


class Broken:
    def chat(self, *a, **k):
        raise LLMUnavailable("candidate down", [])


def turn(experiments, primary=None, text="¿cuál es mi saldo?"):
    fake = primary or FakeLLMClient([BALANCE])
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: fake, experiments=experiments)
    tok = orch.session_store.issue("CLI-FIX0001", ATTRS).token
    result = orch.handle_message(tok, text)
    last = [json.loads(line) for line in default_trace_log.path.read_text(encoding="utf-8").splitlines()][-1]
    return result, last


@pytest.fixture(autouse=True)
def log(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    return tmp_path / "shadow.jsonl"


def test_a_key_always_lands_in_the_same_bucket_and_the_buckets_are_even():
    assert bucket("session-1") == bucket("session-1")
    share = sum(bucket(f"s{i}") < 10 for i in range(2000)) / 2000
    assert 0.07 < share < 0.13


def test_both_are_off_unless_configured_and_the_turn_is_the_usual_one():
    result, trace = turn(Experiments())
    assert result.disposition == "AUTO_RESOLVE" and trace["cohort"] == "primary"


def test_canary_serves_the_chosen_share_of_sessions_with_the_candidate():
    candidate = FakeLLMClient([BALANCE])
    result, trace = turn(Experiments(canary=lambda: candidate, canary_percent=100), primary=FakeLLMClient([]))
    assert (result.disposition, trace["cohort"], candidate.call_count) == ("AUTO_RESOLVE", "canary", 1)
    other, trace = turn(Experiments(canary=lambda: candidate, canary_percent=0))
    assert trace["cohort"] == "primary" and candidate.call_count == 1  # 0%: the candidate is never called


def test_a_broken_canary_costs_the_customer_nothing():
    result, trace = turn(Experiments(canary=lambda: Broken(), canary_percent=100))
    assert result.disposition == "AUTO_RESOLVE" and trace["cohort"] == "canary_fallback"


def test_shadow_logs_what_the_candidate_would_have_done_and_the_customer_reply_is_unchanged(log):
    agree = Experiments(shadow=lambda: FakeLLMClient([BALANCE]))
    result, trace = turn(agree)
    agree.drain()
    assert result.disposition == "AUTO_RESOLVE" and trace["cohort"] == "primary"
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert (row["same_tools"], row["same_args"]) == (True, True) and row["shadow"]["calls"][0]["name"] == "get_account_summary"

    differ = Experiments(shadow=lambda: FakeLLMClient([tool_call_response("get_exchange_rate", {"source_currency": "USD", "target_currency": "MXN"})]))
    turn(differ)
    differ.drain()
    assert json.loads(log.read_text(encoding="utf-8").splitlines()[-1])["same_tools"] is False


def test_a_shadow_that_fails_is_a_finding_in_the_log_not_a_problem_for_the_customer(log):
    exp = Experiments(shadow=lambda: Broken())
    result, _ = turn(exp)
    exp.drain()
    assert result.disposition == "AUTO_RESOLVE"
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["shadow"] == {"error": "LLMUnavailable"} and row["same_tools"] is None


def test_shadow_does_not_run_on_the_canary_cohort_and_respects_its_sample():
    shadow = FakeLLMClient([BALANCE])
    turn(Experiments(shadow=lambda: shadow, canary=lambda: FakeLLMClient([BALANCE]), canary_percent=100))
    assert shadow.call_count == 0  # the canary is already the candidate: comparing it with itself says nothing
    turn(Experiments(shadow=lambda: shadow, shadow_percent=0))
    assert shadow.call_count == 0


def test_the_summaries_count_agreement_errors_and_group_the_traces_by_cohort():
    row = lambda same, lat: {"trace_id": "t", "same_tools": same, "same_args": same, "primary": {"calls": [1], "latency_ms": 100},  # noqa: E731
                             "shadow": {"calls": [2], "latency_ms": lat}}
    s = summarize_shadow([row(True, 50), row(False, 150), {"trace_id": "t", "same_tools": None, "same_args": None, "primary": {"calls": []}, "shadow": {"error": "X"}}])
    assert (s["turns"], s["candidate_errors"], s["same_tools_rate"], len(s["disagreements"])) == (3, 1, 0.5, 1)
    c = cohorts([{"cohort": "canary", "disposition": "ESCALATE", "latency_ms": 10}, {"disposition": "AUTO_RESOLVE", "latency_ms": 5, "cost_usd": 0.1}])
    assert c["canary"]["escalation_rate"] == 1.0 and c["primary"]["cost_usd"] == 0.1


def test_the_endpoint_needs_the_admin_key_and_reports_the_config(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "k")
    client = TestClient(main.app)
    assert client.get("/admin/experiments").status_code == 401
    body = client.get("/admin/experiments", headers={"X-Admin-Key": "k"}).json()
    assert body["config"] == {"canary_percent": 0, "shadow_enabled": False, "canary_enabled": False} and "cohorts" in body
