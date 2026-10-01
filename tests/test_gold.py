"""The gold marts: what they hold, that they add up to silver, and that a failed build leaves the previous mart alone."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import duckdb
import pytest

from data import gold
from data.gold import GoldError, MARTS, build, verify
from tests.conftest import build_fixture_warehouse


@pytest.fixture
def silver():
    """A tiny silver: five movements of two customers, plus the lineage a real load leaves."""
    con = duckdb.connect(":memory:")
    con.execute("""CREATE TABLE transactions (transaction_id VARCHAR, transaction_date TIMESTAMP, customer_id VARCHAR, product_id VARCHAR,
                   transaction_type VARCHAR, transaction_status VARCHAR, amount DECIMAL(15,2), currency VARCHAR, channel VARCHAR,
                   transaction_country VARCHAR)""")
    con.execute("""INSERT INTO transactions VALUES
        ('t1', '2025-01-01 10:00', 'c1', 'p1', 'Payment', 'Approved', -100.50, 'USD', 'Web', 'México'),
        ('t2', '2025-01-01 15:00', 'c1', 'p1', 'Payment', 'Approved', -20.00, 'USD', 'Web', 'México'),
        ('t3', '2025-01-02 09:00', 'c1', 'p2', 'Deposit', 'Pending', 300.00, 'MXN', 'ATM', 'México'),
        ('t4', '2025-01-02 11:00', 'c2', 'p3', 'Payment', 'Approved', -5.25, 'USD', 'App', NULL),
        ('t5', '2025-01-02 12:00', 'c2', 'p3', 'Payment', 'Declined', -7.00, 'USD', 'App', NULL)""")
    con.execute("""CREATE TABLE _ingestion_log (run_id VARCHAR, table_name VARCHAR, status VARCHAR, finished_at TIMESTAMP)""")
    con.execute("INSERT INTO _ingestion_log VALUES ('run-old', 'transactions', 'success', '2025-01-01'), ('run-new', 'transactions', 'success', '2025-01-03')")
    yield con
    con.close()


def rows(con, sql):
    return con.execute(sql).fetchall()


def test_the_serving_marts_hold_the_expected_figures_and_add_up(silver):
    results = {r["mart"]: r for r in build(silver)}
    assert results["gold_daily_activity"]["status"] == results["gold_customer_summary"]["status"] == "built"
    assert rows(silver, """SELECT activity_date, n_transactions, n_customers, total_abs_amount FROM gold_daily_activity
                           WHERE currency = 'USD' AND transaction_type = 'Payment' AND transaction_country = 'México'""") == [(date(2025, 1, 1), 2, 1, 120.50 * 1)]
    assert rows(silver, "SELECT n_transactions, n_channels, n_currencies, n_products FROM gold_customer_summary WHERE customer_id = 'c1'") == [(3, 2, 2, 2)]
    assert rows(silver, "SELECT n_transactions, n_countries FROM gold_customer_summary WHERE customer_id = 'c2'") == [(2, 0)]  # a NULL country is not a country


def test_a_mart_without_its_source_tables_is_skipped_and_says_why(silver):
    skipped = [r for r in build(silver) if r["mart"] == "gold_contact_demand"][0]
    assert skipped["status"] == "skipped" and "call_center_interactions" in skipped["detail"]
    assert "gold_contact_demand" not in {r[0] for r in rows(silver, "SELECT table_name FROM information_schema.tables")}


def test_the_log_names_the_silver_load_the_mart_read_and_the_sql_it_ran(silver):
    build(silver)
    mart, status, runs, sha = rows(silver, "SELECT mart, status, source_runs, sql_sha256 FROM _gold_log WHERE mart = 'gold_customer_summary'")[0]
    assert status == "built" and '"transactions": "run-new"' in runs and len(sha) == 64
    stamped = rows(silver, "SELECT DISTINCT _gold_run_id FROM gold_customer_summary")
    assert stamped == rows(silver, "SELECT gold_run_id FROM _gold_log WHERE mart = 'gold_customer_summary'")


def test_a_failed_reconciliation_rolls_back_and_keeps_the_previous_mart(silver, monkeypatch):
    build(silver)
    before = rows(silver, "SELECT _gold_run_id, count(*) FROM gold_customer_summary GROUP BY 1")
    bad = replace(MARTS[1], reconcile=(("n_transactions", "SELECT sum(n_transactions) FROM gold_customer_summary", "SELECT count(*) + 1 FROM transactions"),))
    monkeypatch.setattr(gold, "MARTS", (MARTS[0], bad))
    with pytest.raises(GoldError, match="adds up to 5, silver has 6"):
        build(silver)
    assert rows(silver, "SELECT _gold_run_id, count(*) FROM gold_customer_summary GROUP BY 1") == before
    assert rows(silver, "SELECT status FROM _gold_log WHERE mart = 'gold_customer_summary' ORDER BY started_at DESC LIMIT 1") == [("failed",)]


def test_a_grain_that_repeats_fails_the_build(silver, monkeypatch):
    dup = replace(MARTS[1], sql="SELECT customer_id, 1 AS n_transactions FROM transactions", reconcile=())
    monkeypatch.setattr(gold, "MARTS", (dup,))
    with pytest.raises(GoldError, match="grain .* is not unique"):
        build(silver)


def test_verify_shows_a_silver_that_changed_after_the_build(silver):
    build(silver)
    assert verify(silver) == []
    silver.execute("INSERT INTO transactions VALUES ('t6', '2025-01-03 10:00', 'c3', 'p9', 'Payment', 'Approved', -1.00, 'USD', 'Web', 'México')")
    problems = verify(silver)
    assert any("gold_customer_summary" in p and "silver has 6" in p for p in problems)
    assert any("gold_daily_activity" in p for p in problems)


def test_the_contact_demand_mart_keeps_a_contact_whose_customer_is_unknown():
    con = duckdb.connect(":memory:")
    con.execute("""CREATE TABLE customers (customer_id VARCHAR, country VARCHAR)""")
    con.execute("INSERT INTO customers VALUES ('c1', 'México')")
    con.execute("""CREATE TABLE call_center_interactions (interaction_id VARCHAR, interaction_date TIMESTAMP, customer_id VARCHAR, channel VARCHAR,
                   reason_category VARCHAR, duration_seconds INTEGER, wait_time_seconds INTEGER, was_resolved BOOLEAN, requires_followup BOOLEAN)""")
    con.execute("""INSERT INTO call_center_interactions VALUES
        ('i1', '2025-03-05 10:00', 'c1', 'Phone', 'Balance', 100, 10, true, false),
        ('i2', '2025-03-20 10:00', 'c1', 'Phone', 'Balance', 300, 30, false, true),
        ('i3', '2025-03-21 10:00', 'ghost', 'Phone', 'Balance', 50, 5, true, false)""")
    assert [r["status"] for r in build(con, only=("gold_contact_demand",))] == ["built"]
    assert rows(con, "SELECT country, n_contacts, n_resolved, n_followup, avg_duration_seconds FROM gold_contact_demand ORDER BY country NULLS LAST") == [
        ("México", 2, 1, 1, 200.0), (None, 1, 1, 0, 50.0)]
    con.close()


def test_every_mart_builds_and_reconciles_on_the_real_contract(tmp_path, monkeypatch):
    path = tmp_path / "w.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(path))
    build_fixture_warehouse()
    con = duckdb.connect(str(path))
    try:
        built = {r["mart"]: r for r in build(con)}
        assert built["gold_daily_activity"]["status"] == built["gold_customer_summary"]["status"] == "built"
        assert built["gold_daily_activity"]["n_rows"] > 0 and verify(con) == []
    finally:
        con.close()


def test_a_column_whose_type_drifts_from_the_contract_fails_the_build(silver, monkeypatch):
    drifted = replace(MARTS[1], sql=MARTS[1].sql.replace("count(*) AS n_transactions", "CAST(count(*) AS VARCHAR) AS n_transactions"), reconcile=())
    monkeypatch.setattr(gold, "MARTS", (drifted,))
    with pytest.raises(GoldError, match="columns differ from the contract.*n_transactions VARCHAR"):
        build(silver)


def test_the_declared_columns_are_the_real_ones_on_every_mart(silver):
    # the contract is not a copy that can rot: it is compared with what each query returns, here and on every build
    assert [r["status"] for r in build(silver)] == ["built", "built", "skipped"]
