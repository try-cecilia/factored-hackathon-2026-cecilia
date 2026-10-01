from datetime import date, datetime, timedelta

import pytest

from agent.policy.behavior import score_customer

T0 = datetime(2025, 1, 1, 12)


def row(i, days, amount=100.0, channel="Web", category="Food", country="México", currency="USD", at=None):
    return {"transaction_id": f"T{i}", "transaction_date": at or T0 + timedelta(days=days), "amount": amount,
            "currency": currency, "channel": channel, "merchant_category": category, "transaction_country": country}


def steady(n=10, spacing=10):
    return [row(i, i * spacing) for i in range(n)]


def test_first_rows_have_no_composite_and_a_steady_customer_scores_zero():
    scored = score_customer(steady())
    assert scored["T0"]["composite"] is None and scored["T4"]["composite"] is None  # fewer than 5 prior rows
    assert scored["T9"]["composite"] == 0.0 and scored["T9"]["band"] == "low"


def test_a_new_channel_country_and_amount_raise_it():
    rows = steady() + [row(10, 100, amount=400.0, channel="ATM", country="Chile")]
    last = score_customer(rows)["T10"]
    assert last["components"]["channel"] == last["components"]["country"] == 1.0
    assert last["components"]["category"] == 0.0
    assert last["components"]["amount"] == 1.0  # 4x the prior mean saturates
    assert last["composite"] > 50 and last["band"] in ("elevated", "high")


def test_amount_is_compared_only_within_its_currency():
    rows = steady() + [row(10, 100, amount=100.0, currency="ARS")]
    assert score_customer(rows)["T10"]["components"]["amount"] is None


def test_the_row_itself_and_later_rows_never_count():
    base = steady()
    before = score_customer(base)["T9"]
    after = score_customer(base + [row(10, 200, amount=9999.0, channel="ATM")])["T9"]
    assert before == after


def test_a_tie_on_the_timestamp_is_not_prior():
    rows = [row(i, i, at=T0) for i in range(6)]
    assert all(r["prior_count"] == 0 and r["composite"] is None for r in score_customer(rows).values())


def test_a_burst_scores_on_24h_velocity_and_a_quiet_gap_does_not():
    rows = steady(8, spacing=4) + [row(8 + k, 28 + 0.1 * k) for k in range(8)]
    burst = score_customer(rows)["T15"]
    assert burst["components"]["velocity_24h"] > 0.5
    quiet = score_customer(steady(8, spacing=4) + [row(8, 28 + 40)])["T8"]
    assert quiet["components"]["velocity_24h"] is None or quiet["components"]["velocity_24h"] == 0.0


def test_dates_without_a_time_are_accepted():
    rows = [row(i, 0, at=date(2025, 1, 1) + timedelta(days=i * 10)) for i in range(8)]
    assert score_customer(rows)["T7"]["prior_count"] == 7


def test_no_category_means_that_component_is_unavailable_not_novel():
    rows = steady() + [row(10, 100, category=None)]
    assert score_customer(rows)["T10"]["components"]["category"] is None


@pytest.mark.parametrize("n", [1, 3])
def test_a_customer_without_history_has_nothing_to_compare(n):
    assert all(r["composite"] is None for r in score_customer(steady(n)).values())


def test_a_history_over_the_cap_keeps_the_latest_rows_so_the_shown_movements_are_still_described(monkeypatch):
    from agent.tools import account_tools

    base = datetime(2025, 1, 1)
    table = [dict(transaction_id=f"t{i:02d}", transaction_date=base + timedelta(days=i), amount=100.0, currency="USD", channel="Web",
                  merchant_category="Food", transaction_country="México", product_id="p", transaction_type="Payment",
                  merchant_name="m", transaction_status="Posted", is_fraud=False, fraud_score=None) for i in range(12)]

    def fake_rows(sql, params):  # honors the one thing under test: the direction of the ORDER BY and the LIMIT
        rows = sorted(table, key=lambda r: r["transaction_date"], reverse="DESC" in sql.split("ORDER BY")[1])
        return rows[:params[-1]]

    monkeypatch.setattr(account_tools, "_rows", fake_rows)
    monkeypatch.setattr(account_tools, "data_as_of", lambda: None)
    monkeypatch.setattr(account_tools, "MAX_BEHAVIOR_HISTORY", 8)
    items = account_tools.recent_activity_for_review("c1", limit=2)["items"]
    assert [t["transaction_id"] for t in items] == ["t11", "t10"]
    assert all(t["behavior"] is not None and t["behavior"]["composite"] == 0.0 for t in items)
