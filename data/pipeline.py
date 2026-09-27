"""LATAM Bank dataset -> DuckDB warehouse, with contracts, lineage and freshness.

Per table, one transaction:
  fetch (S3 or local) -> raw staging -> schema-drift check -> typed staging
  (TRY_CAST to the dictionary's types) -> measure DQ -> quarantine error rows
  -> dedup (latest record wins) -> upsert by primary key -> cross-table checks
  -> lineage rows in _ingestion_log / _partition_log, results in _dq_results.
A load whose quarantine rate exceeds --max-quarantine-rate, or that is
missing a required column, is rolled back (the warehouse keeps its previous
state). Every loaded row carries _source_file / _run_id / _ingested_at.

Update/freshness policy (see docs/data_quality.md):
- Daily partitions are the unit of incremental load. `--incremental` reloads
  everything from (watermark - lookback_days) onward, so partitions that
  arrive late or get re-delivered are absorbed; upsert-by-PK makes replays
  idempotent (tested in tests/test_pipeline.py with a labeled fixture).
- The serving layer reports the warehouse's as-of date with every answer.

Profiles: `serving` = tables the agent queries; `analysis` = contact-center
tables used only for the baseline/demand analysis (docs/data_evidence.md).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from data.contracts import CONTRACT_DEVIATIONS, CONTRACT_VERSION, DEDUP_ORDER, PRIMARY_KEYS
from data.quality import (
    CheckResult,
    DataQualityError,
    build_typed_staging,
    cross_table,
    measure,
    pydantic_sample,
    quarantine,
    schema_drift,
)
from data.sources import make_source

load_dotenv(override=False)


@dataclass(frozen=True)
class TableSpec:
    name: str
    kind: str  # flat | partitioned
    location: str  # filename for flat, prefix for partitioned
    profile: str  # serving | analysis
    customer_scoped: bool = False


# Load order matters: sampling and cross-table checks need parents first.
TABLES = [
    TableSpec("branches", "flat", "branches.csv", "serving"),
    TableSpec("daily_exchange_rates", "flat", "daily_exchange_rates.csv", "serving"),
    TableSpec("customers", "flat", "customers.csv", "serving"),
    TableSpec("products", "flat", "products.csv", "serving", customer_scoped=True),
    TableSpec("transactions", "partitioned", "transactions", "serving", customer_scoped=True),
    TableSpec("call_center_interactions", "partitioned", "call_center_interactions", "analysis", customer_scoped=True),
    TableSpec("call_transcripts", "partitioned", "call_transcripts", "analysis", customer_scoped=True),
    TableSpec("satisfaction_surveys", "partitioned", "satisfaction_surveys", "analysis", customer_scoped=True),
]
SPECS = {t.name: t for t in TABLES}


@dataclass
class RunConfig:
    source: str = "s3"
    raw_dir: Path = field(default_factory=lambda: Path(os.environ.get("RAW_DATA_DIR", "data/raw")))
    only_date: date | None = None
    since: date | None = None
    until: date | None = None
    incremental: bool = False
    lookback_days: int = 3
    sample_customers: int | None = None
    max_quarantine_rate: float = 0.01


@dataclass
class LoadResult:
    table: str
    partitions: int
    rows_staged: int
    rows_quarantined: int
    rows_deduplicated: int
    rows_new: int
    rows_updated: int
    checks: list[CheckResult]
    seconds: float


def duckdb_path() -> str:
    path = os.environ.get("DUCKDB_PATH", "data/warehouse/bank.duckdb")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(duckdb_path(), read_only=read_only)
    con.execute(f"SET memory_limit='{os.environ.get('DUCKDB_MEMORY_LIMIT', '2GB')}'")
    con.execute("SET preserve_insertion_order=false")
    return con


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:  # noqa: BLE001 - not a git checkout (e.g. inside the container)
        return os.environ.get("GIT_SHA", "unknown")


def ensure_meta_tables(con) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS _ingestion_log (
        run_id VARCHAR, table_name VARCHAR, mode VARCHAR, source_root VARCHAR, n_files INTEGER, n_bytes BIGINT,
        partition_min DATE, partition_max DATE, rows_staged BIGINT, rows_quarantined BIGINT,
        rows_deduplicated BIGINT, rows_new BIGINT, rows_updated BIGINT, status VARCHAR, error VARCHAR,
        contract_version VARCHAR, code_version VARCHAR, params VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS _partition_log (
        run_id VARCHAR, table_name VARCHAR, partition_date DATE, source_uri VARCHAR, n_bytes BIGINT, loaded_at TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS _dq_results (
        run_id VARCHAR, table_name VARCHAR, check_name VARCHAR, category VARCHAR, severity VARCHAR,
        failed BIGINT, total BIGINT, rate DOUBLE, passed BOOLEAN, detail VARCHAR, measured_at TIMESTAMP)""")


