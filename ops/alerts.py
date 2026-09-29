"""Alert check for the signals in docs/operations.md ("Monitoring"), run from a schedule (cron, Render cron job, CI).

Reads /admin/ops, /admin/llm_budget and /admin/data_quality from a running service, prints one line per firing
alert, posts them to ALERT_WEBHOOK_URL when set (Slack-style {"text": ...}), and exits 1 if any fired.

    ALERT_BASE_URL=https://... ADMIN_API_KEY=... [ALERT_WEBHOOK_URL=...] python -m ops.alerts

Only the thresholds that need no history are here. The week-over-week ones (CLARIFY rate, escalation rate by
category) need a stored baseline and stay in docs/operations.md.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

P95_LATENCY_MS = 8000
SECURITY_ESCALATIONS = 5  # ponytail: per /admin/ops window (last 1,000 turns), not per hour or per customer; per-customer needs the trace log


def evaluate(ops: dict, budget: dict, dq: dict | None) -> list[str]:
    alerts = []
    if ops.get("handoff_unverified"):
        alerts.append(f"handoff_unverified: {ops['handoff_unverified']} tickets did not read back (the customer was told to call)")
    if ops.get("llm_unavailable"):
        alerts.append(f"llm_unavailable: {ops['llm_unavailable']} turns with no model answer (provider outage or circuit open)")
    if (ops.get("latency_ms_p95") or 0) > P95_LATENCY_MS:
        alerts.append(f"p95 turn latency {ops['latency_ms_p95']} ms > {P95_LATENCY_MS} ms")
    security = (ops.get("escalations_by_category") or {}).get("security", 0)
    if security > SECURITY_ESCALATIONS:
        alerts.append(f"security escalations: {security} in the last {ops.get('turns')} turns (> {SECURITY_ESCALATIONS})")
    if budget.get("exhausted"):
        alerts.append(f"model budget exhausted: ${budget.get('spent_today_usd')} of ${budget.get('limit_usd')}, running degraded")
    if dq is None:
        alerts.append("data quality: no report found")
    elif dq.get("summary", {}).get("status") != "success" or dq.get("summary", {}).get("errors_failed"):
        alerts.append(f"data quality: {dq.get('summary')}")
    return alerts


def _get(base: str, path: str, key: str) -> dict | None:
    req = urllib.request.Request(base.rstrip("/") + path, headers={"X-Admin-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and path.endswith("data_quality"):
            return None
        raise


def main() -> int:
    base, key = os.environ["ALERT_BASE_URL"], os.environ["ADMIN_API_KEY"]
    alerts = evaluate(_get(base, "/admin/ops", key), _get(base, "/admin/llm_budget", key), _get(base, "/admin/data_quality", key))
    for a in alerts:
        print("ALERT", a)
    hook = os.environ.get("ALERT_WEBHOOK_URL")
    if alerts and hook:
        body = json.dumps({"text": "\n".join(alerts)}).encode()
        urllib.request.urlopen(urllib.request.Request(hook, body, {"Content-Type": "application/json"}), timeout=20)
    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
