"""Safe fallback, one test per way a turn can fail: the customer gets a fixed reply or a handoff, never an invented
answer and never a half-done action. Faults are injected; nothing here reaches a model or a network."""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from agent.core import orchestrator as orch_mod
from agent.core import render
from agent.core.orchestrator import Orchestrator
from agent.llm.budget import DailyBudget, SessionBudget
from agent.llm.client import LLMClient, Provider
from agent.policy import escalation
from agent.session.auth import SessionStore
from agent.tools import audit, traces
from eval.fake_llm import FakeLLMClient, tool_call_response


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_REQUESTS_PATH", str(tmp_path / "trace_requests.jsonl"))
    monkeypatch.setenv("HUMAN_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("TRACE_LOG_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.setenv("P1_KEY", "k")
    monkeypatch.setenv("P2_KEY", "k")


def lines(env: str) -> list[dict]:
    path = os.environ[env]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


class HttpError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def failing_client(error, calls, providers=2, **kw):
    def make_provider(n):
        def create(**kwargs):
            calls.append(f"p{n}")
            raise error

        sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        return Provider(f"p{n}", f"m{n}", f"P{n}_KEY", lambda key, timeout: sdk)

    return LLMClient([make_provider(n) for n in range(1, providers + 1)], sleep=lambda s: None, **kw)


def orchestrator(llm, customer="CLI-FIX0001", **kw):
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: llm, **kw)
    tok = orch.session_store.issue(customer, {"segment": "Premium", "country": "México", "customer_status": "Active"}).token
    return orch, tok


ASK = "movimientos de mi tarjeta"  # needs the model to pick a tool: the classifier cannot answer it alone
FIXED = {m[lang] for m in render.MSG.values() for lang in ("es", "pt")}


def assert_handed_over(r, category, rule=None):
    assert (r.disposition, r.category) == ("ESCALATE", category) and r.ticket_id
    assert r.verified_facts == [] and r.response_text in FIXED  # a template, no figure, nothing claimed
    ticket = lines("HUMAN_QUEUE_PATH")[-1]
    assert ticket["ticket_id"] == r.ticket_id and ticket["trace_id"] == r.trace_id
    if rule:
        assert r.policy_rule == rule


# --- the model fails ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("error", [HttpError(503), HttpError(429), TimeoutError("slow"), ConnectionError("reset")])
def test_when_every_provider_fails_transiently_the_turn_is_handed_to_a_person_after_bounded_attempts(error):
    calls = []
    orch, tok = orchestrator(failing_client(error, calls, max_attempts_per_provider=2))
    r = orch.handle_message(tok, ASK)
    assert_handed_over(r, "llm_unavailable", "llm_unavailable")
    assert calls == ["p1", "p1", "p2", "p2"]  # two providers, two attempts each: the bound, not a loop
    attempts = lines("TRACE_LOG_PATH")[-1]["llm_steps"][0]["attempts"]
    assert all(a["outcome"] == "error" and a["kind"] == "transient" for a in attempts)


def test_a_permanent_model_error_is_not_retried_and_still_ends_in_a_handoff():
    calls = []
    orch, tok = orchestrator(failing_client(HttpError(401), calls, providers=1))
    assert_handed_over(orch.handle_message(tok, ASK), "llm_unavailable")
    assert calls == ["p1"]


def test_an_open_circuit_skips_the_provider_and_the_turn_still_ends_safely():
    calls = []
    client = failing_client(HttpError(503), calls, providers=1, breaker_threshold=2)
    orch, tok = orchestrator(client)
    orch.handle_message(tok, ASK)  # two failed attempts open the circuit
    r = orch.handle_message(tok, ASK)
    assert_handed_over(r, "llm_unavailable")
    assert calls == ["p1", "p1"]  # nothing was sent while the circuit was open
    assert lines("TRACE_LOG_PATH")[-1]["llm_steps"][0]["attempts"] == [{"provider": "p1", "outcome": "skipped", "reason": "circuit_open"}]


def test_the_circuit_closes_again_after_its_cooldown(monkeypatch):
    import time as time_mod

    calls = []
    client = failing_client(HttpError(503), calls, providers=1, breaker_threshold=2, breaker_cooldown_s=30)
    orch, tok = orchestrator(client)
    orch.handle_message(tok, ASK)
    now = time_mod.time()
    monkeypatch.setattr("agent.llm.client.time.time", lambda: now + 31)
    orch.handle_message(tok, ASK)
    assert len(calls) == 3  # one probe went through after the cooldown (and failed, so the circuit is open again)
    orch.handle_message(tok, ASK)
    assert len(calls) == 3


