from datetime import date

import pytest

from agent.policy.payment_rules import country_code, load_catalog, resolve_rules, validate_catalog


def sample_rule(**changes):
    rule = {
        "rule_id": "ar_transfer_fee_fixed",
        "version": 1,
        "country": "AR",
        "operation": "Transfer",
        "kind": "commission",
        "currency": "ARS",
        "value": 55,
        "unit": "ARS",
        "source": {
            "issuer": "Example Bank",
            "url": "https://example.invalid/fees",
            "checked_at": "2026-10-01",
            "officially_reviewed": True,
        },
        "valid_from": "2026-01-01",
        "valid_until": "2027-01-01",
    }
    rule.update(changes)
    return rule


def catalog(*rules):
    return {"schema_version": 1, "rules": list(rules)}


def test_country_code_maps_only_the_four_supported_customer_countries():
    assert [country_code(value) for value in ("Argentina", "Brasil", "Colombia", "México")] == ["AR", "BR", "CO", "MX"]
    assert [country_code(value) for value in ("AR", "brazil", "MX")] == ["AR", "BR", "MX"]
    assert country_code("Chile") is None
    assert country_code(None) is None


def test_resolve_rules_requires_exact_country_operation_kind_currency_and_date():
    rules = validate_catalog(catalog(sample_rule()))
    assert resolve_rules("Argentina", "Transfer", "commission", "ARS", date(2026, 10, 3), rules=rules) == rules
    assert resolve_rules("Brazil", "Transfer", "commission", "ARS", date(2026, 10, 3), rules=rules) == []
    assert resolve_rules("BR", "Transfer", "commission", "USD", date(2026, 10, 3), rules=rules) == []
    assert resolve_rules("Argentina", "Payment", "commission", "ARS", date(2026, 10, 3), rules=rules) == []
    assert resolve_rules("Argentina", "Transfer", "threshold", "ARS", date(2026, 10, 3), rules=rules) == []
    assert resolve_rules("Argentina", "Transfer", "commission", "USD", date(2026, 10, 3), rules=rules) == []


def test_rule_validity_includes_start_excludes_end_and_allows_no_end():
    bounded = validate_catalog(catalog(sample_rule()))
    assert len(resolve_rules("AR", "Transfer", "commission", "ARS", date(2026, 1, 1), rules=bounded)) == 1
    assert resolve_rules("AR", "Transfer", "commission", "ARS", date(2027, 1, 1), rules=bounded) == []

    open_ended = validate_catalog(catalog(sample_rule(valid_until=None)))
    assert len(resolve_rules("AR", "Transfer", "commission", "ARS", date(2030, 1, 1), rules=open_ended)) == 1


@pytest.mark.parametrize("missing", ["currency", "source", "valid_from"])
def test_catalog_rejects_rules_without_required_evidence_metadata(missing):
    rule = sample_rule()
    rule.pop(missing)
    with pytest.raises(ValueError):
        validate_catalog(catalog(rule))


def test_catalog_rejects_overlapping_versions_of_the_same_rule():
    first = sample_rule(valid_from="2026-01-01", valid_until="2026-08-01")
    second = sample_rule(version=2, valid_from="2026-07-01", valid_until="2027-01-01")
    with pytest.raises(ValueError, match="overlap"):
        validate_catalog(catalog(first, second))


def test_catalog_rejects_overlapping_rules_with_distinct_ids_and_same_scope():
    first = sample_rule(rule_id="ar_transfer_fee_a")
    second = sample_rule(rule_id="ar_transfer_fee_b", value=2, unit="percent")
    with pytest.raises(ValueError, match="scope"):
        validate_catalog(catalog(first, second))


def test_resolver_returns_no_rule_when_unvalidated_input_is_ambiguous():
    from dataclasses import replace

    rules = validate_catalog(catalog(sample_rule()))
    ambiguous = rules + [replace(rules[0], rule_id="other")]
    assert resolve_rules("AR", "Transfer", "commission", "ARS", date(2026, 10, 3), rules=ambiguous) == []


def test_catalog_requires_explicit_official_source_review():
    rule = sample_rule()
    rule["source"].pop("officially_reviewed")
    with pytest.raises(ValueError, match="officially_reviewed"):
        validate_catalog(catalog(rule))


def test_production_catalog_loads_with_no_unverified_live_rules():
    assert load_catalog() == []


@pytest.mark.parametrize("changes", [
    {"operation": "Wire"},                                   # an operation with no words for the customer
    {"kind": "fee"},
    {"kind": "deadline", "unit": "ARS"},                     # a deadline in money
    {"kind": "deadline", "unit": "weeks"},
    {"kind": "commission", "unit": "USD"},                   # a commission in another currency than the rule's
    {"kind": "threshold", "unit": "percent"},
])
def test_catalog_accepts_only_units_operations_and_kinds_that_have_words(changes):
    with pytest.raises(ValueError):
        validate_catalog(catalog(sample_rule(**changes)))


def test_catalog_units_are_stored_in_one_canonical_form():
    [deadline] = validate_catalog(catalog(sample_rule(kind="deadline", unit="Business_Days", operation="trace")))
    [percent] = validate_catalog(catalog(sample_rule(unit="Percent")))
    [money] = validate_catalog(catalog(sample_rule(unit="ars")))
    assert (deadline.unit, deadline.operation) == ("business days", "Trace")
    assert percent.unit == "percent" and money.unit == "ARS"
