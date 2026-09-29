"""Retention (ops/retention.py): what expired goes, what is current stays, a second run changes nothing, and the purge
leaves its own audit record."""
from __future__ import annotations

import json
import os
import time

import pytest

from agent.tools import state
from ops import retention

NOW = time.time()
DAY = 86400

# (data type, env var for its path, timestamp field, retention env var, days by default)
JSONL_STORES = [
    ("traces", "TRACE_LOG_PATH", "ts", "RETENTION_TRACES_DAYS", 30),
    ("audit", "AUDIT_LOG_PATH", "started_at", "RETENTION_AUDIT_DAYS", 30),
    ("shadow_log", "SHADOW_LOG_PATH", "ts", "RETENTION_SHADOW_DAYS", 30),
    ("tickets", "HUMAN_QUEUE_PATH", "created_at", "RETENTION_TICKETS_DAYS", 90),
    ("trace_requests", "TRACE_REQUESTS_PATH", "created_at", "RETENTION_TRACE_REQUESTS_DAYS", 90),
]


@pytest.fixture
def disk(tmp_path, monkeypatch):
    """Every store under one temporary directory, as on the persistent disk."""
    paths = {
        "TRACE_LOG_PATH": "traces.jsonl", "AUDIT_LOG_PATH": "audit_log.jsonl", "SHADOW_LOG_PATH": "shadow_log.jsonl",
        "HUMAN_QUEUE_PATH": "human_queue.jsonl", "HUMAN_DESK_PATH": "ticket_events.jsonl",
        "TRACE_REQUESTS_PATH": "trace_requests.jsonl", "STATE_DB_PATH": "state.sqlite",
        "RETENTION_STATUS_PATH": "retention_status.json",
    }
    for env, name in paths.items():
        monkeypatch.setenv(env, str(tmp_path / name))
    for var in [s[3] for s in JSONL_STORES] + ["RETENTION_CONVERSATIONS_DAYS", "RETENTION_TICKET_EVENTS_DAYS"]:
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def outcome(outcomes, name):
    return next(o for o in outcomes if o.name == name)


@pytest.mark.parametrize("name,env,field,_days_env,days", JSONL_STORES)
def test_expired_records_go_and_current_ones_stay(disk, name, env, field, _days_env, days):
    path = disk / os.path.basename(os.environ[env])
    write_jsonl(path, [{"id": "old", field: NOW - (days + 1) * DAY}, {"id": "edge", field: NOW - (days - 1) * DAY},
                       {"id": "new", field: NOW - 60}])
    got = outcome(retention.run(now=NOW), name)
    assert (got.kept, got.dropped) == (2, 1)
    assert [r["id"] for r in read_jsonl(path) if "id" in r] == ["edge", "new"]  # the audit log also holds the purge's own event


@pytest.mark.parametrize("name,env,field,_days_env,days", JSONL_STORES)
def test_second_run_drops_and_rewrites_nothing(disk, name, env, field, _days_env, days):
    path = disk / os.path.basename(os.environ[env])
    write_jsonl(path, [{"id": "old", field: NOW - (days + 1) * DAY}, {"id": "new", field: NOW - 60}])
    retention.run(now=NOW)
    before = path.stat().st_ino, [r for r in read_jsonl(path) if "id" in r]
    got = outcome(retention.run(now=NOW), name)
    assert got.dropped == 0
    assert (path.stat().st_ino, [r for r in read_jsonl(path) if "id" in r]) == before  # not rewritten (a new inode)


def test_period_comes_from_the_environment_and_zero_keeps_forever(disk, monkeypatch):
    path = disk / "traces.jsonl"
    write_jsonl(path, [{"id": "a", "ts": NOW - 10 * DAY}, {"id": "b", "ts": NOW - 400 * DAY}])
    monkeypatch.setenv("RETENTION_TRACES_DAYS", "7")
    assert outcome(retention.run(now=NOW), "traces").dropped == 2
    write_jsonl(path, [{"id": "a", "ts": NOW - 400 * DAY}])
    monkeypatch.setenv("RETENTION_TRACES_DAYS", "0")
    assert outcome(retention.run(now=NOW), "traces").dropped == 0
    assert len(read_jsonl(path)) == 1