def test_a_provider_that_runs_out_the_turns_budget_ends_in_a_handoff_not_a_hang():
    import time

    calls = []

    def create(**kwargs):
        calls.append(1)
        time.sleep(0.05)
        raise HttpError(503)

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    client = LLMClient([Provider("p1", "m", "P1_KEY", lambda key, timeout: sdk)], total_budget_s=0.03, backoff_base_s=1.0, sleep=lambda s: None)
    orch, tok = orchestrator(client)
    r = orch.handle_message(tok, ASK)
    assert_handed_over(r, "llm_unavailable")
    assert len(calls) == 1 and lines("TRACE_LOG_PATH")[-1]["llm_steps"][0]["attempts"][-1]["reason"] == "turn_budget_exhausted"


def test_the_daily_budget_running_out_answers_only_what_needs_no_model_and_hands_over_the_rest():
    fake = FakeLLMClient([])
    orch, tok = orchestrator(fake, budget=DailyBudget(limit_usd=0.001))
    orch.budget.add(1.0)
    balance = orch.handle_message(tok, "¿Cuál es mi saldo?")
    assert (balance.disposition, balance.policy_rule) == ("AUTO_RESOLVE", "degraded:deterministic_balance")
    assert_handed_over(orch.handle_message(tok, ASK), "llm_unavailable")
    assert fake.call_count == 0  # the model was never called once the cap was reached


def test_a_session_that_spent_its_share_is_degraded_alone():
    fake = FakeLLMClient([])
    orch, tok = orchestrator(fake, session_budget=SessionBudget(limit_usd=0.05))
    other = orch.session_store.issue("CLI-FIX0004", {"segment": "Student", "country": "México", "customer_status": "Active"}).token
    from agent.session.auth import session_ref

    orch.session_budget.add(session_ref(tok), 0.05)
    r = orch.handle_message(tok, ASK)
    assert_handed_over(r, "llm_unavailable")
    assert lines("TRACE_LOG_PATH")[-1]["llm_steps"][0]["attempts"][0]["reason"] == "session_budget_exhausted"
    assert fake.call_count == 0
    assert not orch.session_budget.exhausted(session_ref(other))  # another session is unaffected


def test_a_reply_the_model_cannot_use_never_becomes_an_answer():
    from eval.fake_llm import text_response

    orch, tok = orchestrator(FakeLLMClient([text_response("Tu saldo es 9,999.99"), tool_call_response("wire_money", {"to": "x"})]))
    prose = orch.handle_message(tok, "¿Cuánto tengo?")
    assert "9,999" not in prose.response_text and prose.disposition in ("CLARIFY", "ABSTAIN")
    unknown = orch.handle_message(tok, "manda dinero")
    assert unknown.disposition == "ESCALATE" and unknown.category == "tool_failure"


# --- the turn's own clock -------------------------------------------------------------------------------------------

def test_when_the_turns_budget_runs_out_after_the_model_answers_no_lookup_starts(monkeypatch):
    monkeypatch.setenv("TURN_BUDGET_SECONDS", "1e-9")  # gone by the time the model answers
    orch, tok = orchestrator(FakeLLMClient([tool_call_response("get_account_summary", {})]))
    r = orch.handle_message(tok, "¿saldo de mi ahorro?")
    assert_handed_over(r, "turn_timeout", "turn_timeout")
    assert not [a for a in lines("AUDIT_LOG_PATH") if a.get("trace_id") == r.trace_id and a.get("tool_name") == "get_account_summary"]


# --- a tool fails -------------------------------------------------------------------------------------------------

def test_a_tool_that_is_down_is_retried_a_bounded_number_of_times_then_the_data_goes_to_a_person(monkeypatch):
    calls = []

    def down(customer_id, **kw):
        calls.append(1)
        raise OSError("warehouse unreachable")

    monkeypatch.setitem(orch_mod.TOOL_FUNCTIONS, "get_account_summary", down)
    orch, tok = orchestrator(FakeLLMClient([tool_call_response("get_account_summary", {})]))
    r = orch.handle_message(tok, "¿saldo de mi ahorro?")
    assert_handed_over(r, "tool_failure")
    assert len(calls) == orch_mod.TOOL_RETRY.max_attempts == 2


