"""The retention purge and every writer of a JSONL file take the same cross-process lock, so a record confirmed to its writer is
never dropped by a purge swapping the file in (agent/filelock.py)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from agent import filelock
from agent.policy import router
from agent.policy.desk import default_desk
from agent.policy.escalation import escalate
from agent.tools.audit import AuditLog, TraceLog
from agent.tools.traces import default_traces
from api import main as _api  # noqa: F401 - importing the API is what puts the ticket queue and the desk under the lock
from ops import retention

ROOT = Path(__file__).resolve().parent.parent
OLD = b'"old": true'


def _trace():
    TraceLog().write({"trace_id": "late", "ts": time.time()})


def _audit():
    AuditLog().event("late_event")


def _ticket():
    escalate(router.foreign_reference(["PRD-FIX0006"]), "CLI-FIX0001", "ref", "hola", "es", [], [], [], {}, None)


def _desk_event():
    default_desk._record("T-late", "claim", "claimed", "ana")


def _trace_request():
    default_traces.open("CLI-FIX0001", "TXN-LATE", "PRD-FIX0001", "ref")


WRITERS = [("TRACE_LOG_PATH", _trace), ("AUDIT_LOG_PATH", _audit), ("HUMAN_QUEUE_PATH", _ticket),
           ("HUMAN_DESK_PATH", _desk_event), ("TRACE_REQUESTS_PATH", _trace_request)]


@pytest.mark.parametrize("env,write", WRITERS, ids=[e for e, _ in WRITERS])
def test_a_record_written_at_the_moment_the_purge_swaps_the_file_in_is_not_lost(env, write, tmp_path, monkeypatch):
    """The window between the purge's last read of the file and os.replace: a writer that finishes there must not be overwritten."""
    path = tmp_path / "records.jsonl"
    monkeypatch.setenv(env, str(path))
    ids = '"trace_id": "x", "customer_id": "C", "transaction_id": "T", "ticket_id": "T-x"'  # what the stores read from a line
    path.write_text('{"old": true, "ts": 1, %s}\n{"keep": true, "ts": 2, %s}\n' % (ids, ids))
    writers = []
    real_replace = os.replace

    def a_write_lands_just_before_the_swap(src, dst):
        thread = threading.Thread(target=write)
        thread.start()
        thread.join(timeout=0.5)  # a writer that takes the lock is held here until the swap is done; one that does not, finishes
        writers.append(thread)
        real_replace(src, dst)

    monkeypatch.setattr(retention.os, "replace", a_write_lands_just_before_the_swap)
    kept, dropped = retention._rewrite_jsonl(path, lambda line: OLD in line, dry_run=False)
    monkeypatch.setattr(retention.os, "replace", real_replace)
    writers[0].join(timeout=10)
    assert not writers[0].is_alive() and dropped == 1
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(lines) == 2 and lines[0]["keep"] is True and not any(line.get("old") for line in lines), lines  # old gone, late write there


def test_the_lock_excludes_other_processes(tmp_path):
    """A second process cannot take the lock while this one holds it, and gets it the moment it is released."""
    path = tmp_path / "x.jsonl"
    probe = ("import sys, time; from agent.filelock import locked\n"
             "t = time.time()\n"
             "with locked(sys.argv[1]): print(round(time.time() - t, 2))\n")
    with filelock.locked(path):
        proc = subprocess.Popen([sys.executable, "-c", probe, str(path)], cwd=ROOT, stdout=subprocess.PIPE, text=True,
                                env={**os.environ, "PYTHONPATH": str(ROOT)})
        time.sleep(1.0)
        assert proc.poll() is None  # still waiting
    assert proc.wait(timeout=10) == 0 and float(proc.stdout.read()) >= 0.9


def test_purges_racing_a_writer_in_another_process_lose_nothing(tmp_path):
    path = tmp_path / "traces.jsonl"
    writer = ("import json, os, sys, time\n"
              "from agent.tools.audit import TraceLog\n"
              "log = TraceLog()\n"
              "for i in range(int(sys.argv[1])): log.write({'trace_id': f'w{i}', 'ts': time.time()})\n")
    n = 1500
    env = {**os.environ, "PYTHONPATH": str(ROOT), "TRACE_LOG_PATH": str(path)}
    proc = subprocess.Popen([sys.executable, "-c", writer, str(n)], cwd=ROOT, env=env)
    rewrites = 0
    while proc.poll() is None:
        filelock.append_line(path, json.dumps({"old": True, "ts": 1}))  # something always expired, so every pass rewrites
        rewrites += retention._rewrite_jsonl(path, lambda line: OLD in line, dry_run=False)[1] > 0
    assert proc.wait() == 0 and rewrites > 5
    retention._rewrite_jsonl(path, lambda line: OLD in line, dry_run=False)
    ids = [json.loads(line)["trace_id"] for line in path.read_text().splitlines()]
    assert sorted(ids, key=lambda s: int(s[1:])) == [f"w{i}" for i in range(n)]  # every record, once, in order


# Not edited (eval/fingerprint.py hashes agent/policy/): filelock.serialize_policy_writers wraps their write methods instead
WRAPPED_FROM_OUTSIDE = {"agent/policy/escalation.py", "agent/policy/desk.py"}


def test_the_ticket_queue_and_the_desk_are_wrapped_when_the_api_starts_and_only_once():
    from agent.policy.desk import TicketDesk
    from agent.policy.escalation import HumanQueue

    filelock.serialize_policy_writers()
    filelock.serialize_policy_writers()
    for method in (HumanQueue.enqueue, TicketDesk._record):
        assert method.__wrapped_by_filelock__ and not getattr(method.__wrapped__, "__wrapped_by_filelock__", False)


def test_no_writer_appends_to_a_pruned_file_without_the_lock():
    """A guard for the next writer: every append-mode open under agent/ is inside a `locked(...)` block or goes through append_line."""
    offenders = []
    for path in (ROOT / "agent").rglob("*.py"):
        if path.name == "filelock.py":
            continue
        if path.relative_to(ROOT).as_posix() in WRAPPED_FROM_OUTSIDE:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if re.search(r'open\([^)]*"a"', line) and not re.search(r"locked\(", " ".join(lines[max(0, i - 1):i + 1])):
                offenders.append(f"{path.relative_to(ROOT)}:{i + 1}")
    assert not offenders, offenders
