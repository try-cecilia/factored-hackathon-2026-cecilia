"""The baseline report reads its contact figures from the gold mart; these hold them to what the raw contacts give."""
from __future__ import annotations

import duckdb
import pytest

from analysis.baseline_contact_center import TEXT_CHANNELS, gold_contacts, rows
from data.gold import build

TXN = "reason_category = 'Transaccional'"


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE TABLE customers (customer_id VARCHAR, country VARCHAR)")
    c.execute("INSERT INTO customers VALUES ('a', 'México'), ('b', 'Colombia'), ('c', 'Argentina')")
    c.execute("""CREATE TABLE call_center_interactions (interaction_id VARCHAR, interaction_date TIMESTAMP, customer_id VARCHAR, channel VARCHAR,
                 reason_category VARCHAR, duration_seconds INTEGER, wait_time_seconds INTEGER, was_resolved BOOLEAN, requires_followup BOOLEAN)""")
    contacts = []
    n = 0
    # 3 customers x 4 channels x 2 reasons over months inside and outside the report window; one customer the customers table does not know
    for month in ("2023-05", "2023-07", "2024-01", "2024-02", "2025-12", "2026-06"):
        for customer in ("a", "b", "c", "ghost"):
            for channel in ("Phone", "WhatsApp", "Web", "Branch"):
                for reason in ("Transaccional", "Consulta"):
                    for day in range(1 + (n % 3)):
                        n += 1
                        contacts.append((f"i{n}", f"{month}-{10 + day} 10:00", customer, channel, reason, 100 + n % 7, 10, n % 2 == 0, n % 5 == 0))
    c.executemany("INSERT INTO call_center_interactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", contacts)
    build(c, only=("gold_contact_demand",))
    yield c
    c.close()


def raw_figures(con):
    """The queries `compute` used before the mart, on the contacts themselves."""
    return {
        "contact_reasons": rows(con, "SELECT reason_category, count(*) AS contacts, round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct FROM call_center_interactions GROUP BY 1 ORDER BY 2 DESC"),
        "channels": rows(con, f"SELECT channel, count(*) AS contacts, round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct FROM call_center_interactions WHERE {TXN} GROUP BY 1 ORDER BY 2 DESC"),
        "text_channel_pct": con.execute(f"SELECT round(100 * avg(CASE WHEN channel IN {TEXT_CHANNELS} THEN 1 ELSE 0 END), 1) FROM call_center_interactions WHERE {TXN}").fetchone()[0],
        "by_country": rows(con, f"SELECT cu.country, count(*) AS contacts, round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct FROM call_center_interactions c JOIN customers cu USING (customer_id) WHERE {TXN} GROUP BY 1 ORDER BY 2 DESC"),
        "monthly_contacts_median": con.execute(f"""SELECT median(n) FROM (SELECT count(*) n FROM call_center_interactions
            WHERE {TXN} AND interaction_date >= DATE '2023-07-01' AND interaction_date < DATE '2026-06-01' GROUP BY date_trunc('month', interaction_date))""").fetchone()[0],
    }


def as_sets(figure):
    """Rows with equal counts may come in either order; compare what each row says."""
    return {tuple(sorted(r.items())) for r in figure} if isinstance(figure, list) else figure


def test_every_figure_read_from_the_mart_equals_the_one_the_raw_contacts_give(con):
    from_mart, from_raw = gold_contacts(con), raw_figures(con)
    assert set(from_mart) == set(from_raw)
    for key in from_raw:
        assert as_sets(from_mart[key]) == as_sets(from_raw[key]), key


def test_the_fixture_has_what_makes_the_comparison_mean_something(con):
    raw = raw_figures(con)
    countries = {r["country"] for r in raw["by_country"]}
    assert countries == {"México", "Colombia", "Argentina"}  # the contacts of the unknown customer are not in a country...
    assert sum(r["contacts"] for r in raw["channels"]) > sum(r["contacts"] for r in raw["by_country"])  # ...but they are in the channels
    assert 0 < raw["text_channel_pct"] < 100 and raw["monthly_contacts_median"] > 0


def test_without_the_mart_it_says_what_to_run():
    empty = duckdb.connect(":memory:")
    with pytest.raises(SystemExit, match="make gold"):
        gold_contacts(empty)
    empty.close()


def test_no_text_channel_among_the_transactional_contacts_is_zero_percent_as_in_silver_and_the_economics_still_run(con):
    con.execute("UPDATE call_center_interactions SET channel = 'Phone'")
    con.execute("DROP TABLE gold_contact_demand")
    build(con, only=("gold_contact_demand",))
    assert raw_figures(con)["text_channel_pct"] == 0.0
    assert gold_contacts(con)["text_channel_pct"] == 0.0
    from analysis.unit_economics import scenarios
    share = gold_contacts(con)["text_channel_pct"] / 100  # what unit_economics reads from the baseline report
    assert scenarios(1000, share, 300, 0.5, 0.01)  # with None here it raised TypeError


def test_with_no_transactional_contact_at_all_the_text_share_stays_undefined(con):
    con.execute("UPDATE call_center_interactions SET reason_category = 'Consulta'")
    con.execute("DROP TABLE gold_contact_demand")
    build(con, only=("gold_contact_demand",))
    assert raw_figures(con)["text_channel_pct"] is None and gold_contacts(con)["text_channel_pct"] is None
