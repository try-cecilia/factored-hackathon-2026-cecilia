"""The turn's time budget limits the turn: no attempt, lookup or action starts after it, a slow call cannot outlast it,
and the handoff has a budget of its own so it can always be written."""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent.core import orchestrator as orch_mod
from agent.core.orchestrator import Orchestrator
from agent.llm.client import LLMClient, LLMUnavailable
from agent.policy import escalation
from agent.session.auth import SessionStore
from eval.fake_llm import FakeLLMClient, tool_call_response


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_REQUESTS_PATH", str(tmp_path / "trace_requests.jsonl"))
    monkeypatch.setenv("HUMAN_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("TRACE_LOG_PATH", str(tmp_path / "traces.jsonl"))


def lines(env: str) -> list[dict]:
    path = os.environ[env]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def orchestrator(llm, customer="CLI-FIX0001"):
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: llm)
    tok = orch.session_store.issue(customer, {"segment": "Premium", "country": "México", "customer_status": "Active"}).token
    return orch, tok


def test_a_confirmation_that_arrives_with_the_budget_spent_opens_nothing_and_hands_the_proposal_to_a_person(monkeypatch):
    orch, tok = orchestrator(FakeLLMClient([tool_call_response("request_trace", {})]), customer="CLI-FIX0004")
    orch.handle_message(tok, "hice una transferencia que todavía no llega")  # proposes the trace
    monkeypatch.setenv("TURN_BUDGET_SECONDS", "1e-9")
    r = orch.handle_message(tok, "sí")
    assert r.policy_rule != "action:trace_opened" and (r.disposition, r.category) == ("ESCALATE", "turn_timeout") and r.ticket_id
    assert lines("TRACE_REQUESTS_PATH") == []  # nothing was opened
    ticket = lines("HUMAN_QUEUE_PATH")[-1]
    assert ticket["pending_action"]["transaction_id"] == "TXN-FIX0006" and ticket["pending_action"]["tool"] == "request_trace"
    assert "abr" not in r.response_text.lower().split("agente")[0]  # the reply never says it was opened


def test_a_tool_that_finishes_after_the_budget_is_not_an_answer(monkeypatch):
    real = orch_mod.TOOL_FUNCTIONS["get_account_summary"]

    def slow(customer_id, **kw):
        time.sleep(0.08)
        return real(customer_id, **kw)

    monkeypatch.setitem(orch_mod.TOOL_FUNCTIONS, "get_account_summary", slow)
    monkeypatch.setenv("TURN_BUDGET_SECONDS", "0.04")
    orch, tok = orchestrator(FakeLLMClient([tool_call_response("get_account_summary", {"product_id": "PRD-FIX0001"})]))
    r = orch.handle_message(tok, "¿saldo de mi ahorro 0001?")
    assert (r.disposition, r.category) == ("ESCALATE", "turn_timeout") and r.verified_facts == [] and r.ticket_id


