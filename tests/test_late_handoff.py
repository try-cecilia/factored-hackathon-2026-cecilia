"""A write that outlives the handoff's budget: the reply names no ticket it cannot confirm, and the late outcome is recorded.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from agent import observability
from agent.core import render
from agent.core.orchestrator import Orchestrator
from agent.llm.client import call_limit, deadline_transport
from agent.policy import escalation
from agent.session.auth import SessionStore
from agent.tools import account_tools
from eval.fake_llm import FakeLLMClient


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var in ("TRACE_REQUESTS_PATH", "HUMAN_QUEUE_PATH", "AUDIT_LOG_PATH", "TRACE_LOG_PATH"):
        monkeypatch.setenv(var, str(tmp_path / f"{var}.jsonl"))
    from agent.policy import intent_guard

    intent_guard.read("hola")


def tickets() -> list[dict]:
    path = os.environ["HUMAN_QUEUE_PATH"]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def orchestrator():
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: FakeLLMClient([]))
    return orch, orch.session_store.issue("CLI-FIX0001", {"segment": "Premium", "country": "México", "customer_status": "Active"}).token


def alive(name):
    return [t for t in threading.enumerate() if t.name == name]


def wait_until(check, seconds=3.0):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


# --- 1. a late write's outcome ---------------------------------------------------------------------------------------------

class SlowOpen:
    """`open` whose writes take `delay` seconds and then land, or fail, like a slow or failing disk."""

    def __init__(self, real, delay, fail=False):
        self.real, self.delay, self.fail = real, delay, fail

    def __call__(self, path, mode="r", *a, **kw):
        f = self.real(path, mode, *a, **kw)
        if "a" not in mode:
            return f
        delay, fail = self.delay, self.fail

        class Slow:
            def __enter__(self_):
                return self_

            def __exit__(self_, *exc):
                f.close()
                return False

            def write(self_, data):
                time.sleep(delay)
                if fail:
                    raise OSError("disk full after a slow write")
                f.write(data)
                f.flush()

        return Slow()


def late_counts():
    c = observability.failure_counts()
    return c.get("handoff_late_landed", 0), c.get("handoff_late_failed", 0)


def test_a_slow_write_that_lands_is_never_named_in_the_reply_but_is_recorded_and_linked_by_the_trace_code(monkeypatch, caplog):
    monkeypatch.setenv("HANDOFF_BUDGET_SECONDS", "0.05")
    monkeypatch.setattr(escalation, "open", SlowOpen(open, 0.2), raising=False)
    landed, failed = late_counts()
    orch, tok = orchestrator()
    with caplog.at_level(logging.INFO):
        r = orch.handle_message(tok, "Me clonaron la tarjeta")
        assert r.ticket_id is None and r.policy_rule.endswith("|handoff_unverified")  # only a confirmed ticket is named
        assert r.response_text == render.MSG["escalate_unverified"]["es"].format(code=r.trace_id[:8])  # the code to quote
        assert wait_until(lambda: late_counts() == (landed + 1, failed))
    (ticket,) = tickets()
    assert ticket["trace_id"] == r.trace_id  # the person who is quoted the code finds it
    late = [rec for rec in caplog.records if getattr(rec, "fields", {}).get("kind") == "handoff_late_landed"]
    assert late and late[0].fields["trace_id"] == r.trace_id and late[0].fields["ticket_id"] == ticket["ticket_id"]


def test_a_slow_write_that_then_fails_leaves_no_reference_and_is_recorded_by_type(monkeypatch, caplog):
    monkeypatch.setenv("HANDOFF_BUDGET_SECONDS", "0.05")
    monkeypatch.setattr(escalation, "open", SlowOpen(open, 0.2, fail=True), raising=False)
    landed, failed = late_counts()
    orch, tok = orchestrator()
    with caplog.at_level(logging.INFO):
        r = orch.handle_message(tok, "Me clonaron la tarjeta")
        assert r.ticket_id is None and r.policy_rule.endswith("|handoff_unverified")
        assert wait_until(lambda: late_counts() == (landed, failed + 1))
    assert tickets() == []  # nothing dangling: no ticket, and the reply never named one
    fields = [rec.fields for rec in caplog.records if getattr(rec, "fields", {}).get("kind") == "handoff_late_failed"]
    assert fields and fields[0]["trace_id"] == r.trace_id and fields[0]["error_type"] == "OSError"
    assert "disk full" not in caplog.text  # the type, never the message


def test_a_ticket_written_in_time_but_read_back_late_is_not_named_either(monkeypatch):
    monkeypatch.setenv("HANDOFF_BUDGET_SECONDS", "0.05")
    real = escalation.HumanQueue.get
    monkeypatch.setattr(escalation.HumanQueue, "get", lambda self, ticket_id: (time.sleep(0.2), real(self, ticket_id))[1])
    orch, tok = orchestrator()
    r = orch.handle_message(tok, "Me clonaron la tarjeta")
    assert r.ticket_id is None and r.policy_rule.endswith("|handoff_unverified") and tickets()[0]["trace_id"] == r.trace_id