def test_a_line_it_cannot_read_is_kept(disk):
    path = disk / "traces.jsonl"
    path.write_text('{"id": "old", "ts": 1}\nnot json at all\n{"id": "no-ts"}\n{"id": "bad-ts", "ts": "yesterday"}\n', encoding="utf-8")
    got = outcome(retention.run(now=NOW), "traces")
    assert got.dropped == 1
    assert path.read_text(encoding="utf-8").splitlines()[0] == "not json at all"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_a_missing_store_is_not_an_error(disk):
    outcomes = retention.run(now=NOW)
    assert all(o.dropped == 0 and not o.note.startswith("failed") for o in outcomes)


def test_lines_appended_while_it_rewrites_are_carried_over(disk):
    path = disk / "traces.jsonl"
    write_jsonl(path, [{"id": "old", "ts": 1}, {"id": "new", "ts": NOW}])
    calls = []

    def expired(line):
        if not calls:  # a writer appends between reading the file and swapping the rewrite in
            with open(path, "ab") as f:
                f.write(b'{"id": "late", "ts": %d}\n' % NOW)
        calls.append(line)
        return json.loads(line)["id"] == "old"

    assert retention._rewrite_jsonl(path, expired, dry_run=False) == (1, 1)
    assert [r["id"] for r in read_jsonl(path)] == ["new", "late"]


def test_dry_run_counts_but_changes_and_records_nothing(disk):
    path = disk / "traces.jsonl"
    write_jsonl(path, [{"id": "old", "ts": 1}, {"id": "new", "ts": NOW}])
    before = path.read_bytes()
    assert outcome(retention.run(now=NOW, dry_run=True), "traces").dropped == 1
    assert path.read_bytes() == before
    assert not (disk / "audit_log.jsonl").exists() and not (disk / "retention_status.json").exists()


def test_the_purge_records_itself_in_the_audit_log_and_the_status_file(disk):
    write_jsonl(disk / "traces.jsonl", [{"id": "old", "ts": 1}, {"id": "new", "ts": NOW}])
    write_jsonl(disk / "audit_log.jsonl", [{"call_id": "old", "started_at": 1}])
    before = time.time()
    retention.run(now=NOW)
    events = [r for r in read_jsonl(disk / "audit_log.jsonl") if r.get("event") == "retention_purge"]
    assert len(events) == 1  # the audit line that was old went; the purge's own record is current and stays
    assert events[0]["dropped"] == {"traces": 1, "audit": 1}
    assert events[0]["failed"] == [] and events[0]["started_at"] >= before
    assert "customer_id" not in json.dumps(events[0])
    status = json.loads((disk / "retention_status.json").read_text(encoding="utf-8"))
    assert status["last_run"] == NOW and status["failed"] == []
    # and the next purge, a day on, still finds it (30 days keep it) and adds its own
    retention.run(now=NOW + DAY)
    assert len([r for r in read_jsonl(disk / "audit_log.jsonl") if r.get("event") == "retention_purge"]) == 2


def test_a_ticket_keeps_all_its_events_until_it_has_left_the_queue_and_aged_out(disk):
    old, recent = NOW - 200 * DAY, NOW - 5 * DAY
    write_jsonl(disk / "human_queue.jsonl", [{"ticket_id": "T-live", "created_at": old},
                                             {"ticket_id": "T-fresh", "created_at": recent}])
    write_jsonl(disk / "ticket_events.jsonl", [
        {"ticket_id": "T-gone", "ts": old}, {"ticket_id": "T-gone", "ts": old + 1},           # left the queue, all old
        {"ticket_id": "T-active", "ts": old}, {"ticket_id": "T-active", "ts": recent},        # old claim, recent approve
        {"ticket_id": "T-live", "ts": old},                                                   # still in the queue: kept
        {"ticket_id": "T-orphan-new", "ts": recent},                                          # not in the queue but recent
    ])
    outcomes = retention.run(now=NOW)
    assert outcome(outcomes, "tickets").dropped == 1  # T-live is older than 90 days: it leaves the queue in this run...
    kept = {e["ticket_id"] for e in read_jsonl(disk / "ticket_events.jsonl")}
    # ...and its events, all old, go with it in the same run because the queue is read after it was pruned
    assert kept == {"T-active", "T-orphan-new"}
    assert outcome(outcomes, "ticket_events").dropped == 3
    assert outcome(retention.run(now=NOW), "ticket_events").dropped == 0


