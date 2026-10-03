"""Tool-layer policies on fixture data: masking, ownership, semantics, freshness. (Retention: tests/test_retention.py.)"""
from __future__ import annotations

import pytest

from agent.tools import account_tools as t
from agent.tools.errors import DataUnavailable, InvalidArgument, NotApplicable, PermissionDenied
from agent.policy.payment_rules import PaymentRule


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


def test_freshness_is_opt_in_and_stale_data_is_served_with_its_date_by_default(monkeypatch):
    monkeypatch.delenv("FRESHNESS_ENFORCE", raising=False)
    assert t.get_account_summary("CLI-FIX0004")["as_of"].isoformat() == "2024-01-16"


def test_missing_data_date_is_rejected_even_when_age_check_is_disabled(monkeypatch):
    monkeypatch.setenv("FRESHNESS_ENFORCE", "0")
    monkeypatch.setattr(t, "data_as_of", lambda: None)
    with pytest.raises(DataUnavailable) as exc:
        t.get_account_summary("CLI-FIX0004")
    assert exc.value.field == "as_of"


def test_transaction_limit_is_clamped_in_the_tool_too():
    assert t.list_transactions("CLI-FIX0001", limit=10_000)["limit"] == 50


def test_payment_conditions_use_verified_country_and_currency(monkeypatch):
    from agent.policy import payment_rules

    profile = t.get_customer_profile("CLI-FIX0001")
    product = profile["products"][0]
    country = payment_rules.country_code(profile["country"])
    rule = PaymentRule("transfer_fee", 1, country, "Transfer", "commission", product["currency"], 25,
                       product["currency"], "Test fixture",
                       "https://example.test/rules", __import__("datetime").date(2026, 1, 1),
                       __import__("datetime").date(2026, 1, 1), None)
    monkeypatch.setattr(payment_rules, "load_catalog", lambda: [rule])
    result = t.get_payment_conditions("CLI-FIX0001", product["product_id"], "Transfer", "commission", "2026-10-03")
    assert result["country"] == country
    assert result["currency"] == product["currency"]
    assert result["rules"][0]["value"] == 25
    assert result["rules"][0]["source_url"] == "https://example.test/rules"
    from agent.core.render import render_result
    for lang, phrase in (("es", "comisión de Transfer"), ("pt", "comissão de Transfer")):
        rendered = render_result("get_payment_conditions", result, lang, profile["country"])
        assert phrase in rendered and "Test fixture" in rendered
        assert "25" in rendered and "v1" in rendered
        assert product["currency"] in rendered


def test_payment_condition_rendering_includes_scope_currency_for_percentage_and_deadline():
    from agent.core.render import render_result

    for unit in ("percent", "business days"):
        result = {"operation": "Transfer", "currency": "ARS", "rules": [{
            "kind": "commission" if unit == "percent" else "deadline", "value": 1.5 if unit == "percent" else 2,
            "unit": unit, "version": 1, "valid_from": "2026-01-01", "source_issuer": "Test fixture",
            "source_url": "https://example.test/rules", "source_checked_at": "2026-01-01",
        }]}
        rendered = render_result("get_payment_conditions", result, "es", "Argentina")
        assert "ARS" in rendered and unit in rendered


def test_payment_conditions_without_backed_rule_raise_specific_unavailability():
    with pytest.raises(DataUnavailable, match="respaldada") as exc:
        t.get_payment_conditions("CLI-FIX0001", "PRD-FIX0001", "Transfer", "commission", "2026-10-03")
    assert exc.value.field == "payment_rule"
