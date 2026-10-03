"""The human side of a handoff: an operator claims a ticket, approves or rejects the action it carries, resolves a
ticket that carries none with a message for the customer, or hands the conversation back to the automation.
A resolution may instead name a predefined result for the ticket's family (RESULTS), which the customer reads as a fixed
template (agent/core/render.py), with the person's own words, if any, after it in the fixed quote.

Only a person can approve an action the assistant is not allowed to take (docs/plan.md). The desk is an append-only
event log next to the queue (HUMAN_DESK_PATH); a ticket's state is the replay of its events, and its version is their
count. Every transition checks the current state under one lock, so a double click, a retry or two operators can
never apply the same action twice: repeating the outcome a ticket already reached returns it unchanged, and any
other move on a finished ticket is a Conflict. An operator may also pass the version they saw: a decision made on a
stale screen is refused. Approving re-checks the world (the movement must still be pending) instead of trusting
what the assistant saw when it filed the ticket. A ticket that carries an action is closed by deciding that action,
never by resolving around it.

Statuses: open -> claimed -> approved | rejected | handed_back | stale (the movement settled before approval) | resolved.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from agent.llm.privacy import mask_card_numbers
from agent.policy.escalation import default_queue
from agent.tools import account_tools
from agent.tools.traces import default_traces

TERMINAL = {"approved", "rejected", "handed_back", "stale", "resolved"}
OUTCOME_OF = {"approve": ("approved", "stale"), "reject": ("rejected",), "release": ("handed_back",), "resolve": ("resolved",)}
ACTIONS = ("claim", "approve", "reject", "release", "resolve")
MESSAGE_MAX_CHARS = 500  # what the customer reads when a person resolves their case

# The predefined results a person may resolve a case with, by family of case, in the order offered. Each has a template the
# customer reads (render.RESOLVE_RESULT); a ticket's family comes from its category, never from anything the caller sends.
# A result only says what a person found and what the customer can do next: none announces an action (a block, a dispute, a
# trace), because resolving executes none. The one action, a trace, is opened by approving the ticket that carries it.
RESULTS = {
    "fraud": ("charge_confirmed", "will_contact", "call_the_bank"),
    "payments": ("movement_settled", "trace_not_possible", "will_contact", "call_the_bank"),
    "specialist": ("needs_specialist", "will_contact", "call_the_bank"),
    "general": ("info_checked", "no_action_needed", "will_contact", "call_the_bank"),
}
FAMILY = {"fraud": "fraud", "theft": "fraud", "account_takeover": "fraud", "classifier_escalation": "fraud",
          "trace_unmatched": "payments", "trace_unverified": "payments", "trace_review": "payments",
          "compliance_hold": "specialist", "security": "specialist", "legal_or_regulator": "specialist", "safety": "specialist"}


def results_for(ticket: dict) -> tuple[str, ...]:
    """The results this ticket may be resolved with: none when it carries an action, which is decided by approving or
    rejecting it, never by resolving around it."""
    if ticket.get("pending_action"):
        return ()
    return RESULTS[FAMILY.get(ticket.get("category") or "", "general")]


class DeskError(Exception):
    pass


class NotFound(DeskError):
    pass


class Conflict(DeskError):
    pass


class HeldByAnother(Conflict):
    """Another operator holds the ticket (claimed it). Its text is the desk's as always; the type lets a caller that must not
    name that operator (the demo's console) say so in its own words."""


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
        status, operator, trace_id, message, result = "open", None, None, None, None
        for e in events:
            status = e["status"]
            operator = e["operator"] if status == "claimed" else operator
            trace_id = e["detail"].get("trace_id", trace_id)
            message = e["detail"].get("message") if status == "resolved" else message
            result = e["detail"].get("result") if status == "resolved" else result
        return {"ticket_id": ticket_id, "status": status, "operator": operator, "trace_id": trace_id, "version": len(events),
                "message": message,  # the resolution's words to the customer; None unless resolved (or resolved with a result alone)
                "result": result,  # the predefined result it was resolved with (RESULTS); None unless resolved with one
                "history": [{k: e[k] for k in ("action", "status", "operator", "ts", "detail")} for e in events]}

    def _record(self, ticket_id: str, action: str, status: str, operator: str, detail: dict | None = None) -> None:
        event = {"ticket_id": ticket_id, "action": action, "status": status, "operator": operator, "ts": time.time(),
                 "detail": detail or {}}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def act(self, ticket_id: str, action: str, operator: str, expected_version: int | None = None,
            reason: str | None = None, message: str | None = None, result: str | None = None) -> dict[str, Any]:
        """One operator move (claim, approve, reject, release, resolve) on one ticket; returns the ticket's new state.
        A resolution takes a message for the customer, or a predefined result of the ticket's family and, optionally, a message."""
        operator = (operator or "").strip()
        if action not in ACTIONS or not operator:
            raise DeskError(f"an action ({', '.join(ACTIONS)}) and an operator name are required")
        if action == "resolve":
            message = _customer_message(message) if result is None or (message or "").strip() else None
        with self._lock:
            ticket = default_queue.get(ticket_id)
            if ticket is None:
                raise NotFound(f"no ticket {ticket_id}")
            if action == "resolve" and result is not None and result not in results_for(ticket):
                raise DeskError("that result is not one of this case's")
            current = self.state(ticket_id)
            status = current["status"]
            if status in TERMINAL:  # repeating what already happened is a no-op; anything else is a conflict
                if status in OUTCOME_OF.get(action, ()) and operator == self._closer(ticket_id):
                    if action != "resolve" or (message, result) == (current["message"], current["result"]):
                        return current
                    raise Conflict("ticket is already resolved with another message")  # the customer already has the first
                raise Conflict(f"ticket is already {status}")
            if expected_version is not None and expected_version != current["version"]:
                raise Conflict(f"the ticket changed (you saw version {expected_version}, now {current['version']})")
            if action == "claim":
                if status == "claimed":
                    if current["operator"] == operator:
                        return current
                    raise HeldByAnother(f"ticket is already claimed by {current['operator']}")
                self._record(ticket_id, action, "claimed", operator)
            else:
                if status != "claimed" or current["operator"] != operator:
                    error = HeldByAnother if status == "claimed" else Conflict
                    raise error("claim the ticket before deciding it")
                self._decide(ticket, action, operator, reason, message, result)
            return self.state(ticket_id)

    def _closer(self, ticket_id: str) -> str | None:
        events = self._events(ticket_id)
        return events[-1]["operator"] if events else None

    def _decide(self, ticket: dict, action: str, operator: str, reason: str | None, message: str | None,
                result: str | None = None) -> None:
        ticket_id = ticket["ticket_id"]
        if action == "release":
            return self._record(ticket_id, action, "handed_back", operator)
        if action == "reject":
            return self._record(ticket_id, action, "rejected", operator, {"reason": (reason or "")[:300]})
        pending = ticket.get("pending_action")
        if action == "resolve":
            if pending:  # resolving would leave the trace the customer asked for neither opened nor refused
                raise Conflict("this ticket carries an action: approve or reject it")
            return self._record(ticket_id, action, "resolved", operator,
                                {"message": message, **({"result": result} if result is not None else {})})
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


def _customer_message(message: str | None) -> str:
    """The operator's words as the customer will read them: on one line (each case notice is one line of the chat, and
    joining first lets the masking see a card number a line break had split), with any full card number masked (the
    customer's own included: a full PAN is never shown), without the «» it is quoted in (so it cannot close the quote
    and read as the assistant's words), between 1 and MESSAGE_MAX_CHARS characters. Card numbers are the only data
    masked: anything else the operator writes (another id, an account number, a phone) is theirs to get right."""
    text = mask_card_numbers(" ".join((message or "").split())).replace("«", '"').replace("»", '"').strip()
    if not text:
        raise DeskError("a message for the customer is required to resolve a case")
    if len(text) > MESSAGE_MAX_CHARS:
        raise DeskError(f"the message for the customer is longer than {MESSAGE_MAX_CHARS} characters")
    return text


default_desk = TicketDesk()
