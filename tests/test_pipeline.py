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

from data.pipeline import TABLES, PipelineError, RunConfig, lineage_summary, run_pipeline, write_report
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


def test_lineage_times_are_utc_whatever_the_machine_time_zone(fresh_db, monkeypatch):
    """started_at, finished_at and _ingested_at are plain TIMESTAMPs. DuckDB stores a UTC time in them converted to
    the machine's zone (Buenos Aires on a laptop, UTC on the deploy), so the same load would read hours apart. The
    load runs as if the machine were in Buenos Aires, so this also bites on a UTC machine such as CI."""
    from datetime import datetime, timezone

    from data import pipeline

    real_connect = duckdb.connect

    def connect_in_buenos_aires(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        con.execute("SET TimeZone = 'America/Buenos_Aires'")  # what DuckDB takes from the machine there
        return con

    with monkeypatch.context() as m:
        m.setattr(pipeline.duckdb, "connect", connect_in_buenos_aires)
        build_fixture_warehouse()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    finished = q(fresh_db, "SELECT max(finished_at) FROM _ingestion_log")[0][0]
    ingested = q(fresh_db, "SELECT max(_ingested_at) FROM transactions")[0][0]
    assert abs((now - finished).total_seconds()) < 300 and abs((now - ingested).total_seconds()) < 300


def test_duckdb_threads_follow_the_environment(fresh_db, monkeypatch):
    """The Render instance loads on one thread: each DuckDB thread holds its own CSV read buffers."""
    from data.pipeline import get_connection

    monkeypatch.setenv("DUCKDB_THREADS", "1")
    con = get_connection()
    try:
        assert int(con.execute("SELECT current_setting('threads')").fetchone()[0]) == 1
    finally:
        con.close()


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


def test_complaints_contract_dedup_lineage_and_report(fresh_db, tmp_path):
    build_fixture_warehouse()

    run_id, [result] = run_pipeline(["complaints"], RunConfig(source="local", raw_dir=FIXTURES / "raw"))

    complaint_spec = next(t for t in TABLES if t.name == "complaints")
    assert (complaint_spec.kind, complaint_spec.location, complaint_spec.profile, complaint_spec.customer_scoped) == (
        "partitioned", "complaints", "analysis", True,
    )
    assert (result.partitions, result.rows_staged, result.rows_deduplicated, result.rows_new) == (2, 8, 1, 7)
    assert q(fresh_db, "SELECT status, process_date FROM complaints WHERE complaint_id='CPL-FIX0005'") == [
        ("In Process", date(2024, 1, 15))
    ]
    assert q(fresh_db, "SELECT data_type FROM information_schema.columns "
                       "WHERE table_name='complaints' AND column_name='claimed_amount'") == [("DECIMAL(15,2)",)]
    assert q(fresh_db, "SELECT count(*) FROM complaints WHERE origin_interaction_id IS NULL") == [(6,)]

    checks = {c.check: c for c in result.checks}
    assert checks["pydantic_row_contract_sample"].failed == 0
    assert (checks["rule:claimed_amount_has_currency"].failed,
            checks["rule:resolved_has_evidence"].failed) == (1, 1)
    assert (checks["cross:fk_affected_product"].failed, checks["cross:fk_affected_product"].total) == (1, 3)
    assert (checks["cross:customer_owns_affected_product"].failed,
            checks["cross:customer_owns_affected_product"].total) == (1, 2)
    assert checks["cross:fk_origin_interaction"].severity == "info"
    assert checks["cross:fk_origin_interaction"].detail == "not run; missing parent tables: call_center_interactions"

    report_path = tmp_path / "complaints-quality.json"
    report = write_report(run_id, [result], str(report_path))
    assert report_path.exists() and report["tables"]["complaints"]["rows_new"] == 7
    assert report["summary"]["checks_not_run"] == 2
    assert report["summary"]["checks_run"] == len(result.checks) - 2
    assert any(c["check"] == "cross:customer_owns_affected_product" and c["failed"] == 1
               for c in report["checks"])
    assert q(fresh_db, "SELECT count(*) FROM _partition_log WHERE table_name='complaints'") == [(2,)]
    assert q(fresh_db, "SELECT count(*) FROM _dq_results WHERE table_name='complaints'")[0][0] == len(result.checks)
    con = duckdb.connect(str(fresh_db), read_only=True)
    try:
        lineage = lineage_summary(con)
    finally:
        con.close()
    assert lineage["checks"]["not_run"] == 2
    assert lineage["checks"]["run"] > len(result.checks) - lineage["checks"]["not_run"]


def test_complaints_re_delivered_partition_updates_and_replays(fresh_db):
    build_fixture_warehouse()
    run_pipeline(["complaints"], RunConfig(source="local", raw_dir=FIXTURES / "raw"))

    cfg = RunConfig(source="local", raw_dir=FIXTURES / "raw_complaints_late", only_date=date(2024, 1, 15))
    _, [late] = run_pipeline(["complaints"], cfg)
    assert (late.rows_new, late.rows_updated) == (1, 1)
    assert q(fresh_db, "SELECT status, resolution_satisfaction FROM complaints "
                       "WHERE complaint_id='CPL-FIX0005'") == [("Resolved", 4)]

    _, [replay] = run_pipeline(["complaints"], cfg)
    assert (replay.rows_new, replay.rows_updated) == (0, 2)
    assert q(fresh_db, "SELECT count(*) FROM complaints") == [(8,)]


def test_complaints_date_filter(fresh_db):
    _, [one_day] = run_pipeline(
        ["complaints"],
        RunConfig(source="local", raw_dir=FIXTURES / "raw", only_date=date(2024, 1, 14)),
    )
    assert (one_day.partitions, one_day.rows_staged, one_day.rows_new) == (1, 7, 7)
    assert all(c.category == "dependency" and c.severity == "info"
               and c.detail.startswith("not run; missing parent tables:")
               for c in one_day.checks if c.check.startswith("cross:"))


def test_complaints_customer_sample_uses_loaded_customers(fresh_db):
    build_fixture_warehouse(sample_customers=2)
    _, [complaints] = run_pipeline(
        ["complaints"], RunConfig(source="local", raw_dir=FIXTURES / "raw", sample_customers=2)
    )
    assert complaints.rows_staged > 0
    assert q(fresh_db, "SELECT count(DISTINCT customer_id) FROM complaints") == [(2,)]
    assert q(fresh_db, "SELECT count(*) FROM complaints c LEFT JOIN customers u USING (customer_id) "
                       "WHERE u.customer_id IS NULL") == [(0,)]


def test_a_sample_reads_only_its_own_customers_rows(fresh_db, tmp_path):
    """A sample keeps its customers' rows from the moment the files are read. Another customer's bad row never reaches the
    checks (it used to be counted against the sample's total), and the window is not copied whole three times: on the
    Render instance those copies spilled 1.4 GB past its 1 GB disk (2026-09-29)."""
    build_fixture_warehouse(sample_customers=2)
    insider = q(fresh_db, "SELECT customer_id, product_id FROM products ORDER BY customer_id, product_id LIMIT 1")[0]
    sampled = {r[0] for r in q(fresh_db, "SELECT customer_id FROM customers")}
    outsider = next(c for c in ("CLI-FIX0001", "CLI-FIX0002", "CLI-FIX0003", "CLI-FIX0005") if c not in sampled)
    src = FIXTURES / "raw_bad" / "transactions" / "year=2024" / "month=01" / "day=17" / "transactions_20240117.csv"
    header, good, _, bad = src.read_text(encoding="utf-8").splitlines()[:4]  # TXN-FIX0101 is clean, TXN-FIX0103 has amount "abc"
    part = tmp_path / "raw" / "transactions" / "year=2024" / "month=01" / "day=17"
    part.mkdir(parents=True)
    rows = [good.replace("PRD-FIX0001,CLI-FIX0001", ",".join(insider[::-1])), bad.replace("CLI-FIX0001", outsider)]
    (part / "transactions_20240117.csv").write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")

    _, [r] = run_pipeline(["transactions"], RunConfig(source="local", raw_dir=tmp_path / "raw", sample_customers=2))
    assert r.rows_staged == 1
    assert not [c for c in r.checks if c.check.startswith("type_cast") and c.failed], "a row outside the sample was measured"


def test_complaints_quality_gate_and_missing_schema_roll_back(fresh_db, tmp_path):
    build_fixture_warehouse()
    run_pipeline(["complaints"], RunConfig(source="local", raw_dir=FIXTURES / "raw"))
    before = q(fresh_db, "SELECT count(*) FROM complaints")[0][0]
    cfg = RunConfig(source="local", raw_dir=FIXTURES / "raw_complaints_bad")

    with pytest.raises(PipelineError) as exc:
        run_pipeline(["complaints"], cfg)
    assert isinstance(exc.value.cause, DataQualityError)
    assert q(fresh_db, "SELECT count(*) FROM complaints") == [(before,)]

    cfg.max_quarantine_rate = 0.5
    _, [result] = run_pipeline(["complaints"], cfg)
    assert (result.rows_quarantined, result.rows_new) == (1, 1)
    errors = q(fresh_db, "SELECT _row_errors FROM _quarantine_complaints WHERE complaint_id='CPL-BAD0001'")[0][0]
    assert "not_null:description" in errors
    assert "rule:priority_enum" in errors
    assert "cast:sla_breached" in errors
    assert "cast:resolution_days" in errors
    assert "cast:resolution_satisfaction" in errors

    raw_missing = tmp_path / "raw_missing"
    part = raw_missing / "complaints" / "year=2024" / "month=01" / "day=15"
    part.mkdir(parents=True)
    src = FIXTURES / "raw" / "complaints" / "year=2024" / "month=01" / "day=15" / "complaints_20240115.csv"
    rows = [line.split(",") for line in src.read_text(encoding="utf-8").splitlines()]
    description = rows[0].index("description")
    (part / src.name).write_text("\n".join(",".join(row[:description] + row[description + 1:]) for row in rows) + "\n",
                                 encoding="utf-8")
    after_quarantine = q(fresh_db, "SELECT count(*) FROM complaints")[0][0]
    with pytest.raises(PipelineError) as exc:
        run_pipeline(["complaints"], RunConfig(source="local", raw_dir=raw_missing))
    assert isinstance(exc.value.cause, DataQualityError) and "missing required columns description" in str(exc.value.cause)
    assert q(fresh_db, "SELECT count(*) FROM complaints") == [(after_quarantine,)]


def test_s3_daily_files_download_in_parallel_once_each_skipping_the_cache(tmp_path, monkeypatch):
    """One at a time, the dataset's 4,392 daily files took hours from a slow link (about 18 a minute): the round
    trips dominate. Two downloads must be in flight at once, each file fetched once, a cached file not at all."""
    import threading

    from data.sources import S3Source

    days = {d: f"data/transactions/year=2024/month=01/day={d:02d}/part-0.csv" for d in (1, 2, 3, 4)}
    body = {key: f"rows of day {d}\n".encode() for d, key in days.items()}
    listing = [{"Key": key, "Size": len(data)} for key, data in body.items()]
    listing.append({"Key": "data/transactions/year=2024/month=01/day=03/_SUCCESS", "Size": 0})
    both_in_flight = threading.Barrier(2, timeout=3)  # sequential downloads break it
    fetched = []

    class Chunks:
        def __init__(self, data: bytes):
            self.data = data

        def iter_chunks(self, chunk_size: int):
            yield self.data

    class FakeS3:
        def get_paginator(self, name):
            return self

        def paginate(self, Bucket, Prefix):
            return [{"Contents": [o for o in listing if o["Key"].startswith(Prefix)]}]

        def get_object(self, Bucket, Key):
            fetched.append(Key)
            both_in_flight.wait()
            return {"Body": Chunks(body[Key])}

    monkeypatch.setattr(S3Source, "_s3", lambda self: FakeS3())
    raw = tmp_path / "raw"
    cached = raw / days[2].removeprefix("data/")
    cached.parent.mkdir(parents=True)
    cached.write_bytes(body[days[2]])  # same size: already downloaded

    files = S3Source(raw, bucket="bucket").partitions("transactions", since=date(2024, 1, 2))

    assert sorted(fetched) == [days[3], days[4]]  # day 1 is outside the window, day 2 is cached, _SUCCESS is no csv
    assert [f.uri for f in files] == [f"s3://bucket/{days[d]}" for d in (2, 3, 4)]
    assert [f.partition for f in files] == [date(2024, 1, d) for d in (2, 3, 4)]
    assert all(f.local_path.read_bytes() == body[days[d]] and f.size == len(body[days[d]])
               for f, d in zip(files, (2, 3, 4)))


@pytest.mark.integration
def test_s3_partition_replay_is_idempotent(fresh_db, tmp_path):
    cfg = RunConfig(source="s3", raw_dir=tmp_path / "raw", only_date=date(2023, 6, 17))
    _, [first] = run_pipeline(["transactions"], cfg)
    _, [second] = run_pipeline(["transactions"], cfg)
    assert first.rows_new > 0 and second.rows_new == 0
    assert q(fresh_db, "SELECT count(*) FROM transactions")[0][0] == first.rows_new
    shutil.rmtree(tmp_path / "raw", ignore_errors=True)
