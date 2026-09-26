"""Idempotency + quality-check tests for the ingestion pipeline.

Uses a throwaway DuckDB file so it never touches the real warehouse.
Requires AWS credentials in the environment (same ones the pipeline uses),
since these are integration tests against the real S3 dataset — this is the
"clearly labeled test fixture" demonstrating update correctness on a
single partitioned day, per the challenge's requirement for static data.

Env var isolation note: DUCKDB_PATH/RAW_DATA_DIR are set via a *module-scoped
MonkeyPatch instance* inside the fixture below, not via bare `os.environ[...]
= ...` at module import time. pytest imports every test module during
collection, before running any test, so a module-level env mutation here
used to leak into tests/test_orchestrator.py (which was then unable to find
the real warehouse) depending on file collection order — and, worse, an
earlier version of this pattern once caused this suite's teardown to delete
the real data/warehouse/bank.duckdb. MonkeyPatch scopes the change to this
fixture's lifetime and guarantees it's undone, regardless of import order.
"""
from pathlib import Path

import pytest

from data import pipeline  # noqa: E402


@pytest.fixture(scope="module")
def clean_test_db():
    mp = pytest.MonkeyPatch()
    mp.setenv("DUCKDB_PATH", "data/warehouse/test_bank.duckdb")
    mp.setenv("RAW_DATA_DIR", "data/raw_test")
    path = Path(pipeline._duckdb_path())
    if path.exists():
        path.unlink()
    yield path
    if path.exists():
        path.unlink()
    mp.undo()


def test_transactions_partition_replay_is_idempotent(clean_test_db):
    con = pipeline.get_connection()
    try:
        result_1 = pipeline.load_partitioned_table(con, "transactions", only_date="2023-06-17")
        count_after_first = con.execute("SELECT count(*) FROM transactions").fetchone()[0]
        assert count_after_first == result_1.rows_inserted
        assert count_after_first > 0

        # Replay the exact same partition: row count must not double.
        result_2 = pipeline.load_partitioned_table(con, "transactions", only_date="2023-06-17")
        count_after_second = con.execute("SELECT count(*) FROM transactions").fetchone()[0]
        assert count_after_second == count_after_first

        # And loading a second, different day should only add that day's rows.
        pipeline.load_partitioned_table(con, "transactions", only_date="2023-06-18")
        count_after_third = con.execute("SELECT count(*) FROM transactions").fetchone()[0]
        assert count_after_third > count_after_second
    finally:
        con.close()


def test_quality_report_has_expected_shape(clean_test_db):
    con = pipeline.get_connection()
    try:
        pipeline.load_flat_table(con, "branches")
        report = pipeline.run_quality_checks(con, "branches")
        assert report["total_rows"] == 350
        assert "duplicate_rate" in report
        assert "null_rates" in report
    finally:
        con.close()