def test_a_tool_that_recovers_answers_from_its_verified_result(monkeypatch):
    real = orch_mod.TOOL_FUNCTIONS["get_account_summary"]
    calls = []

    def flaky(customer_id, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("busy")
        return real(customer_id, **kw)

    monkeypatch.setitem(orch_mod.TOOL_FUNCTIONS, "get_account_summary", flaky)
    orch, tok = orchestrator(FakeLLMClient([tool_call_response("get_account_summary", {"product_id": "PRD-FIX0001"})]))
    r = orch.handle_message(tok, "¿saldo de mi ahorro 0001?")
    assert r.disposition == "AUTO_RESOLVE" and "2,455.81" in r.response_text and len(calls) == 2


def test_a_tool_error_that_is_an_answer_is_never_retried(monkeypatch):
    from agent.tools.errors import DataUnavailable

    calls = []

    def missing(customer_id, **kw):
        calls.append(1)
        raise DataUnavailable("no balance", field="balance")

    monkeypatch.setitem(orch_mod.TOOL_FUNCTIONS, "get_account_summary", missing)
    orch, tok = orchestrator(FakeLLMClient([tool_call_response("get_account_summary", {})]))
    assert_handed_over(orch.handle_message(tok, "¿saldo de mi ahorro?"), "data_unavailable")
    assert len(calls) == 1


# --- the tracing service fails: the one write --------------------------------------------------------------------

def pending_trace_turn():
    orch, tok = orchestrator(FakeLLMClient([tool_call_response("request_trace", {})]), customer="CLI-FIX0004")
    proposal = orch.handle_message(tok, "hice una transferencia que todavía no llega")
    assert proposal.policy_rule == "action:trace_propose" or proposal.disposition == "CLARIFY"
    return orch, tok


def test_a_tracing_service_that_fails_once_is_retried_and_opens_exactly_one_request(monkeypatch):
    orch, tok = pending_trace_turn()
    real, calls = traces.TraceService.open, []

    def flaky(self, *a, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("connection reset")
        return real(self, *a, **kw)

    monkeypatch.setattr(traces.TraceService, "open", flaky)
    r = orch.handle_message(tok, "sí")
    assert r.policy_rule == "action:trace_opened" and len(calls) == 2
    assert len(lines("TRACE_REQUESTS_PATH")) == 1 and lines("TRACE_REQUESTS_PATH")[0]["trace_id"] in r.response_text


def test_a_write_that_landed_but_reported_failure_is_not_repeated(monkeypatch):
    """The service stored the request, then the confirmation was lost: the retry finds it by its derived id."""
    orch, tok = pending_trace_turn()
    real, calls = traces.TraceService.open, []

    def lost_confirmation(self, *a, **kw):
        calls.append(1)
        request = real(self, *a, **kw)
        if len(calls) == 1:
            raise TimeoutError("no response")
        return request

    monkeypatch.setattr(traces.TraceService, "open", lost_confirmation)
    r = orch.handle_message(tok, "sí")
    assert r.policy_rule == "action:trace_opened" and len(lines("TRACE_REQUESTS_PATH")) == 1


def test_a_tracing_service_that_stays_down_is_tried_a_bounded_number_of_times_and_nothing_is_announced(monkeypatch):
    orch, tok = pending_trace_turn()
    calls = []

    def down(self, *a, **kw):
        calls.append(1)
        raise OSError("connection refused")

    monkeypatch.setattr(traces.TraceService, "open", down)
    r = orch.handle_message(tok, "sí")
    assert r.policy_rule == "action:trace_unverified" and r.ticket_id
    assert len(calls) == traces.TRACE_RETRY.max_attempts == 3 and lines("TRACE_REQUESTS_PATH") == []
    assert not r.response_text.startswith(render.MSG["trace_opened"]["es"][:20])
    step = next(s for s in lines("TRACE_LOG_PATH")[-1]["stages"] if s["stage"] == "trace_service")
    assert step["attempts"] == 3 and step["outcome"] == "TraceServiceUnavailable"


# --- the ticket queue fails: the handoff itself --------------------------------------------------------------------

class WriteThenFail:
    """An `open` whose first write reaches the file and then reports an error, like a flush that failed after the bytes landed."""

    def __init__(self, real):
        self.real, self.opened = real, 0

    def __call__(self, path, mode="r", *a, **kw):
        self.opened += 1
        f = self.real(path, mode, *a, **kw)
        if self.opened != 1 or "a" not in mode:
            return f
        outer = self

        class Proxy:
            def __enter__(self_):
                return self_

            def __exit__(self_, *exc):
                f.close()
                return False

            def write(self_, data):
                f.write(data)
                f.flush()
                raise OSError("write reported failure after it landed")

        return Proxy()


def test_a_ticket_write_that_landed_but_reported_failure_is_not_filed_twice(monkeypatch):
    orch, tok = orchestrator(FakeLLMClient([]))
    monkeypatch.setattr(escalation, "open", WriteThenFail(open), raising=False)
    r = orch.handle_message(tok, "Me clonaron la tarjeta")
    assert (r.disposition, r.category) == ("ESCALATE", "theft") and r.ticket_id
    assert [t["ticket_id"] for t in lines("HUMAN_QUEUE_PATH")] == [r.ticket_id]  # one ticket, though the write was attempted twice
    assert r.response_text == render.MSG["escalate"]["es"]


def test_a_queue_that_cannot_be_written_says_so_with_a_code_and_never_claims_a_transfer(monkeypatch):
    attempts = []

    def broken(path, mode="r", *a, **kw):
        if "a" in mode:
            attempts.append(1)
            raise PermissionError("read-only disk")
        return open(path, mode, *a, **kw)

    monkeypatch.setattr(escalation, "open", broken, raising=False)
    orch, tok = orchestrator(FakeLLMClient([]))
    r = orch.handle_message(tok, "Me clonaron la tarjeta")
    assert r.ticket_id is None and r.policy_rule.endswith("|handoff_unverified")
    assert r.response_text == render.MSG["escalate_unverified"]["es"].format(code=r.trace_id[:8])
    assert len(attempts) == escalation.ENQUEUE_RETRY.max_attempts == 3


# --- our own code fails ---------------------------------------------------------------------------------------------

def test_an_unexpected_failure_inside_a_turn_is_a_handoff_and_leaks_nothing(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("secret account 5000000001 in the message")

    monkeypatch.setattr(orch_mod.router, "pre_llm", boom)
    orch, tok = orchestrator(FakeLLMClient([]))
    r = orch.handle_message(tok, "¿saldo?")
    assert_handed_over(r, "internal_error", "internal_error:RuntimeError")
    record = lines("TRACE_LOG_PATH")[-1]
    assert record["error_type"] == "RuntimeError" and "5000000001" not in json.dumps(record)
    assert "5000000001" not in json.dumps(lines("HUMAN_QUEUE_PATH")[-1]["reason"])


def test_an_unexpected_failure_with_the_queue_also_down_still_answers_with_a_code(monkeypatch):
    monkeypatch.setattr(orch_mod.router, "pre_llm", lambda *a, **kw: 1 / 0)
    monkeypatch.setattr(escalation.default_queue, "enqueue", lambda ticket: (_ for _ in ()).throw(OSError("down")))
    orch, tok = orchestrator(FakeLLMClient([]))
    r = orch.handle_message(tok, "¿saldo?")
    assert r.ticket_id is None and r.response_text == render.MSG["escalate_unverified"]["es"].format(code=r.trace_id[:8])


def test_the_state_store_failing_to_save_never_loses_the_reply(monkeypatch):
    orch, tok = orchestrator(FakeLLMClient([]))
    monkeypatch.setattr(orch.conversations, "save", lambda key: (_ for _ in ()).throw(OSError("disk full")))
    r = orch.handle_message(tok, "Me clonaron la tarjeta")
    assert r.disposition == "ESCALATE" and r.ticket_id


def test_the_audit_and_trace_logs_share_the_turns_id_even_when_it_fails(monkeypatch):
    monkeypatch.setattr(orch_mod.router, "pre_llm", lambda *a, **kw: 1 / 0)
    orch, tok = orchestrator(FakeLLMClient([]))
    r = orch.handle_message(tok, "¿saldo?")
    assert lines("TRACE_LOG_PATH")[-1]["trace_id"] == r.trace_id
    assert audit.current_trace_id.get() is None  # the id does not leak into the next request on this thread
