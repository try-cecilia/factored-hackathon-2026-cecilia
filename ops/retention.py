"""Retention for the JSONL records this service writes (they contain customer data).

Policy implemented here (see docs/operations.md):
- traces.jsonl and audit_log.jsonl: 30 days (debugging/audit window);
- human_queue.jsonl: 90 days here, as a stand-in — in production tickets
  live in the bank's case system under its regulatory retention schedule.
Run daily (cron / scheduled job):  python -m ops.retention
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

POLICY = [  # (env var for the path, default path, timestamp field, max age days)
    ("TRACE_LOG_PATH", "data/warehouse/traces.jsonl", "ts", 30),
    ("AUDIT_LOG_PATH", "data/warehouse/audit_log.jsonl", "started_at", 30),
    ("HUMAN_QUEUE_PATH", "data/warehouse/human_queue.jsonl", "created_at", 90),
]


def prune(path: Path, ts_field: str, max_age_days: int, now: float | None = None) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    cutoff = (now or time.time()) - max_age_days * 86400
    kept, dropped = [], 0
    for line in path.read_text().splitlines():
        ts = json.loads(line).get(ts_field)
        if isinstance(ts, (int, float)) and ts < cutoff:
            dropped += 1
        else:
            kept.append(line)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(k + "\n" for k in kept))
    tmp.replace(path)
    return len(kept), dropped


def main() -> None:
    for env, default, field, days in POLICY:
        kept, dropped = prune(Path(os.environ.get(env, default)), field, days)
        print(f"{env}: kept={kept} dropped={dropped} (>{days}d)")


if __name__ == "__main__":
    main()
