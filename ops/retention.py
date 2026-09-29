"""Retention for everything this service writes to disk (it contains customer data), one policy table for all of it.

    python -m ops.retention                 # apply the policy once
    python -m ops.retention --dry-run       # count what would go; delete nothing, record nothing
    python -m ops.retention --loop          # apply it now and then every RETENTION_INTERVAL_HOURS (the container does this)

What is kept for how long is `rules()` below and the table in docs/operations.md ("Data retention"); every period is
an environment variable (RETENTION_*_DAYS, 0 = keep forever), and the paths are the ones the writers use.
- Idempotent: a second run right after the first drops nothing and rewrites nothing.
- A JSONL file is rewritten only when something in it expired, aside and swapped in whole, so a reader never sees it
  half written. Lines appended while it was being rewritten are carried over. A writer that opened the file in the few
  microseconds before the swap could still lose that one line (LIMITATIONS.md); running it daily, the file is
  rewritten only when a day's worth of records has expired.
- A line that is not JSON, or has no usable timestamp, is kept: retention never destroys what it cannot read.
- A ticket's event log is dropped with its ticket, never event by event, or a ticket's state and version would change.
- Every run records itself: an `retention_purge` event in the audit log (counts only, no customer data) and a status
  file that /metrics reads, so a purge that stopped running is an alert (ops/alerts.yml).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger("retention")

DAY = 86400
STALE_TEMP_SECONDS = DAY  # a leftover of a killed rewrite or a killed ingestion (*.tmp, *.building)


@dataclass(frozen=True)
class Rule:
    name: str  # the data type, as the docs and the audit event name it
    kind: str  # jsonl | ticket_events | sessions | conversations | case_notifications | stale_files
    path: str
    days: float  # 0 = keep forever
    field: str = ""  # the record's timestamp, for jsonl


def _days(var: str, default: float) -> float:
    return float(os.environ.get(var) or default)


def _wh(env: str, default: str) -> str:
    return os.environ.get(env, f"data/warehouse/{default}")


def rules() -> list[Rule]:
    """The policy, read from the environment at call time. Order matters: tickets go before what hangs off them."""
    return [
        Rule("traces", "jsonl", _wh("TRACE_LOG_PATH", "traces.jsonl"), _days("RETENTION_TRACES_DAYS", 30), "ts"),
        Rule("audit", "jsonl", _wh("AUDIT_LOG_PATH", "audit_log.jsonl"), _days("RETENTION_AUDIT_DAYS", 30), "started_at"),
        Rule("shadow_log", "jsonl", _wh("SHADOW_LOG_PATH", "shadow_log.jsonl"), _days("RETENTION_SHADOW_DAYS", 30), "ts"),
        Rule("tickets", "jsonl", _wh("HUMAN_QUEUE_PATH", "human_queue.jsonl"), _days("RETENTION_TICKETS_DAYS", 90), "created_at"),
        Rule("ticket_events", "ticket_events", _wh("HUMAN_DESK_PATH", "ticket_events.jsonl"),
             _days("RETENTION_TICKET_EVENTS_DAYS", 90), "ts"),
        Rule("trace_requests", "jsonl", _wh("TRACE_REQUESTS_PATH", "trace_requests.jsonl"),
             _days("RETENTION_TRACE_REQUESTS_DAYS", 90), "created_at"),
        Rule("sessions", "sessions", os.environ.get("STATE_DB_PATH", ""), 0),  # expired ones go at once
        Rule("conversations", "conversations", os.environ.get("STATE_DB_PATH", ""), _days("RETENTION_CONVERSATIONS_DAYS", 1)),
        Rule("case_notifications", "case_notifications", os.environ.get("STATE_DB_PATH", ""), 0),  # follows the tickets
        Rule("stale_temp_files", "stale_files", str(Path(_wh("TRACE_LOG_PATH", "traces.jsonl")).parent), 0),
    ]


@dataclass
class Outcome:
    name: str
    kept: int = 0
    dropped: int = 0
    days: float = 0
    note: str = ""


def _split(data: bytes) -> tuple[list[bytes], bytes]:
    """Complete lines and the unfinished last one (a writer may be in the middle of it)."""
    head, newline, tail = data.rpartition(b"\n")
    return (head.split(b"\n") if newline else []), tail


def _timestamp(line: bytes, field_name: str):
    try:
        value = json.loads(line).get(field_name)
    except (ValueError, AttributeError):
        return None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _rewrite_jsonl(path: Path, expired: Callable[[bytes], bool], dry_run: bool) -> tuple[int, int]:
    """Drop the lines `expired` says so about. Returns (kept, dropped)."""
    if not path.exists():
        return 0, 0
    data = path.read_bytes()
    lines, tail = _split(data)
    lines = [line for line in lines if line.strip()]
    keep = [line for line in lines if not expired(line)]
    dropped = len(lines) - len(keep)
    if dropped == 0 or dry_run:
        return len(lines), dropped
    aside = path.with_name(path.name + ".retention.tmp")
    try:
        aside.write_bytes(b"".join(line + b"\n" for line in keep) + tail)
        with open(path, "rb") as f:  # whatever was appended while this was being worked out
            f.seek(len(data))
            appended = f.read()
        if appended:
            with open(aside, "ab") as f:
                f.write(appended)
        os.replace(aside, path)
    finally:
        aside.unlink(missing_ok=True)
    return len(keep), dropped


def _prune_jsonl(rule: Rule, now: float, dry_run: bool) -> Outcome:
    out = Outcome(rule.name, days=rule.days)
    if not rule.days:
        out.note = "kept forever"
        return out
    cutoff = now - rule.days * DAY
    out.kept, out.dropped = _rewrite_jsonl(
        Path(rule.path), lambda line: (ts := _timestamp(line, rule.field)) is not None and ts < cutoff, dry_run)
    return out


def _ticket_ids(path: Path) -> set[str] | None:
    """The ids of the tickets still in the queue, or None when there is no queue file to say."""
    if not path.exists():
        return None
    ids = set()
    for line in path.read_bytes().splitlines():
        try:
            ids.add(json.loads(line)["ticket_id"])
        except (ValueError, KeyError, TypeError):
            continue
    return ids


def _prune_ticket_events(rule: Rule, now: float, dry_run: bool, queue_path: str) -> Outcome:
    """A ticket's events are dropped together, once the ticket has left the queue and its last event has aged out."""
    out = Outcome(rule.name, days=rule.days)
    live = _ticket_ids(Path(queue_path))
    if not rule.days or live is None:
        out.note = "kept forever" if not rule.days else "no ticket queue to compare with: kept"
        return out
    cutoff = now - rule.days * DAY
    path = Path(rule.path)
    last_event: dict[str, float] = {}
    if path.exists():
        for line in path.read_bytes().splitlines():
            try:
                event = json.loads(line)
                last_event[event["ticket_id"]] = max(last_event.get(event["ticket_id"], 0.0), float(event["ts"]))
            except (ValueError, KeyError, TypeError):
                continue
    gone = {t for t, ts in last_event.items() if t not in live and ts < cutoff}

    def expired(line: bytes) -> bool:
        try:
            return json.loads(line).get("ticket_id") in gone
        except (ValueError, AttributeError):
            return False

    out.kept, out.dropped = _rewrite_jsonl(path, expired, dry_run)
    return out