def _table_exists(con, name: str) -> bool:
    return bool(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]).fetchone()[0])


def watermark(con, table: str) -> date | None:
    if not _table_exists(con, "_partition_log"):
        return None
    return con.execute("SELECT max(partition_date) FROM _partition_log WHERE table_name = ?", [table]).fetchone()[0]


def _resolve_files(con, spec: TableSpec, cfg: RunConfig, source):
    if spec.kind == "flat":
        return [source.flat(spec.location)], "full"
    since, until, mode = cfg.since, cfg.until, "full"
    if cfg.only_date:
        since = until = cfg.only_date
        mode = "partition"
    elif cfg.incremental:
        wm = watermark(con, spec.name)
        if wm is not None:
            since = max(filter(None, [since, wm - timedelta(days=cfg.lookback_days)]))
        mode = "incremental"
    return source.partitions(spec.location, since=since, until=until), mode


def _upsert(con, table: str, clean: str) -> tuple[int, int, int]:
    """Dedup the clean batch (latest record wins), then delete-and-insert by PK.
    Returns (rows_deduplicated, rows_new, rows_updated)."""
    pk = PRIMARY_KEYS[table]
    pk_sql = ", ".join(pk)
    cols = [r[0] for r in con.execute(f"DESCRIBE {clean}").fetchall() if r[0] != "_row_errors"]
    order = f"{DEDUP_ORDER[table]} DESC NULLS LAST, " if table in DEDUP_ORDER else ""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {clean}_dedup AS
        SELECT {', '.join(f'"{c}"' for c in cols)} FROM (
            SELECT *, row_number() OVER (PARTITION BY {pk_sql} ORDER BY {order}_source_file DESC) AS _rn FROM {clean}
        ) WHERE _rn = 1
    """)
    n_clean = con.execute(f"SELECT count(*) FROM {clean}").fetchone()[0]
    n_dedup = con.execute(f"SELECT count(*) FROM {clean}_dedup").fetchone()[0]

    if not _table_exists(con, table):
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM {clean}_dedup WHERE 1=0")
        con.execute(f"ALTER TABLE {table} ADD PRIMARY KEY ({pk_sql})")
    else:
        # Schema evolution: new columns in the batch are added, not dropped.
        existing = {r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()}
        for name, typ, *_ in con.execute(f"DESCRIBE {clean}_dedup").fetchall():
            if name not in existing:
                con.execute(f'ALTER TABLE {table} ADD COLUMN "{name}" {typ}')

    join = " AND ".join(f"t.{c} = s.{c}" for c in pk)
    n_updated = con.execute(f"SELECT count(*) FROM {table} t JOIN {clean}_dedup s ON {join}").fetchone()[0]
    con.execute(f"DELETE FROM {table} t USING {clean}_dedup s WHERE {join}")
    con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM {clean}_dedup")
    return n_clean - n_dedup, n_dedup - n_updated, n_updated


def load_table(con, spec: TableSpec, cfg: RunConfig, run_id: str, source, sample_mode: bool) -> LoadResult:
    started = time.time()
    started_at = datetime.now(timezone.utc)
    files, mode = _resolve_files(con, spec, cfg, source)
    raw, typed, clean = f"raw_{spec.name}", f"typed_{spec.name}", f"clean_{spec.name}"
    params = {"since": cfg.since, "until": cfg.until, "only_date": cfg.only_date, "lookback_days": cfg.lookback_days,
              "sample_customers": cfg.sample_customers, "sample_mode": sample_mode}
    root = str(Path(cfg.raw_dir).resolve()) + "/"

    if not files:
        return LoadResult(spec.name, 0, 0, 0, 0, 0, 0, [], time.time() - started)

    con.execute("BEGIN TRANSACTION")
    try:
        paths = ", ".join("'" + str(f.local_path.resolve()).replace("'", "''") + "'" for f in files)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE {raw} AS
            SELECT * EXCLUDE (filename), replace(filename, '{root}', '') AS _source_file,
                   '{run_id}' AS _run_id, now()::TIMESTAMP AS _ingested_at
            FROM read_csv_auto([{paths}], union_by_name=true, filename=true, hive_partitioning=false)
        """)
        checks = schema_drift(con, raw, spec.name)
        if checks[0].failed:
            raise DataQualityError(f"{spec.name}: missing required columns {checks[0].detail}")
        build_typed_staging(con, raw, typed, spec.name)

        if sample_mode and spec.name == "customers":
            con.execute(f"""DELETE FROM {typed} WHERE customer_id NOT IN (
                SELECT customer_id FROM {typed} ORDER BY md5(customer_id) LIMIT {int(cfg.sample_customers)})""")
        elif sample_mode and spec.customer_scoped and _table_exists(con, "customers"):
            con.execute(f"DELETE FROM {typed} WHERE customer_id NOT IN (SELECT customer_id FROM customers)")

        checks += measure(con, raw, typed, spec.name)
        staged = con.execute(f"SELECT count(*) FROM {typed}").fetchone()[0]
        n_quarantined = quarantine(con, typed, spec.name, run_id)
        q_rate = n_quarantined / staged if staged else 0.0
        checks.append(CheckResult(spec.name, "quarantine_rate", "gate", "error" if q_rate > cfg.max_quarantine_rate else "info",
                                  n_quarantined, staged, f"threshold={cfg.max_quarantine_rate}"))
        if q_rate > cfg.max_quarantine_rate:
            raise DataQualityError(f"{spec.name}: quarantine rate {q_rate:.2%} > {cfg.max_quarantine_rate:.2%}")

        con.execute(f"CREATE OR REPLACE TEMP TABLE {clean} AS SELECT * EXCLUDE (_row_errors) FROM {typed} WHERE _row_errors = ''")
        if staged - n_quarantined > 0:
            checks.append(pydantic_sample(con, clean, spec.name))
        n_dedup, n_new, n_updated = _upsert(con, spec.name, clean)
        checks += cross_table(con, spec.name)

        now = datetime.now(timezone.utc)
        parts = [f for f in files if f.partition]
        if parts:
            con.executemany(
                "INSERT INTO _partition_log VALUES (?, ?, ?, ?, ?, ?)",
                [(run_id, spec.name, f.partition, f.uri, f.size, now) for f in parts],
            )
        con.execute(
            "INSERT INTO _ingestion_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'success', NULL, ?, ?, ?, ?, ?)",
            [run_id, spec.name, "sample" if sample_mode else mode, files[0].uri.rsplit("/", 1)[0], len(files),
             sum(f.size for f in files), min((f.partition for f in parts), default=None),
             max((f.partition for f in parts), default=None), staged, n_quarantined, n_dedup, n_new, n_updated,
             CONTRACT_VERSION, _git_sha(), json.dumps(params, default=str), started_at, now],
        )
        con.executemany(
            "INSERT INTO _dq_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(run_id, c.table, c.check, c.category, c.severity, c.failed, c.total, c.rate, c.passed, c.detail[:500], now) for c in checks],
        )
        con.execute("COMMIT")
    except Exception as exc:
        con.execute("ROLLBACK")
        con.execute(
            "INSERT INTO _ingestion_log (run_id, table_name, mode, status, error, contract_version, code_version, params, started_at, finished_at) "
            "VALUES (?, ?, ?, 'failed', ?, ?, ?, ?, ?, ?)",
            [run_id, spec.name, mode, str(exc)[:1000], CONTRACT_VERSION, _git_sha(), json.dumps(params, default=str),
             started_at, datetime.now(timezone.utc)],
        )
        raise
    finally:
        for t in (raw, typed, clean, f"{clean}_dedup"):
            con.execute(f"DROP TABLE IF EXISTS {t}")

    return LoadResult(spec.name, len(files), staged, n_quarantined, n_dedup, n_new, n_updated, checks, time.time() - started)


