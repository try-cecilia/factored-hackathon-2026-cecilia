"""Deterministic tools for the Account/Payment Inquiries workflow.

Plain Python over the DuckDB warehouse — no LLM involved. Enforced in every
function, in code:
1. Ownership: the session's customer_id must own the product. A mismatch
   raises PermissionDenied (security event), not an empty result.
2. Verification: results are returned only when the fields the answer needs
   exist; otherwise DataUnavailable. Questions that don't apply to a product
   raise NotApplicable, which the policy layer answers rather than escalates.
3. Data minimization: account/card numbers leave this layer as last-4 only.
4. Freshness: every result carries `as_of` (the warehouse's data date). With
   FRESHNESS_ENFORCE=1, a warehouse older than FRESHNESS_SLO_HOURS makes
   balance/transaction answers DataUnavailable instead of silently stale.
All calls are written to the audit log with the current trace id.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional

from agent.llm.privacy import internal_ids, normalize
from agent.tools.audit import default_audit_log
from agent.tools.db import duckdb_path, get_connection
from agent.tools.errors import DataUnavailable, InvalidArgument, NotApplicable, PermissionDenied, ResourceNotFound

CREDIT_PRODUCT_TYPES = {"Tarjeta Crédito", "Préstamo Personal", "Préstamo Hipotecario"}
CURRENCIES = {"MXN", "COP", "ARS", "USD"}
MAX_TRANSACTIONS = 50
MAX_FX_FALLBACK_DAYS = 7


def _audited(tool_name: str, customer_id: str, args: dict[str, Any], fn):
    record = default_audit_log.start(tool_name, customer_id, args)
    try:
        result = fn()
    except Exception as exc:
        default_audit_log.finish(record, success=False, error=exc)
        raise
    default_audit_log.finish(record, success=True, result_summary=_summarize(result))
    return result


def _summarize(result: Any) -> Any:
    if isinstance(result, dict) and isinstance(result.get("items"), list):
        return {k: v for k, v in result.items() if k != "items"} | {"n_items": len(result["items"])}
    return result


def _rows(sql: str, params: list) -> list[dict]:
    cur = get_connection().execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@lru_cache(maxsize=8)
def _as_of_for(path: str) -> date | None:
    row = get_connection().execute("SELECT max(process_date) FROM transactions").fetchone()
    return row[0] if row else None


def data_as_of() -> date | None:
    return _as_of_for(duckdb_path())


def _check_freshness() -> None:
    if os.environ.get("FRESHNESS_ENFORCE") != "1":
        return
    as_of = data_as_of()
    slo_h = float(os.environ.get("FRESHNESS_SLO_HOURS", "36"))
    age_h = (datetime.now(timezone.utc).date() - as_of).days * 24 if as_of else float("inf")
    if age_h > slo_h:
        raise DataUnavailable(f"warehouse data as of {as_of} exceeds freshness SLO of {slo_h:.0f}h", field="as_of")


def _last4(number: Any) -> str | None:
    return str(number)[-4:] if number else None


def _owned_product(customer_id: str, product_id: str) -> dict:
    rows = _rows("SELECT product_id, customer_id, product_type, product_status FROM products WHERE product_id = ?", [product_id])
    if not rows:
        raise ResourceNotFound(f"No product found with id {product_id}.")
    if rows[0]["customer_id"] != customer_id:
        raise PermissionDenied(f"Customer {customer_id} requested product {product_id} owned by another customer.",
                               resource_id=product_id)
    return rows[0]


def _parse_date(value: Optional[str], name: str) -> Optional[date]:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise InvalidArgument(f"{name} must be YYYY-MM-DD, got {value!r}", missing_slots=[name]) from None


def foreign_product_refs(customer_id: str, text: str) -> list[str]:
    """Product ids written in the customer's message that exist but belong to
    someone else. Customers don't type internal ids; one that isn't theirs is
    an unauthorized-access or injection attempt, caught here before any model
    decides whether to pass it on. Detection is shared with the masking
    (agent/llm/privacy.py), so an id written with odd dashes, invisible
    characters or glued to other words is caught here too."""
    ids = sorted({c for mention in internal_ids(normalize(text)) for c in mention if c.startswith("PRD-")})
    if not ids:
        return []

    def _run():
        rows = _rows(f"SELECT product_id FROM products WHERE product_id IN ({', '.join('?' * len(ids))}) AND customer_id <> ?",
                     ids + [customer_id])
        return sorted(r["product_id"] for r in rows)

    return _audited("ownership_check", customer_id, {"product_ids": ids}, _run)


def get_customer_profile(customer_id: str) -> dict:
    """Segment/status plus the product catalog (masked). The orchestrator turns
    the catalog into aliases; the model sees only alias, type, currency and
    status (ADR-001)."""

    def _run():
        cust = _rows("SELECT customer_id, segment, country, customer_status FROM customers WHERE customer_id = ?", [customer_id])
        if not cust:
            raise ResourceNotFound(f"Customer {customer_id} not found.")
        # A total order: aliases (P1, P2...) and the options listed to the customer must mean
        # the same product on every turn, even for two products of one type opened the same day.
        products = _rows(
            """SELECT product_id, product_type, product_number, currency, product_status
               FROM products WHERE customer_id = ? ORDER BY product_type, opening_date, product_id""", [customer_id])
        for p in products:
            p["last4"] = _last4(p.pop("product_number"))
        return {**cust[0], "products": products, "as_of": data_as_of()}

    return _audited("get_customer_profile", customer_id, {}, _run)


def get_account_summary(customer_id: str, product_id: Optional[str] = None) -> dict:
    def _run():
        _check_freshness()
        if product_id:
            _owned_product(customer_id, product_id)
            where, params = "product_id = ?", [product_id]
        else:
            where, params = "customer_id = ?", [customer_id]
        items = _rows(
            f"""SELECT product_id, product_type, product_number, currency, current_balance, credit_limit,
                       product_status, days_past_due, last_transaction_date
                FROM products WHERE {where} ORDER BY product_type, opening_date""", params)
        for it in items:
            it["last4"] = _last4(it.pop("product_number"))
            if it["current_balance"] is None:
                raise DataUnavailable(f"balance missing for product {it['product_id']}", field="current_balance")
        return {"items": items, "as_of": data_as_of()}

    return _audited("get_account_summary", customer_id, {"product_id": product_id}, _run)


def list_transactions(
    customer_id: str,
    product_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 10,
) -> dict:
    def _run():
        _check_freshness()
        if product_id:
            _owned_product(customer_id, product_id)
        start, end = _parse_date(start_date, "start_date"), _parse_date(end_date, "end_date")
        if start and end and start > end:
            raise InvalidArgument("start_date is after end_date", missing_slots=["start_date", "end_date"])
        n = max(1, min(int(limit or 10), MAX_TRANSACTIONS))
        clauses, params = ["customer_id = ?"], [customer_id]
        if product_id:
            clauses.append("product_id = ?"); params.append(product_id)
        if start:
            clauses.append("process_date >= ?"); params.append(start)
        if end:
            clauses.append("process_date <= ?"); params.append(end)
        if status:
            clauses.append("transaction_status = ?"); params.append(status)
        items = _rows(
            f"""SELECT transaction_id, transaction_date, product_id, transaction_type, amount, currency,
                       channel, merchant_name, transaction_status, is_fraud, fraud_score
                FROM transactions WHERE {' AND '.join(clauses)}
                ORDER BY transaction_date DESC LIMIT ?""", params + [n])
        return {"items": items, "as_of": data_as_of(), "limit": n,
                "filters": {"product_id": product_id, "start_date": start, "end_date": end, "status": status}}

    return _audited("list_transactions", customer_id,
                    {"product_id": product_id, "start_date": start_date, "end_date": end_date, "status": status, "limit": limit}, _run)


def get_payment_status(customer_id: str, product_id: str) -> dict:
    def _run():
        _check_freshness()
        product = _owned_product(customer_id, product_id)
        if product["product_type"] not in CREDIT_PRODUCT_TYPES:
            raise NotApplicable(
                f"payment status applies to credit products; {product_id} is a {product['product_type']}",
                payload={"product_id": product_id, "product_type": product["product_type"], "applies_to": sorted(CREDIT_PRODUCT_TYPES)},
            )
        row = _rows("""SELECT current_balance, credit_limit, currency, days_past_due, last_transaction_date, product_status, product_type
                       FROM products WHERE product_id = ?""", [product_id])[0]
        if row["days_past_due"] is None:
            raise DataUnavailable(f"days_past_due is missing for product {product_id}", field="days_past_due")
        available = None
        if row["credit_limit"] is not None and row["current_balance"] is not None:
            available = row["credit_limit"] - row["current_balance"]
        return {"product_id": product_id, **row, "available_credit": available,
                "is_past_due": row["days_past_due"] > 0, "as_of": data_as_of()}

    return _audited("get_payment_status", customer_id, {"product_id": product_id}, _run)


def get_exchange_rate(customer_id: str, source_currency: str, target_currency: str, on_date: Optional[str] = None) -> dict:
    """Rate for a date (default: data as-of). Falls back, flagged, to the most
    recent prior date within MAX_FX_FALLBACK_DAYS, then to the inverse pair."""

    def _run():
        src, tgt = str(source_currency or "").upper(), str(target_currency or "").upper()
        bad = [n for n, v in (("source_currency", src), ("target_currency", tgt)) if v not in CURRENCIES]
        if bad or src == tgt:
            raise InvalidArgument(f"currencies must be two different values of {sorted(CURRENCIES)}", missing_slots=bad or ["target_currency"])
        requested = _parse_date(on_date, "on_date") or data_as_of()
        oldest = requested - timedelta(days=MAX_FX_FALLBACK_DAYS)

        def lookup(a, b):
            return _rows("""SELECT date, exchange_rate FROM daily_exchange_rates
                            WHERE source_currency = ? AND target_currency = ? AND date <= ? AND date >= ?
                            ORDER BY date DESC LIMIT 1""", [a, b, requested, oldest])

        direct = lookup(src, tgt)
        inverse = [] if direct else lookup(tgt, src)
        if not direct and not inverse:
            raise DataUnavailable(f"no {src}->{tgt} rate within {MAX_FX_FALLBACK_DAYS} days before {requested}", field="exchange_rate")
        row = (direct or inverse)[0]
        rate = row["exchange_rate"] if direct else round(1 / float(row["exchange_rate"]), 6)
        return {"source_currency": src, "target_currency": tgt, "requested_date": requested, "used_date": row["date"],
                "exchange_rate": rate, "was_fallback": row["date"] != requested, "derived_from_inverse": not direct,
                "as_of": data_as_of()}

    return _audited("get_exchange_rate", customer_id,
                    {"on_date": on_date, "source_currency": source_currency, "target_currency": target_currency}, _run)


def recent_activity_for_review(customer_id: str, limit: int = 10) -> dict:
    """Evidence pack for a human reviewing a fraud/dispute escalation."""

    def _run():
        items = _rows("""SELECT transaction_id, transaction_date, product_id, transaction_type, amount, currency,
                                merchant_name, transaction_country, transaction_status, is_fraud, fraud_score
                         FROM transactions WHERE customer_id = ? ORDER BY transaction_date DESC LIMIT ?""",
                      [customer_id, limit])
        return {"items": items, "as_of": data_as_of()}

    return _audited("recent_activity_for_review", customer_id, {"limit": limit}, _run)
