"""How far a movement is from the customer's own earlier behavior: the frozen contract in docs/BEHAVIORAL_EVIDENCE.md.

Descriptive evidence for a human reviewer. Not a fraud probability or fraud determination, and nothing may route, block or
answer because of it: only the ticket's evidence list and the operator screen read it (ADR-005).

Inputs are the customer's own rows, each a dict with transaction_id, transaction_date, amount, currency, channel,
merchant_category and transaction_country. A row's history is the rows strictly earlier than it, so no label, status,
future row or other customer can enter.
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable

MIN_PRIOR = 5            # prior rows for any composite, and for each velocity component
MIN_COMPONENTS = 4       # of the six
MIN_TENURE_DAYS = 60     # for the 30-day velocity
COMPONENTS = ("amount", "channel", "category", "country", "velocity_24h", "velocity_30d")
DISCLAIMER = "Descriptive behavioral evidence only; not a fraud probability or fraud determination."


def _when(value: Any) -> datetime:
    """The warehouse mixes DATE and TIMESTAMP columns."""
    return value if isinstance(value, datetime) else datetime.combine(value, datetime.min.time())


def _rise(ratio: float, saturates_at: float) -> float:
    """0 up to the usual rate, then logarithmic up to 1 at `saturates_at` times it."""
    return 0.0 if ratio <= 1 else min(math.log2(ratio) / math.log2(saturates_at), 1.0)


def band(composite: float) -> str:
    return "low" if composite < 25 else "moderate" if composite < 50 else "elevated" if composite < 75 else "high"


def score_customer(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """For every row of one customer, its components, composite (or None) and band, keyed by transaction_id."""
    ordered = sorted(rows, key=lambda r: (_when(r["transaction_date"]), r["transaction_id"]))
    times = [_when(r["transaction_date"]) for r in ordered]
    channels: set = set()
    categories: set = set()
    countries: set = set()
    amount_sum: dict[str, float] = defaultdict(float)
    amount_n: dict[str, int] = defaultdict(int)
    seen = 0  # rows strictly earlier than the current one: a tie on the timestamp is not prior
    out: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(ordered):
        lo = bisect_left(times, times[i])  # the prior rows are exactly ordered[:lo]
        while seen < lo:
            prior = ordered[seen]
            channels.add(prior.get("channel")); categories.add(prior.get("merchant_category")); countries.add(prior.get("transaction_country"))
            amount_sum[prior.get("currency")] += abs(float(prior["amount"])); amount_n[prior.get("currency")] += 1
            seen += 1
        out[row["transaction_id"]] = _describe(row, times[i], times, lo, channels, categories, countries, amount_sum, amount_n)
    return out


def _describe(row, now, times, n_prior, channels, categories, countries, amount_sum, amount_n) -> dict[str, Any]:
    c: dict[str, float | None] = dict.fromkeys(COMPONENTS)
    if n_prior:
        c["channel"] = float(row.get("channel") not in channels)
        c["country"] = float(row.get("transaction_country") not in countries)
        if row.get("merchant_category") is not None:
            c["category"] = float(row["merchant_category"] not in categories)
    currency = row.get("currency")
    if amount_n[currency] and amount_sum[currency] > 0 and float(row["amount"]) != 0:
        mean = amount_sum[currency] / amount_n[currency]
        c["amount"] = min(abs(math.log2(abs(float(row["amount"])) / mean)) / 2, 1.0)
    in_30d = n_prior - bisect_right(times, now - timedelta(days=30), 0, n_prior)
    if in_30d >= MIN_PRIOR:
        in_24h = n_prior - bisect_right(times, now - timedelta(hours=24), 0, n_prior)
        c["velocity_24h"] = _rise(in_24h / (in_30d / 30), 8)
    tenure = (now - times[0]).days if n_prior else 0
    if n_prior >= MIN_PRIOR and tenure >= MIN_TENURE_DAYS:
        c["velocity_30d"] = _rise(in_30d / (n_prior / tenure * 30), 4)
    available = [v for v in c.values() if v is not None]
    composite = round(100 * sum(available) / len(available), 1) if n_prior >= MIN_PRIOR and len(available) >= MIN_COMPONENTS else None
    return {"components": c, "composite": composite, "band": band(composite) if composite is not None else None,
            "prior_count": n_prior}


def evidence_for(rows: list[dict[str, Any]], transaction_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """`score_customer` for just the rows the reviewer will see."""
    scored = score_customer(rows)
    return {t: scored[t] for t in transaction_ids if t in scored}