class Dribble(BaseHTTPRequestHandler):
    """A chunked answer that keeps sending a piece every 0.1 s for 0.45 s: every read is in time, the whole is not."""

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        body = json.dumps({"model": "m", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        step = max(1, len(body) // 5)
        for i in range(0, len(body), step):
            piece = body[i:i + step]
            self.wfile.write(f"{len(piece):x}\r\n".encode() + piece + b"\r\n")
            self.wfile.flush()
            time.sleep(0.1)
        self.wfile.write(b"0\r\n\r\n")

    def log_message(self, *a):
        pass


def test_a_server_that_dribbles_its_answer_cannot_outlast_the_models_total_budget(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Dribble)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LLM_PROVIDERS", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}/v1")
    try:
        t0 = time.perf_counter()
        with pytest.raises(LLMUnavailable) as e:
            LLMClient(sleep=lambda s: None, timeout_s=5, total_budget_s=0.15, max_attempts_per_provider=2).chat(
                [{"role": "user", "content": "hi"}])
        assert time.perf_counter() - t0 < 0.3  # the 0.45 s answer never got to finish
        assert any("timeout" in a.get("error", "").lower() for a in e.value.attempts)
    finally:
        server.shutdown()
        server.server_close()


def test_the_time_spent_building_the_client_counts_against_the_models_total_budget(monkeypatch):
    # Building the client (an SDK import, a TLS context, a garbage-collector pause) happens inside the total budget: the call that
    # follows gets only what is left of it, never a full request timeout on top of it.
    server = ThreadingHTTPServer(("127.0.0.1", 0), Dribble)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LLM_PROVIDERS", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}/v1")
    client = LLMClient(sleep=lambda s: None, timeout_s=5, total_budget_s=0.3, max_attempts_per_provider=1)
    build = client._client

    def slow_build(p, api_key):
        time.sleep(0.2)
        return build(p, api_key)

    monkeypatch.setattr(client, "_client", slow_build)
    try:
        t0 = time.perf_counter()
        with pytest.raises(LLMUnavailable) as e:
            client.chat([{"role": "user", "content": "hi"}])
        assert time.perf_counter() - t0 < 0.45  # 0.2 s building + what was left of 0.3 s; the full answer takes 0.2 + 0.5
        assert any("timeout" in a.get("error", "").lower() for a in e.value.attempts)
    finally:
        server.shutdown()
        server.server_close()


def test_the_handoff_has_a_budget_of_its_own_and_is_written_even_when_the_turn_is_out_of_time(monkeypatch):
    monkeypatch.setenv("TURN_BUDGET_SECONDS", "1e-9")
    real_open, opened = open, []

    def flaky(path, mode="r", *a, **kw):
        if "a" in mode:
            opened.append(1)
            if len(opened) == 1:
                raise OSError("busy")
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr(escalation, "open", flaky, raising=False)
    orch, tok = orchestrator(FakeLLMClient([]))
    r = orch.handle_message(tok, "Me clonaron la tarjeta")
    assert r.ticket_id and len(opened) == 2 and [t["ticket_id"] for t in lines("HUMAN_QUEUE_PATH")] == [r.ticket_id]


# --- the degraded path obeys the same clock -------------------------------------------------------------------------

def audited_lookups(trace_id: str) -> list[dict]:
    return [a for a in lines("AUDIT_LOG_PATH") if a.get("trace_id") == trace_id and a.get("tool_name") == "get_account_summary"]


def test_with_the_model_down_and_the_budget_spent_a_plain_balance_question_is_not_looked_up_or_answered(monkeypatch):
    monkeypatch.setenv("TURN_BUDGET_SECONDS", "1e-9")
    orch, tok = orchestrator(FakeLLMClient([]))  # never reached: the budget is gone before the model
    from agent.llm.client import LLMUnavailable

    orch._llm = lambda: type("Down", (), {"chat": lambda self, *a, **k: (_ for _ in ()).throw(LLMUnavailable("down", []))})()
    r = orch.handle_message(tok, "cual es mi saldo")
    assert r.disposition == "ESCALATE" and r.policy_rule != "degraded:deterministic_balance" and r.ticket_id
    assert audited_lookups(r.trace_id) == [] and r.verified_facts == []


def test_a_degraded_lookup_that_finishes_after_the_budget_is_not_used(monkeypatch):
    from agent.llm.client import LLMUnavailable

    real = orch_mod.TOOL_FUNCTIONS["get_account_summary"]

    def slow(customer_id, **kw):
        time.sleep(0.12)
        return real(customer_id, **kw)

    monkeypatch.setitem(orch_mod.TOOL_FUNCTIONS, "get_account_summary", slow)
    monkeypatch.setenv("TURN_BUDGET_SECONDS", "0.1")
    orch, tok = orchestrator(FakeLLMClient([]))
    orch._llm = lambda: type("Down", (), {"chat": lambda self, *a, **k: (_ for _ in ()).throw(LLMUnavailable("down", []))})()
    from agent.policy import intent_guard

    intent_guard.read("hola")  # keep the classifier's first load out of the budget
    r = orch.handle_message(tok, "cual es mi saldo")
    assert r.disposition == "ESCALATE" and r.verified_facts == [] and "2,455.81" not in r.response_text and r.ticket_id


def test_within_its_budget_the_degraded_balance_is_still_answered():
    from agent.llm.client import LLMUnavailable

    orch, tok = orchestrator(FakeLLMClient([]))
    orch._llm = lambda: type("Down", (), {"chat": lambda self, *a, **k: (_ for _ in ()).throw(LLMUnavailable("down", []))})()
    assert orch.handle_message(tok, "cual es mi saldo").policy_rule == "degraded:deterministic_balance"
