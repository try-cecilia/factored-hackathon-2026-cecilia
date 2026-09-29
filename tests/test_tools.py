"""Tool-layer policies on fixture data: masking, ownership, semantics, freshness. (Retention: tests/test_retention.py.)"""
from __future__ import annotations

import pytest

from agent.tools import account_tools as t
from agent.tools.errors import DataUnavailable, InvalidArgument, NotApplicable, PermissionDenied


def test_numbers_leave_the_tool_layer_masked():
    items = t.get_account_summary("CLI-FIX0001")["items"]
    assert all("product_number" not in it and len(it["last4"]) == 4 for it in items)
    profile = t.get_customer_profile("CLI-FIX0001")
    assert {p["last4"] for p in profile["products"]} >= {"0001", "0002"}


def test_ownership_is_enforced_on_every_tool():
    for fn, kw in ((t.get_account_summary, {"product_id": "PRD-FIX0006"}), (t.list_transactions, {"product_id": "PRD-FIX0006"}),
                   (t.get_payment_status, {"product_id": "PRD-FIX0007"})):
        with pytest.raises(PermissionDenied):
            fn("CLI-FIX0001", **kw)


def test_payment_status_semantics():
    assert t.get_payment_status("CLI-FIX0001", "PRD-FIX0005")["days_past_due"] == 5
    with pytest.raises(NotApplicable):
        t.get_payment_status("CLI-FIX0001", "PRD-FIX0001")
    with pytest.raises(DataUnavailable):
        t.get_payment_status("CLI-FIX0002", "PRD-FIX0007")


def test_fx_fallback_inverse_and_validation():
    r = t.get_exchange_rate("CLI-FIX0001", "MXN", "USD", on_date="2024-01-15")
    assert r["was_fallback"] and str(r["used_date"]) == "2024-01-14"
    inv = t.get_exchange_rate("CLI-FIX0001", "USD", "ARS", on_date="2024-01-16")
    assert inv["derived_from_inverse"] and inv["exchange_rate"] == pytest.approx(1 / 0.001221, rel=1e-4)
    with pytest.raises(InvalidArgument):
        t.get_exchange_rate("CLI-FIX0001", "EUR", "USD")
    with pytest.raises(DataUnavailable):  # nothing within the 7-day fallback window
        t.get_exchange_rate("CLI-FIX0001", "COP", "ARS", on_date="2024-01-16")


def test_freshness_policy_blocks_stale_answers_when_enforced(monkeypatch):
    assert t.get_account_summary("CLI-FIX0004")["as_of"].isoformat() == "2024-01-16"
    monkeypatch.setenv("FRESHNESS_ENFORCE", "1")
    monkeypatch.setenv("FRESHNESS_SLO_HOURS", "36")
    with pytest.raises(DataUnavailable) as exc:
        t.get_account_summary("CLI-FIX0004")
    assert exc.value.field == "as_of"


def test_transaction_limit_is_clamped_in_the_tool_too():
    assert t.list_transactions("CLI-FIX0001", limit=10_000)["limit"] == 50
