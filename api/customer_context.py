"""What an operator sees about the customer beside a case: the customer's products, latest movements, and other cases and traces.

Read-only and minimal: the products are the type, currency, status and the last four digits of the number (the database cuts it, so
the number itself is never read), the movements are the customer's latest ones and the pending ones, and nothing carries a fraud score,
a channel, a document or a contact. It reads the warehouse with the tools' own connection, freshness date and freshness limit (`account_tools._rows`,
`data_as_of`, `_check_freshness`) but not through the tools themselves: they write an exception's message into the audit log, which /admin/audit_log
serves, and a message can quote a path, a query or a customer. The read is recorded here instead, as an audit event with the ticket,
the outcome and, on a failure, the exception's type. The cases and traces come
from the queue, the desk and the trace file, so they are there even when the warehouse is not: the warehouse's part is `warehouse`
(available or not), and when it fails the rest is still answered.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from agent import observability
from agent.policy.desk import TicketDesk
from agent.policy.escalation import HumanQueue
from agent.tools import account_tools
from agent.tools.audit import default_audit_log
from agent.tools.traces import TraceService

logger = logging.getLogger(__name__)

MOVEMENTS_SHOWN = 10  # the latest ones...
PENDING_SHOWN = 100  # ...plus the pending ones, however old: a pending movement is what a case is often about. Past this cap the
# response says how many were left out (`pending_omitted`) and the console shows "and N more"; it is far above what one customer holds.
CASES_SHOWN = 10
TRACES_SHOWN = 10


def for_ticket(ticket: dict, queue: HumanQueue, desk: TicketDesk, traces: TraceService) -> dict[str, Any]:
    customer_id = ticket["customer_id"]
    products, movements, as_of, omitted, error_type, queried_at, freshness = _warehouse(customer_id)
    available = products is not None
    default_audit_log.event("customer_context_read", ticket_id=ticket["ticket_id"], warehouse="ok" if available else "unavailable",
                            **({} if available else {"error_type": error_type}))
    return {
        "warehouse": {"available": available, "source": "account_warehouse", "as_of": as_of,
                      "queried_at": queried_at, "freshness": freshness},
        "products": products or [],
        "movements": movements or [],
        "pending_omitted": omitted,
        "cases": _other_cases(ticket, queue, desk),
        "traces": _traces(customer_id, traces.path),
    }


_PRODUCTS = """SELECT product_id, product_type, currency, product_status, right(CAST(product_number AS VARCHAR), 4) AS last4
               FROM products WHERE customer_id = ? ORDER BY product_type, opening_date, product_id"""
_MOVEMENTS = """SELECT transaction_id, transaction_date, product_id, transaction_type, amount, currency, merchant_name, transaction_status
                FROM transactions WHERE customer_id = ? {where} ORDER BY transaction_date DESC, transaction_id LIMIT ?"""


def _warehouse(customer_id: str) -> tuple[list[dict] | None, list[dict] | None, str | None, int, str | None, str, str]:
    """Return the customer data with its source date, query time, and freshness state."""
    queried_at = datetime.now(timezone.utc).isoformat()
    as_of = None
    try:
        as_of = account_tools.data_as_of()
        account_tools._check_freshness()
        if not account_tools._rows("SELECT 1 FROM customers WHERE customer_id = ?", [customer_id]):
            raise LookupError("no such customer")
        products = account_tools._rows(_PRODUCTS, [customer_id])
        latest = account_tools._rows(_MOVEMENTS.format(where=""), [customer_id, MOVEMENTS_SHOWN])
        pending = account_tools._rows(_MOVEMENTS.format(where="AND transaction_status = 'Pending'"), [customer_id, PENDING_SHOWN])
        pending_total = account_tools._rows("SELECT count(*) AS n FROM transactions WHERE customer_id = ? AND transaction_status = 'Pending'", [customer_id])[0]["n"]
    except Exception as exc:
        observability.count_failure("customer_context_unavailable")
        logger.warning("customer context: the warehouse did not answer (%s)", type(exc).__name__)
        stale = isinstance(exc, account_tools.DataUnavailable) and exc.field == "as_of"
        freshness = "stale" if stale and as_of else "missing" if stale else "unavailable"
        return None, None, _iso(as_of), 0, type(exc).__name__, queried_at, freshness
    products = [{"product_id": p["product_id"], "type": p["product_type"], "currency": p["currency"], "status": p["product_status"],
                 "last4": p["last4"]} for p in products]
    seen: set[str] = set()
    movements = []
    for m in sorted([*latest, *pending], key=lambda m: str(m["transaction_date"]), reverse=True):
        if m["transaction_id"] in seen:
            continue
        seen.add(m["transaction_id"])
        movements.append({"transaction_id": m["transaction_id"], "date": _iso(m["transaction_date"]), "product_id": m["product_id"],
                          "type": m["transaction_type"], "amount": _number(m["amount"]), "currency": m["currency"],
                          "merchant": m["merchant_name"], "status": m["transaction_status"], "pending": m["transaction_status"] == "Pending"})
    return products, movements, _iso(as_of), max(pending_total - len(pending), 0), None, queried_at, "current"


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