def _prune_sqlite(rule: Rule, now: float, dry_run: bool, queue_path: str) -> Outcome:
    out = Outcome(rule.name, days=rule.days)
    if not rule.path or not Path(rule.path).exists():
        out.note = "STATE_DB_PATH not set or not created yet: nothing to prune"
        return out
    conn = sqlite3.connect(rule.path, timeout=10)
    try:
        with conn:
            if rule.kind == "sessions":
                where, params, table = "expires_at < ?", (now,), "sessions"
            elif rule.kind == "conversations":
                if not rule.days:
                    out.note = "kept forever"
                    return out
                where, params, table = "updated_at < ?", (now - rule.days * DAY,), "conversations"
            else:  # case_notifications: a notice lives as long as its ticket
                live = _ticket_ids(Path(queue_path))
                if live is None:
                    out.note = "no ticket queue to compare with: kept"
                    return out
                rows = conn.execute("SELECT customer_id, ticket_id FROM case_notifications").fetchall()
                stale = [r for r in rows if r[1] not in live]
                out.kept, out.dropped = len(rows) - len(stale), len(stale)
                if stale and not dry_run:
                    conn.executemany("DELETE FROM case_notifications WHERE customer_id = ? AND ticket_id = ?", stale)
                return out
            total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            doomed = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]
            if doomed and not dry_run:
                conn.execute(f"DELETE FROM {table} WHERE {where}", params)
            out.kept, out.dropped = total - doomed, doomed
    finally:
        conn.close()
    return out