class PipelineError(Exception):
    def __init__(self, run_id: str, table: str, results: list[LoadResult], cause: Exception):
        super().__init__(f"{table}: {cause}")
        self.run_id, self.table, self.results, self.cause = run_id, table, results, cause


def run_pipeline(tables: list[str], cfg: RunConfig) -> tuple[str, list[LoadResult]]:
    """Fail-fast: a failed table stops the run (children depend on parents),
    earlier tables stay committed. Raises PipelineError carrying partial results."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    source = make_source(cfg.source, cfg.raw_dir)
    con = get_connection()
    results = []
    try:
        ensure_meta_tables(con)
        sample_mode = cfg.sample_customers is not None
        for spec in (SPECS[t] for t in tables):
            try:
                results.append(load_table(con, spec, cfg, run_id, source, sample_mode))
            except DataQualityError as exc:
                raise PipelineError(run_id, spec.name, results, exc) from exc
    finally:
        con.close()
    return run_id, results


def write_report(run_id: str, results: list[LoadResult], path: str, failure: dict | None = None) -> dict:
    checks = [c.as_dict() for r in results for c in r.checks]
    report = {
        "run_id": run_id,
        "contract_version": CONTRACT_VERSION,
        "code_version": _git_sha(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tables": {
            r.table: {"partitions": r.partitions, "rows_staged": r.rows_staged, "rows_quarantined": r.rows_quarantined,
                      "rows_deduplicated": r.rows_deduplicated, "rows_new": r.rows_new, "rows_updated": r.rows_updated,
                      "seconds": round(r.seconds, 2)}
            for r in results
        },
        "summary": {
            "status": "failed" if failure else "success",
            "errors_failed": sum(1 for c in checks if c["severity"] == "error" and c["passed"] is False),
            "warnings_failed": sum(1 for c in checks if c["severity"] == "warn" and c["passed"] is False),
            "checks_run": len(checks),
        },
        "failure": failure,
        "contract_deviations": CONTRACT_DEVIATIONS,
        "checks": checks,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def _date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def main() -> None:
    p = argparse.ArgumentParser(description="Ingest the LATAM Bank dataset into DuckDB with contracts + lineage")
    p.add_argument("--profile", choices=["serving", "analysis", "all"], default="serving")
    p.add_argument("--tables", nargs="*", help="explicit table list (overrides --profile)")
    p.add_argument("--source", choices=["s3", "local"], default="s3")
    p.add_argument("--raw-dir", default=os.environ.get("RAW_DATA_DIR", "data/raw"))
    p.add_argument("--date", help="load a single daily partition (YYYY-MM-DD)")
    p.add_argument("--since", help="first partition date to load (YYYY-MM-DD)")
    p.add_argument("--until", help="last partition date to load (YYYY-MM-DD)")
    p.add_argument("--incremental", action="store_true", help="load from (watermark - lookback) onward")
    p.add_argument("--lookback-days", type=int, default=3)
    p.add_argument("--sample-customers", type=int, help="deterministic md5-ordered customer sample (demo deploys)")
    p.add_argument("--max-quarantine-rate", type=float, default=0.01)
    p.add_argument("--report", default="data/reports/quality_report.json")
    a = p.parse_args()

    tables = a.tables or [t.name for t in TABLES if a.profile == "all" or t.profile == a.profile]
    cfg = RunConfig(source=a.source, raw_dir=Path(a.raw_dir), only_date=_date(a.date), since=_date(a.since),
                    until=_date(a.until), incremental=a.incremental, lookback_days=a.lookback_days,
                    sample_customers=a.sample_customers, max_quarantine_rate=a.max_quarantine_rate)
    try:
        run_id, results = run_pipeline(tables, cfg)
        failure = None
    except PipelineError as exc:
        run_id, results, failure = exc.run_id, exc.results, {"table": exc.table, "error": str(exc.cause)}
    report = write_report(run_id, results, a.report, failure)
    for r in results:
        failed = [c for c in r.checks if c.passed is False]
        print(f"[{r.table}] files={r.partitions} staged={r.rows_staged} quarantined={r.rows_quarantined} "
              f"dedup={r.rows_deduplicated} new={r.rows_new} updated={r.rows_updated} "
              f"failed_checks={len(failed)} ({r.seconds:.1f}s)")
    print(f"run_id={run_id} summary={report['summary']} report={a.report}")
    if failure:
        raise SystemExit(f"FAILED at {failure['table']}: {failure['error']}")


if __name__ == "__main__":
    main()
