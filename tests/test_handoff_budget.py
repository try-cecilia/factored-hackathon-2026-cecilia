"""The handoff has a budget that covers all of it: the evidence, the lock, the write and the read-back. Past it nothing is
written, and the customer gets the message that says nothing was registered, with a code."""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

from agent.core import render
from agent.core.orchestrator import Orchestrator
from agent.filelock import locked
from agent.llm.client import LLMClient
from agent.policy import escalation
from agent.resilience import handoff_budget_seconds, request_budget_seconds
from agent.session.auth import SessionStore
from agent.tools import account_tools
from eval.fake_llm import FakeLLMClient


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var in ("TRACE_REQUESTS_PATH", "HUMAN_QUEUE_PATH", "AUDIT_LOG_PATH", "TRACE_LOG_PATH"):
        monkeypatch.setenv(var, str(tmp_path / f"{var}.jsonl"))


def tickets() -> list[dict]:
    path = os.environ["HUMAN_QUEUE_PATH"]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def orchestrator(llm=None, customer="CLI-FIX0001"):
    from agent.policy import intent_guard

    intent_guard.read("hola")  # the classifier loads on first use (about 0.4 s): keep that out of the timings below
    llm = llm or FakeLLMClient([])
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: llm)
    return orch, orch.session_store.issue(customer, {"segment": "Premium", "country": "México", "customer_status": "Active"}).token


def hold_lock(seconds):
    """Another writer holds the ticket file's lock for `seconds`."""
    taken = threading.Event()

    def run():
        with locked(escalation.default_queue.path):
            taken.set()
            time.sleep(seconds)

    threading.Thread(target=run, daemon=True).start()
    taken.wait()


def test_a_held_lock_cannot_hold_the_handoff_past_its_budget_and_nothing_is_written_late(monkeypatch):
    monkeypatch.setenv("HANDOFF_BUDGET_SECONDS", "0.05")
    orch, tok = orchestrator()
    hold_lock(0.4)
    t0 = time.perf_counter()
    r = orch.handle_message(tok, "Me clonaron la tarjeta")
    assert time.perf_counter() - t0 < 0.25  # the budget was 50 ms; the lock was held for 400
    assert r.ticket_id is None and r.response_text == render.MSG["escalate_unverified"]["es"].format(code=r.trace_id[:8])
    time.sleep(0.5)  # the lock is free now: a write that was only postponed would land here
    assert tickets() == []


def test_the_evidence_is_skipped_when_the_budget_is_gone_and_no_ticket_is_written_after_it(monkeypatch):
    monkeypatch.setenv("HANDOFF_BUDGET_SECONDS", "0.04")
    real = account_tools.recent_activity_for_review

    def slow(*a, **kw):
        time.sleep(0.1)
        return real(*a, **kw)

    monkeypatch.setattr(account_tools, "recent_activity_for_review", slow)
    orch, tok = orchestrator()
    t0 = time.perf_counter()
    r = orch.handle_message(tok, "no reconozco un cargo en mi tarjeta")  # fraud: evidence is gathered
    assert time.perf_counter() - t0 < 0.3
    assert r.ticket_id is None and r.policy_rule.endswith("|handoff_unverified") and tickets() == []


def test_within_its_budget_the_handoff_is_filed_and_read_back(monkeypatch):
    monkeypatch.setenv("HANDOFF_BUDGET_SECONDS", "2")
    orch, tok = orchestrator()
    hold_lock(0.1)  # a short wait for the lock is fine
    r = orch.handle_message(tok, "Me clonaron la tarjeta")
    assert r.ticket_id and [t["ticket_id"] for t in tickets()] == [r.ticket_id]


def test_a_turn_is_bounded_by_the_turn_budget_plus_the_handoff_budget(monkeypatch):
    """The whole request: the model runs out the turn's 0.2 s, then the handoff meets a lock held for a second."""
    monkeypatch.setenv("TURN_BUDGET_SECONDS", "0.2")
    monkeypatch.setenv("HANDOFF_BUDGET_SECONDS", "0.1")
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Stall(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            time.sleep(1.0)  # a model that does not answer inside the turn

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stall)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LLM_PROVIDERS", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}/v1")
    client = LLMClient(sleep=lambda s: None, timeout_s=5)
    orch, tok = orchestrator(client)
    hold_lock(1.0)
    assert request_budget_seconds() == pytest.approx(0.3)
    t0 = time.perf_counter()
    r = orch.handle_message(tok, "movimientos de mi tarjeta")
    assert time.perf_counter() - t0 < 0.3 + 0.2  # 0.2 turn + 0.1 handoff, and a margin for the work in between
    assert r.disposition == "ESCALATE" and r.ticket_id is None
    server.shutdown()


def test_the_budgets_are_readable_from_the_environment(monkeypatch):
    monkeypatch.delenv("HANDOFF_BUDGET_SECONDS", raising=False)
    monkeypatch.setenv("TURN_BUDGET_SECONDS", "30")
    assert handoff_budget_seconds() == 3 and request_budget_seconds() == 33