def _prune_stale_files(rule: Rule, now: float, dry_run: bool) -> Outcome:
    """Leftovers a killed process leaves next to the data: rewrite asides and half-built warehouses."""
    out = Outcome(rule.name, days=STALE_TEMP_SECONDS / DAY)
    root = Path(rule.path)
    if not root.is_dir():
        return out
    for pattern in ("*.tmp", "*.building", "*.building.wal"):
        for f in root.glob(pattern):
            if f.is_file() and now - f.stat().st_mtime > STALE_TEMP_SECONDS:
                out.dropped += 1
                if not dry_run:
                    f.unlink(missing_ok=True)
    return out


def status_path() -> Path:
    return Path(os.environ.get("RETENTION_STATUS_PATH", "data/warehouse/retention_status.json"))


def run(now: float | None = None, dry_run: bool = False) -> list[Outcome]:
    now = time.time() if now is None else now
    policy = rules()
    queue_path = next(r.path for r in policy if r.name == "tickets")
    outcomes = []
    for rule in policy:
        try:
            if rule.kind == "jsonl":
                outcomes.append(_prune_jsonl(rule, now, dry_run))
            elif rule.kind == "ticket_events":
                outcomes.append(_prune_ticket_events(rule, now, dry_run=dry_run, queue_path=queue_path))
            elif rule.kind == "stale_files":
                outcomes.append(_prune_stale_files(rule, now, dry_run))
            else:
                outcomes.append(_prune_sqlite(rule, now, dry_run, queue_path))
        except Exception as exc:  # noqa: BLE001 - one store failing must not stop the others from being pruned
            logger.exception("retention: %s failed", rule.name)
            outcomes.append(Outcome(rule.name, days=rule.days, note=f"failed: {type(exc).__name__}"))
    if not dry_run:
        _record(outcomes, now)
    return outcomes


def _record(outcomes: list[Outcome], now: float) -> None:
    """The purge's own audit trail (counts only) and the status file /metrics reads."""
    from agent.tools.audit import default_audit_log

    failed = [o.name for o in outcomes if o.note.startswith("failed")]
    default_audit_log.event("retention_purge", dropped={o.name: o.dropped for o in outcomes if o.dropped},
                            failed=failed, policy_days={o.name: o.days for o in outcomes if o.days})
    path = status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    aside = path.with_name(path.name + ".tmp")
    aside.write_text(json.dumps({"last_run": now, "failed": failed, "outcomes": [asdict(o) for o in outcomes]}), encoding="utf-8")
    os.replace(aside, path)


def loop(interval_hours: float, sleep: Callable[[float], None] = time.sleep, cycles: int | None = None) -> None:
    """Run now and then every `interval_hours`; a failed cycle is logged and the next one still happens."""
    done = 0
    while cycles is None or done < cycles:
        try:
            print_outcomes(run())
        except Exception:  # noqa: BLE001
            logger.exception("retention cycle failed")
        done += 1
        if cycles is None or done < cycles:
            sleep(interval_hours * 3600)


def print_outcomes(outcomes: list[Outcome]) -> None:
    for o in outcomes:
        age = f" (>{o.days:g}d)" if o.days else ""
        print(f"retention {o.name}: kept={o.kept} dropped={o.dropped}{age}{' ' + o.note if o.note else ''}", flush=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="count what would be dropped; change nothing")
    ap.add_argument("--loop", action="store_true", help="run repeatedly every --interval-hours")
    ap.add_argument("--interval-hours", type=float, default=float(os.environ.get("RETENTION_INTERVAL_HOURS") or 24))
    args = ap.parse_args(argv)
    if args.loop:
        loop(args.interval_hours)
    else:
        print_outcomes(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
