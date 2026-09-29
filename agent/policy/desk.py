"""The human side of a handoff: an operator claims a ticket, approves or rejects the action it carries, or hands the
conversation back to the automation.

Only a person can approve an action the assistant is not allowed to take (docs/plan.md). The desk is an append-only
event log next to the queue (HUMAN_DESK_PATH); a ticket's state is the replay of its events, and its version is their
count. Every transition checks the current state under one lock, so a double click, a retry or two operators can
never apply the same action twice: repeating the outcome a ticket already reached returns it unchanged, and any
other move on a finished ticket is a Conflict. An operator may also pass the version they saw: a decision made on a
stale screen is refused. Approving re-checks the world (the movement must still be pending) instead of trusting
what the assistant saw when it filed the ticket.

Statuses: open -> claimed -> approved | rejected | handed_back | stale (the movement settled before approval).
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from agent.policy.escalation import default_queue
from agent.tools import account_tools
from agent.tools.traces import default_traces

TERMINAL = {"approved", "rejected", "handed_back", "stale"}
OUTCOME_OF = {"approve": ("approved", "stale"), "reject": ("rejected",), "release": ("handed_back",)}


class DeskError(Exception):
    pass


class NotFound(DeskError):
    pass


class Conflict(DeskError):
    pass


class TicketDesk:
    def __init__(self):
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        p = Path(os.environ.get("HUMAN_DESK_PATH", "data/warehouse/ticket_events.jsonl"))
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _events(self, ticket_id: str) -> list[dict]:
        # ponytail: linear scan of a local JSONL file; the bank's case system answers this by id
        if not self.path.exists():
            return []
        found = (json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip())
        return [e for e in found if e["ticket_id"] == ticket_id]

    def state(self, ticket_id: str) -> dict[str, Any]:
        events = self._events(ticket_id)
        status, operator = "open", None
        for e in events:
            status = e["status"]
            operator = e["operator"] if status == "claimed" else operator
        return {"ticket_id": ticket_id, "status": status, "operator": operator, "version": len(events),
                "history": [{k: e[k] for k in ("action", "status", "operator", "ts", "detail")} for e in events]}

    def _record(self, ticket_id: str, action: str, status: str, operator: str, detail: dict | None = None) -> None:
        event = {"ticket_id": ticket_id, "action": action, "status": status, "operator": operator, "ts": time.time(),
                 "detail": detail or {}}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def act(self, ticket_id: str, action: str, operator: str, expected_version: int | None = None,
            reason: str | None = None) -> dict[str, Any]:
        """One operator move (claim, approve, reject, release) on one ticket; returns the ticket's new state."""
        operator = (operator or "").strip()
        if action not in ("claim", "approve", "reject", "release") or not operator:
            raise DeskError("an action (claim, approve, reject, release) and an operator name are required")
        with self._lock:
            ticket = default_queue.get(ticket_id)
            if ticket is None:
                raise NotFound(f"no ticket {ticket_id}")
            current = self.state(ticket_id)
            status = current["status"]
            if status in TERMINAL:  # repeating what already happened is a no-op; anything else is a conflict
                if status in OUTCOME_OF.get(action, ()) and operator == self._closer(ticket_id):
                    return current
                raise Conflict(f"ticket is already {status}")
            if expected_version is not None and expected_version != current["version"]:
                raise Conflict(f"the ticket changed (you saw version {expected_version}, now {current['version']})")
            if action == "claim":
                if status == "claimed":
                    if current["operator"] == operator:
                        return current
                    raise Conflict(f"ticket is already claimed by {current['operator']}")
                self._record(ticket_id, action, "claimed", operator)
            else:
                if status != "claimed" or current["operator"] != operator:
                    raise Conflict("claim the ticket before deciding it")
                self._decide(ticket, action, operator, reason)
            return self.state(ticket_id)

    def _closer(self, ticket_id: str) -> str | None:
        events = self._events(ticket_id)
        return events[-1]["operator"] if events else None

    def _decide(self, ticket: dict, action: str, operator: str, reason: str | None) -> None:
        ticket_id = ticket["ticket_id"]
        if action == "release":
            return self._record(ticket_id, action, "handed_back", operator)
        if action == "reject":
            return self._record(ticket_id, action, "rejected", operator, {"reason": (reason or "")[:300]})
        pending = ticket.get("pending_action")
        if not pending:
            raise Conflict("this ticket carries no action to approve")
        outcome, trace = self._execute(ticket, pending)
        if outcome == "no_longer_pending":  # the world moved on: nothing is opened, and the operator is told
            return self._record(ticket_id, action, "stale", operator, {"outcome": outcome})
        if outcome == "unverified":  # not read back: stays claimed so the operator can retry (opening is idempotent)
            raise Conflict("the tracing service did not confirm the trace; nothing was announced, try again")
        self._record(ticket_id, action, "approved", operator, {"outcome": outcome, "trace_id": trace["trace_id"]})

    @staticmethod
    def _execute(ticket: dict, pending: dict) -> tuple[str, dict | None]:
        customer, txn, product = ticket["customer_id"], pending["transaction_id"], pending["product_id"]
        still = account_tools.request_trace(customer, product_id=product, transaction_id=txn)["items"]
        if not still:
            return "no_longer_pending", None
        default_traces.open(customer, txn, product, ticket["session_ref"])
        trace = default_traces.find(customer, txn)  # read back before saying it exists
        return ("opened", trace) if trace else ("unverified", None)


default_desk = TicketDesk()
