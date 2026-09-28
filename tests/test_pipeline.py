"""Pipeline tests on hand-made fixtures (see tests/fixtures/README.md).

The late-arrival test is the challenge's "clearly labeled test fixture"
demonstrating update correctness for static data: a re-delivered partition
with one corrected amount and one new row must update in place, add exactly
one row, and be idempotent on replay.
"""
from __future__ import annotations

import shutil
from datetime import date

import duckdb
import pytest

from data.pipeline import PipelineError, RunConfig, run_pipeline
from data.quality import DataQualityError
from tests.conftest import FIXTURES, SERVING, build_fixture_warehouse


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    path = tmp_path / "w.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(path))
    return path


def q(path, sql, params=None):
    con = duckdb.connect(str(path), read_only=True)
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


def test_contracts_dedup_and_lineage(fresh_db):
    _, results = build_fixture_warehouse()
    by_table = {r.table: r for r in results}

    # Duplicate customer record: the later last_updated wins.
    assert q(fresh_db, "SELECT email FROM customers WHERE customer_id='CLI-FIX0004'") == [("mateo@fixture.test",)]
    assert by_table["customers"].rows_deduplicated == 1
    # Exact duplicate transaction is measured, then deduplicated.
    assert by_table["transactions"].rows_deduplicated == 1
    dup = q(fresh_db, "SELECT failed FROM _dq_results WHERE table_name='transactions' AND check_name='pk_duplicates_in_batch'")
    assert dup == [(1,)]
    assert q(fresh_db, "SELECT count(*) FROM transactions") == [(10,)]
    # Row- and partition-level lineage.
    assert q(fresh_db, "SELECT count(*) FROM transactions WHERE _source_file IS NULL OR _run_id IS NULL") == [(0,)]
    assert q(fresh_db, "SELECT count(DISTINCT partition_date) FROM _partition_log WHERE table_name='transactions'") == [(3,)]
    assert q(fresh_db, "SELECT count(*) FROM _ingestion_log WHERE status='success'") == [(len(SERVING),)]
    # Contract types from the dictionary were applied.
    assert q(fresh_db, "SELECT data_type FROM information_schema.columns WHERE table_name='transactions' AND column_name='amount'") == [("DECIMAL(15,2)",)]
    # Warn-level rules are measured: one credit card is missing days_past_due.
    assert q(fresh_db, "SELECT failed FROM _dq_results WHERE check_name='rule:credit_fields_present'") == [(1,)]


def test_lineage_times_are_utc_whatever_the_machine_time_zone(fresh_db):
    """started_at, finished_at and _ingested_at are plain TIMESTAMPs. DuckDB stores a UTC time in them converted to
    the machine's zone (Buenos Aires on a laptop, UTC on the deploy), so the same load would read hours apart."""
    from datetime import datetime, timezone

    build_fixture_warehouse()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    finished = q(fresh_db, "SELECT max(finished_at) FROM _ingestion_log")[0][0]
    ingested = q(fresh_db, "SELECT max(_ingested_at) FROM transactions")[0][0]
    assert abs((now - finished).total_seconds()) < 300 and abs((now - ingested).total_seconds()) < 300


def test_late_arriving_partition_updates_in_place_and_is_idempotent(fresh_db):
    build_fixture_warehouse()
    before = q(fresh_db, "SELECT count(*) FROM transactions")[0][0]

    _, [late] = run_pipeline(["transactions"], RunConfig(source="local", raw_dir=FIXTURES / "raw_late", only_date=date(2024, 1, 16)))
    assert (late.rows_new, late.rows_updated) == (1, 3)
    assert q(fresh_db, "SELECT amount FROM transactions WHERE transaction_id='TXN-FIX0009'")[0][0] == pytest.approx(54.00)
    assert q(fresh_db, "SELECT count(*) FROM transactions")[0][0] == before + 1

    _, [replay] = run_pipeline(["transactions"], RunConfig(source="local", raw_dir=FIXTURES / "raw_late", only_date=date(2024, 1, 16)))
    assert (replay.rows_new, replay.rows_updated) == (0, 4)
    assert q(fresh_db, "SELECT count(*) FROM transactions")[0][0] == before + 1


def test_incremental_reads_only_the_lookback_window(fresh_db):
    build_fixture_warehouse()
    _, [inc] = run_pipeline(["transactions"], RunConfig(source="local", raw_dir=FIXTURES / "raw", incremental=True, lookback_days=1))
    assert inc.partitions == 2  # watermark 2024-01-16 minus 1 day -> 15th and 16th
    assert inc.rows_new == 0
    assert q(fresh_db, "SELECT mode FROM _ingestion_log WHERE table_name='transactions' ORDER BY started_at DESC LIMIT 1") == [("incremental",)]


def test_quality_gate_rolls_back_then_quarantines_under_threshold(fresh_db):
    build_fixture_warehouse()
    before = q(fresh_db, "SELECT count(*) FROM transactions")[0][0]
    bad = RunConfig(source="local", raw_dir=FIXTURES / "raw_bad")

    with pytest.raises(PipelineError) as exc:
        run_pipeline(["transactions"], bad)
    assert isinstance(exc.value.cause, DataQualityError) and exc.value.table == "transactions"
    assert q(fresh_db, "SELECT count(*) FROM transactions")[0][0] == before
    assert q(fresh_db, "SELECT count(*) FROM _ingestion_log WHERE status='failed'") == [(1,)]

    bad.max_quarantine_rate = 0.5
    _, [r] = run_pipeline(["transactions"], bad)
    assert (r.rows_quarantined, r.rows_new) == (2, 3)
    errors = dict(q(fresh_db, "SELECT transaction_id, _row_errors FROM _quarantine_transactions"))
    assert "rule:status_enum" in errors["TXN-FIX0102"]
    assert "cast:amount" in errors["TXN-FIX0103"]


def test_schema_evolution_adds_new_column(fresh_db, tmp_path):
    build_fixture_warehouse()
    raw = tmp_path / "raw_evolved"
    part = raw / "transactions" / "year=2024" / "month=01" / "day=18"
    part.mkdir(parents=True)
    src = FIXTURES / "raw" / "transactions" / "year=2024" / "month=01" / "day=16" / "transactions_20240116.csv"
    lines = src.read_text(encoding="utf-8").splitlines()
    lines = [lines[0] + ",loyalty_points"] + [l.replace("2024-01-16", "2024-01-18").replace("TXN-FIX00", "TXN-EVO00") + ",7" for l in lines[1:]]
    (part / "transactions_20240118.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    _, [r] = run_pipeline(["transactions"], RunConfig(source="local", raw_dir=raw))
    drift = [c for c in r.checks if c.check == "schema_new_columns"][0]
    assert drift.failed == 1 and drift.detail == "loyalty_points"
    assert q(fresh_db, "SELECT count(*) FROM transactions WHERE loyalty_points = 7") == [(3,)]


@pytest.mark.integration
def test_s3_partition_replay_is_idempotent(fresh_db, tmp_path):
    cfg = RunConfig(source="s3", raw_dir=tmp_path / "raw", only_date=date(2023, 6, 17))
    _, [first] = run_pipeline(["transactions"], cfg)
    _, [second] = run_pipeline(["transactions"], cfg)
    assert first.rows_new > 0 and second.rows_new == 0
    assert q(fresh_db, "SELECT count(*) FROM transactions")[0][0] == first.rows_new
    shutil.rmtree(tmp_path / "raw", ignore_errors=True)
