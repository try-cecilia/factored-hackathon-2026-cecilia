"""What an operator sees about the customer beside a case: the customer's products, latest movements, and other cases and traces.

Read-only and minimal: the products are the type, currency, status and the last four digits of the number (never the number), the
movements are what the assistant's own tools already list (`agent/tools/account_tools.py`, called as they are, and audited like any
other read of the customer's data), and nothing carries a fraud score, a channel, a document or a contact. The cases and traces come
from the queue, the desk and the trace file, so they are there even when the warehouse is not: the warehouse's part is `warehouse`
(available or not), and when it fails the rest is still answered.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from agent import observability
from agent.policy.desk import TicketDesk
from agent.policy.escalation import HumanQueue
from agent.tools import account_tools
from agent.tools.traces import TraceService

logger = logging.getLogger(__name__)

MOVEMENTS_SHOWN = 10  # the latest ones...
PENDING_SHOWN = 10  # ...plus the pending ones, however old: a pending movement is what a case is often about
CASES_SHOWN = 10
TRACES_SHOWN = 10


def for_ticket(ticket: dict, queue: HumanQueue, desk: TicketDesk, traces: TraceService) -> dict[str, Any]:
    customer_id = ticket["customer_id"]
    products, movements, as_of = _warehouse(customer_id)
    return {
        "warehouse": {"available": products is not None, "as_of": as_of},
        "products": products or [],
        "movements": movements or [],
        "cases": _other_cases(ticket, queue, desk),
        "traces": _traces(customer_id, traces.path),
    }


def _warehouse(customer_id: str) -> tuple[list[dict] | None, list[dict] | None, str | None]:
    """(products, movements, data date), or all None when the warehouse does not answer, whatever the reason. The exception is
    counted and logged by its type only: its message can quote a path, a query or a customer id."""
    try:
        profile = account_tools.get_customer_profile(customer_id)
        latest = account_tools.list_transactions(customer_id, limit=MOVEMENTS_SHOWN)["items"]
        pending = account_tools.list_transactions(customer_id, status="Pending", limit=PENDING_SHOWN)["items"]
    except Exception as exc:
        observability.count_failure("customer_context_unavailable")
        logger.warning("customer context: the warehouse did not answer (%s)", type(exc).__name__)
        return None, None, None
    products = [{"product_id": p["product_id"], "type": p["product_type"], "currency": p["currency"], "status": p["product_status"],
                 "last4": p["last4"]} for p in profile["products"]]
    seen: set[str] = set()
    movements = []
    for m in sorted([*latest, *pending], key=lambda m: str(m["transaction_date"]), reverse=True):
        if m["transaction_id"] in seen:
            continue
        seen.add(m["transaction_id"])
        movements.append({"transaction_id": m["transaction_id"], "date": _iso(m["transaction_date"]), "product_id": m["product_id"],
                          "type": m["transaction_type"], "amount": _number(m["amount"]), "currency": m["currency"],
                          "merchant": m["merchant_name"], "status": m["transaction_status"], "pending": m["transaction_status"] == "Pending"})
    return products, movements, _iso(profile["as_of"])


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, (date, datetime)) else None if value is None else str(value)


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _other_cases(ticket: dict, queue: HumanQueue, desk: TicketDesk) -> list[dict]:
    """The customer's other cases, newest first, each with the desk's state now."""
    others = [t for t in queue.for_customer(ticket["customer_id"]) if t["ticket_id"] != ticket["ticket_id"]]
    others.sort(key=lambda t: t.get("created_at") or 0, reverse=True)
    return [{"ticket_id": t["ticket_id"], "category": t.get("category"), "queue": t.get("queue"), "priority": t.get("priority"),
             "created_at": t.get("created_at"), "status": desk.state(t["ticket_id"])["status"]} for t in others[:CASES_SHOWN]]


def _traces(customer_id: str, path: Path) -> list[dict]:
    """The customer's trace requests, newest first. A line that is not a JSON object is skipped, never quoted."""
    if not path.exists():
        return []
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if customer_id not in line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        if isinstance(request, dict) and request.get("customer_id") == customer_id:
            found.append({"trace_id": request.get("trace_id"), "transaction_id": request.get("transaction_id"),
                          "status": request.get("status"), "created_at": request.get("created_at")})
    found.sort(key=lambda t: t["created_at"] or 0, reverse=True)
    return found[:TRACES_SHOWN]
