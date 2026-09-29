"""Smoke test of a running deploy: the CI container, or the Render URL once it is live.

    python ops/container_smoke.py BASE_URL

Checks only what needs no language model, so it holds on any warehouse and without a model key: health,
the guided scenarios (DEMO_MODE=1), the data-quality view (tables from the lineage, the complete-dataset run,
no source location), a fraud report escalated with its ticket in the bank view and no token in it, a suspended
account held, and an expired session. Stdlib only; exits 1 on the first failure.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/")


def call(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"content-type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, None


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        sys.exit(1)


status, health = call("GET", "/health")
check(status == 200 and health["status"] == "ok" and not str(health["data_as_of"]).startswith("unavailable"), f"health: {health}")
status, scenarios = call("GET", "/demo/scenarios")
check(status == 200 and bool(scenarios), f"{len(scenarios or [])} guided scenarios")
by_id = {s["id"]: s for s in scenarios}
status, dq = call("GET", "/demo/data_quality")
check(status == 200 and bool(dq), f"data-quality view: HTTP {status}")
text = json.dumps(dq)  # on a deploy the lineage tables hold the organizer's bucket: it must not leave
check(bool(dq["served"]["tables"]) and dq["full_run"] is not None and "s3://" not in text and "file:" not in text,
      f"data quality: {len(dq['served']['tables'])} tables from the lineage, the complete-dataset run, no source location")

for sid, want in (("human_fraud", "ESCALATE"), ("human_compliance", "ESCALATE"), ("failure_expired", "REAUTH_REQUIRED")):
    s = by_id.get(sid)
    if s is None:
        print(f"skip {sid}: this warehouse has no customer for it")
        continue
    status, session = call("POST", "/auth/session", {"customer_id": s["customer_id"], "pin": s["test_pin"]})
    check(status == 200, f"{sid}: sign in as {s['customer_id']}")
    token = session["token"]
    if s["fault"]:
        check(call("POST", "/demo/fault", {"session_token": token, "fault": s["fault"]})[0] == 200, f"{sid}: {s['fault']}")
    reply = [call("POST", "/chat", {"session_token": token, "message": t})[1] for t in s["turns"]][-1]
    check(reply["disposition"] == want and bool(reply["why"]), f"{sid}: {reply['disposition']} by {reply['policy_rule']}")
    if want == "ESCALATE":
        _, tickets = call("POST", "/demo/tickets", {"session_token": token})
        check(bool(tickets) and tickets[0]["ticket_id"] == reply["ticket_id"] and token not in json.dumps(tickets),
              f"{sid}: ticket {reply['ticket_id'][:8]} in the bank view, without the token")
print("smoke test passed")