def test_ticket_events_are_kept_when_there_is_no_queue_to_compare_with(disk):
    write_jsonl(disk / "ticket_events.jsonl", [{"ticket_id": "T-1", "ts": 1}])
    got = outcome(retention.run(now=NOW), "ticket_events")
    assert got.dropped == 0 and "kept" in got.note


def test_sessions_conversations_and_case_notices_are_pruned(disk):
    conn = state.connect(str(disk / "state.sqlite"))
    conn.executemany("INSERT INTO sessions VALUES (?, 'C1', ?, ?, '{}')",
                     [("expired", NOW - 3600, NOW - 60), ("live", NOW - 60, NOW + 800)])
    conn.executemany("INSERT INTO conversations VALUES (?, '{}', ?)",
                     [("stale", NOW - 2 * DAY), ("fresh", NOW - 3600)])
    conn.executemany("INSERT INTO case_notifications VALUES (?, ?, 'claimed')", [("C1", "T-gone"), ("C1", "T-live")])
    conn.commit()
    conn.close()
    write_jsonl(disk / "human_queue.jsonl", [{"ticket_id": "T-live", "created_at": NOW - DAY}])

    outcomes = retention.run(now=NOW)
    assert [outcome(outcomes, n).dropped for n in ("sessions", "conversations", "case_notifications")] == [1, 1, 1]
    conn = state.connect(str(disk / "state.sqlite"))
    assert [r[0] for r in conn.execute("SELECT token_hash FROM sessions")] == ["live"]
    assert [r[0] for r in conn.execute("SELECT key FROM conversations")] == ["fresh"]
    assert [r[0] for r in conn.execute("SELECT ticket_id FROM case_notifications")] == ["T-live"]
    assert [outcome(retention.run(now=NOW), n).dropped for n in ("sessions", "conversations", "case_notifications")] == [0, 0, 0]


def test_without_a_state_database_there_is_nothing_to_prune(disk, monkeypatch):
    monkeypatch.delenv("STATE_DB_PATH")
    assert outcome(retention.run(now=NOW), "sessions").dropped == 0


def test_leftovers_of_a_killed_process_go_but_a_recent_one_stays(disk):
    old, recent = disk / "traces.jsonl.retention.tmp", disk / "bank.duckdb.building"
    for f in (old, recent):
        f.write_text("x")
    os.utime(old, (NOW - 3 * DAY, NOW - 3 * DAY))
    os.utime(recent, (NOW - 60, NOW - 60))
    assert outcome(retention.run(now=NOW), "stale_temp_files").dropped == 1
    assert not old.exists() and recent.exists()


def test_one_failing_store_does_not_stop_the_rest(disk, monkeypatch):
    write_jsonl(disk / "audit_log.jsonl", [{"call_id": "old", "started_at": 1}])
    real = retention._prune_jsonl

    def flaky(rule, now, dry_run):
        if rule.name == "traces":
            raise OSError("disk error")
        return real(rule, now, dry_run)

    monkeypatch.setattr(retention, "_prune_jsonl", flaky)
    outcomes = retention.run(now=NOW)
    assert outcome(outcomes, "traces").note.startswith("failed")
    assert outcome(outcomes, "audit").dropped == 1
    event = [r for r in read_jsonl(disk / "audit_log.jsonl") if r.get("event") == "retention_purge"][0]
    assert event["failed"] == ["traces"]


def test_the_loop_runs_every_interval_and_survives_a_failed_cycle(disk, monkeypatch):
    runs, sleeps = [], []

    def fake_run():
        runs.append(1)
        if len(runs) == 1:
            raise RuntimeError("boom")
        return []

    monkeypatch.setattr(retention, "run", fake_run)
    retention.loop(12, sleep=sleeps.append, cycles=3)
    assert len(runs) == 3 and sleeps == [12 * 3600, 12 * 3600]
