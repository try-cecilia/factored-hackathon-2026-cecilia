"""The ticket write takes the lock between processes (agent/filelock.py) inside the handoff's budget: a flock held by another
process cannot hang a turn, and the ticket queue no longer sits behind the unbounded wrapper."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from agent.core import render
from agent.core.orchestrator import Orchestrator
from agent.filelock import locked, serialize_policy_writers
from agent.policy import escalation
from agent.policy.desk import TicketDesk
from agent.session.auth import SessionStore
from eval.fake_llm import FakeLLMClient

HOLD = "import fcntl,os,sys,time; fd=os.open(sys.argv[1]+'.lock', os.O_RDWR|os.O_CREAT, 0o600); fcntl.flock(fd, fcntl.LOCK_EX); print('held', flush=True); time.sleep(float(sys.argv[2]))"


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var in ("TRACE_REQUESTS_PATH", "HUMAN_QUEUE_PATH", "AUDIT_LOG_PATH", "TRACE_LOG_PATH"):
        monkeypatch.setenv(var, str(tmp_path / f"{var}.jsonl"))


def other_process_holds(path, seconds):
    proc = subprocess.Popen([sys.executable, "-c", HOLD, str(path), str(seconds)], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"
    return proc


def tickets() -> list[dict]:
    path = os.environ["HUMAN_QUEUE_PATH"]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def test_locked_gives_up_after_its_timeout_when_another_process_holds_the_lock(tmp_path):
    proc = other_process_holds(tmp_path / "f.jsonl", 2)
    try:
        t0 = time.perf_counter()
        with pytest.raises(TimeoutError):
            with locked(tmp_path / "f.jsonl", timeout=0.1):
                pytest.fail("took a lock another process holds")
        assert 0.08 < time.perf_counter() - t0 < 0.35
    finally:
        proc.kill()
    with locked(tmp_path / "f.jsonl", timeout=0.5):  # the holder died: the kernel released it
        pass


def test_locked_with_a_timeout_takes_a_free_lock_at_once_and_zero_means_try_once(tmp_path):
    with locked(tmp_path / "g.jsonl", timeout=1):
        pass
    proc = other_process_holds(tmp_path / "g.jsonl", 2)
    try:
        t0 = time.perf_counter()
        with pytest.raises(TimeoutError), locked(tmp_path / "g.jsonl", timeout=0):
            pass
        assert time.perf_counter() - t0 < 0.1
    finally:
        proc.kill()


def test_a_flock_held_by_another_process_cannot_hang_a_turn_and_no_ticket_lands_late(monkeypatch):
    from agent.policy import intent_guard

    intent_guard.read("hola")  # the classifier's first load is not what is timed
    monkeypatch.setenv("HANDOFF_BUDGET_SECONDS", "0.1")
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: FakeLLMClient([]))
    tok = orch.session_store.issue("CLI-FIX0001", {"segment": "Premium", "country": "México", "customer_status": "Active"}).token
    proc = other_process_holds(escalation.default_queue.path, 1.0)
    try:
        t0 = time.perf_counter()
        r = orch.handle_message(tok, "Me clonaron la tarjeta")
        assert time.perf_counter() - t0 < 0.4  # the lock is held for a second; the handoff's budget is 0.1 s
        assert r.ticket_id is None and r.response_text == render.MSG["escalate_unverified"]["es"].format(code=r.trace_id[:8])
    finally:
        proc.kill()
        proc.wait()
    time.sleep(0.3)
    assert tickets() == []  # nothing was written after the customer was told it was not


def test_the_ticket_queue_is_not_behind_the_unbounded_wrapper_but_the_desk_still_is():
    serialize_policy_writers()
    assert not getattr(escalation.HumanQueue.enqueue, "__wrapped_by_filelock__", False)
    assert getattr(TicketDesk._record, "__wrapped_by_filelock__", False)


def test_a_ticket_is_still_written_under_the_lock_and_two_writers_do_not_interleave(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from agent.policy.router import Decision, Disposition

    d = Decision(Disposition.ESCALATE, "x", "llm_unavailable", rule="llm_unavailable")

    def file(i):
        return escalation.escalate(d, "CLI-FIX0001", "ref", f"req {i}" + " x" * 300, "es", [], [], [], {}, "t" * 32).ticket_id

    with ThreadPoolExecutor(8) as ex:
        ids = list(ex.map(file, range(40)))
    assert sorted(t["ticket_id"] for t in tickets()) == sorted(ids)  # 40 whole lines, none torn
