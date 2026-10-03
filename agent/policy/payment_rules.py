"""Versioned, source-backed payment conditions scoped to a country and currency."""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

CATALOG_PATH = Path(__file__).with_name("payment_rules.json")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
# Closed vocabularies: every value a reply or a receipt may carry has an ES/PT word in agent/core/render.py, so nothing
# internal ("Transfer", "business days") is printed to the customer as it is stored.
OPERATIONS = ("Transfer", "Payment", "Deposit", "Withdrawal", "Purchase", "Trace")
KINDS = ("commission", "deadline", "threshold")
DAY_UNITS = ("business days", "calendar days")
_COUNTRIES = {
    "ar": "AR", "argentina": "AR",
    "br": "BR", "brasil": "BR", "brazil": "BR",
    "co": "CO", "colombia": "CO",
    "mx": "MX", "mexico": "MX",
}


@dataclass(frozen=True, slots=True)
class PaymentRule:
    rule_id: str
    version: int
    country: str
    operation: str
    kind: str
    currency: str
    value: int | float
    unit: str
    source_issuer: str
    source_url: str
    source_checked_at: date
    valid_from: date
    valid_until: date | None


def country_code(country: str | None) -> str | None:
    """Normalize only the countries explicitly supported by the rule catalog."""
    if not isinstance(country, str) or not country.strip():
        return None
    normalized = unicodedata.normalize("NFKD", country.strip().casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return _COUNTRIES.get(normalized)


def _required_text(record: dict, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"rule {key} must be a non-empty string")
    return value.strip()


def _day(value, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be an ISO date") from None


def validate_catalog(raw: dict) -> list[PaymentRule]:
    """Validate all rule data before returning an immutable, typed view."""
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("rules"), list):
        raise ValueError("catalog must have schema_version 1 and a rules list")

    rules: list[PaymentRule] = []
    seen_versions: set[tuple[str, int]] = set()
    for record in raw["rules"]:
        if not isinstance(record, dict):
            raise ValueError("each rule must be an object")
        rule_id = _required_text(record, "rule_id")
        version = record.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("rule version must be a positive integer")
        if (rule_id, version) in seen_versions:
            raise ValueError(f"duplicate rule version: {rule_id} v{version}")
        seen_versions.add((rule_id, version))

        country = country_code(_required_text(record, "country"))
        if country is None:
            raise ValueError("country must be one of AR, BR, CO, MX")
        currency = _required_text(record, "currency").upper()
        if not _CURRENCY.fullmatch(currency):
            raise ValueError("currency must be a three-letter ISO 4217 code")
        operation = next((op for op in OPERATIONS if op.casefold() == _required_text(record, "operation").casefold()), None)
        if operation is None:
            raise ValueError(f"operation must be one of {', '.join(OPERATIONS)}")
        kind = _required_text(record, "kind").casefold()
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        value = record.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
            raise ValueError("rule value must be a finite, non-negative number")
        unit = " ".join(_required_text(record, "unit").replace("_", " ").split())
        unit = currency if unit.upper() == currency else unit.casefold()
        allowed = DAY_UNITS if kind == "deadline" else (currency, "percent") if kind == "commission" else (currency,)
        if unit not in allowed:
            raise ValueError(f"a {kind} rule's unit must be one of {', '.join(allowed)}")

        source = record.get("source")
        if not isinstance(source, dict):
            raise ValueError("rule source must include issuer, url, and checked_at")
        issuer = _required_text(source, "issuer")
        url = _required_text(source, "url")
        if source.get("officially_reviewed") is not True:
            raise ValueError("rule source must be explicitly officially_reviewed")
        parsed_url = urlparse(url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError("rule source URL must use HTTPS")
        checked_at = _day(source.get("checked_at"), "source.checked_at")

        valid_from = _day(record.get("valid_from"), "valid_from")
        valid_until = _day(record["valid_until"], "valid_until") if record.get("valid_until") is not None else None
        if valid_until is not None and valid_until <= valid_from:
            raise ValueError("valid_until must be after valid_from")

        rules.append(PaymentRule(rule_id, version, country, operation, kind, currency, value, unit, issuer, url,
                                 checked_at, valid_from, valid_until))

    by_id: dict[str, list[PaymentRule]] = {}
    for rule in rules:
        by_id.setdefault(rule.rule_id, []).append(rule)
    for rule_id, versions in by_id.items():
        versions.sort(key=lambda item: item.version)
        first = versions[0]
        for previous, current in zip(versions, versions[1:]):
            if (current.country, current.operation.casefold(), current.kind, current.currency, current.unit.casefold()) != (
                    first.country, first.operation.casefold(), first.kind, first.currency, first.unit.casefold()):
                raise ValueError(f"versions of {rule_id} must keep the same rule scope")
            if previous.valid_until is None or current.valid_from < previous.valid_until:
                raise ValueError(f"versions of {rule_id} overlap")
    by_scope: dict[tuple[str, str, str, str], list[PaymentRule]] = {}
    for rule in rules:
        scope = (rule.country, rule.operation.casefold(), rule.kind, rule.currency)
        by_scope.setdefault(scope, []).append(rule)
    for scoped_rules in by_scope.values():
        for index, first in enumerate(scoped_rules):
            for second in scoped_rules[index + 1:]:
                first_ends_after_second_starts = first.valid_until is None or second.valid_from < first.valid_until
                second_ends_after_first_starts = second.valid_until is None or first.valid_from < second.valid_until
                if first_ends_after_second_starts and second_ends_after_first_starts:
                    raise ValueError("rules with the same scope overlap")
    return rules


def load_catalog(path: Path = CATALOG_PATH) -> list[PaymentRule]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return validate_catalog(raw)


def resolve_rules(country: str | None, operation: str, kind: str, currency: str, on_date: date,
                  *, rules: Sequence[PaymentRule] | None = None) -> list[PaymentRule]:
    """Return every exact component applicable to the scope and requested date."""
    code = country_code(country)
    if code is None:
        return []
    catalog = load_catalog() if rules is None else rules
    op, rule_kind, cur = operation.strip().casefold(), kind.strip().casefold(), currency.strip().upper()
    matches = [rule for rule in catalog
               if rule.country == code and rule.operation.casefold() == op and rule.kind == rule_kind
               and rule.currency == cur and rule.valid_from <= on_date
               and (rule.valid_until is None or on_date < rule.valid_until)]
    return matches if len(matches) == 1 else []


def snapshot(rules: Sequence[PaymentRule]) -> list[dict]:
    """The rules as a trace record keeps them: what applied when it was opened, with its source and validity."""
    return [{"rule_id": r.rule_id, "version": r.version, "value": r.value, "unit": r.unit,
             "source_issuer": r.source_issuer, "source_url": r.source_url,
             "source_checked_at": r.source_checked_at.isoformat(), "valid_from": r.valid_from.isoformat(),
             "valid_until": r.valid_until.isoformat() if r.valid_until else None} for r in rules]


def trace_deadline_rules(country: str | None, currency: str | None, on_date: date | None = None) -> list[dict]:
    """The country's source-backed deadline for tracing a movement in this currency, as a snapshot; any doubt (no currency, no
    exact rule, a broken catalog) means no deadline, never a guessed one, and never blocks opening the trace."""
    if not currency:
        return []
    try:
        return snapshot(resolve_rules(country, "Trace", "deadline", currency, on_date or date.today()))
    except Exception:  # noqa: BLE001 - a broken catalog must not block opening a trace or create an unsupported promise
        return []


def deadline_business_days(rules: Sequence[dict] | None) -> int | None:
    """A trace's deadline in whole business days, only from its rule snapshot: None when there is no single rule in business days
    (zero is a deadline, absence is not). Never read from a record's own field, so a legacy synthetic SLA is never revived."""
    if not rules or len(rules) != 1 or not isinstance(rules[0], dict) or rules[0].get("unit") != "business days":
        return None
    value = rules[0].get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value != int(value):
        return None
    return int(value)
