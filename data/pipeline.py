"""S3 -> DuckDB ingestion pipeline for the LATAM Bank dataset.

Design notes (see /ARCHITECTURE.md for the full rationale):
- Fetches CSVs from S3 via boto3 into a local `data/raw/` staging area, then
  loads them into DuckDB from disk. (DuckDB's httpfs extension needs to
  download itself from extensions.duckdb.org at first use, which is blocked
  in network-restricted environments including this one; boto3 talking
  directly to the S3 API has no such dependency, and the local staging area
  doubles as an audit trail of exactly what was ingested.)
- Only ingests the tables the Account/Payment Inquiries workflow needs:
  customers, products, branches, transactions, daily_exchange_rates.
- Idempotent by primary key: re-running a load (whole table or a single
  transactions partition) deletes-then-reinserts matching keys, so replays
  never duplicate rows. This is what "batch, incremental... according to
  the supplied inputs" and the required update-correctness fixture rest on.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import boto3
import duckdb
from dotenv import load_dotenv

from data.contracts import FOREIGN_KEYS, NOT_NULL_COLUMNS, PRIMARY_KEYS

load_dotenv(override=True)  # this sandbox pre-sets placeholder AWS_* env vars; ours must win

RAW_DIR = Path(os.environ.get("RAW_DATA_DIR", "data/raw"))

FLAT_TABLES = {
    "customers": "customers.csv",
    "products": "products.csv",
    "branches": "branches.csv",
    "daily_exchange_rates": "daily_exchange_rates.csv",
}
PARTITIONED_TABLES = {
    "transactions": "transactions",
}


def _bucket() -> str:
    return os.environ.get("DATASET_BUCKET", "***REMOVED***")


def _duckdb_path() -> str:
    path = os.environ.get("DUCKDB_PATH", "data/warehouse/bank.duckdb")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(_duckdb_path(), read_only=read_only)


def _s3_client():
    # path-style addressing + explicit sigv4: virtual-hosted-style requests get a
    # 403 from the sandbox's egress gateway in this environment.
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-2"),
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        config=boto3.session.Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _get_object_to_file(s3, key: str, dest: Path) -> None:
    # get_object (not download_file/TransferManager): s3transfer's default flexible-checksum
    # request headers get a 403 from this sandbox's egress gateway; a plain GetObject doesn't.
    body = s3.get_object(Bucket=_bucket(), Key=key)["Body"]
    with open(dest, "wb") as f:
        for chunk in body.iter_chunks(chunk_size=8 * 1024 * 1024):
            f.write(chunk)


def fetch_flat_table(table: str) -> Path:
    """Download a flat CSV from S3 to the local raw staging area (skips if already present)."""
    dest = RAW_DIR / FLAT_TABLES[table]
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        _get_object_to_file(_s3_client(), f"data/{FLAT_TABLES[table]}", dest)
    return dest


def fetch_partitioned_table(table: str, only_date: str | None = None) -> Path:
    """Sync a partitioned (daily) table from S3 to the local raw staging area."""
    prefix = f"data/{PARTITIONED_TABLES[table]}/"
    if only_date:
        y, m, d = only_date.split("-")
        prefix = f"{prefix}year={y}/month={m}/day={d}/"
    dest_root = RAW_DIR / PARTITIONED_TABLES[table]
    dest_root.mkdir(parents=True, exist_ok=True)

    s3 = _s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_bucket(), Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len("data/"):]
            local_path = RAW_DIR / rel
            if local_path.exists() and local_path.stat().st_size == obj["Size"]:
                continue
            local_path.parent.mkdir(parents=True, exist_ok=True)
            _get_object_to_file(s3, key, local_path)
    return dest_root


@dataclass
class LoadResult:
    table: str
    rows_staged: int
    rows_inserted: int
    quality: dict = field(default_factory=dict)


def _upsert(con: duckdb.DuckDBPyConnection, table: str, staging: str) -> int:
    pk_cols = PRIMARY_KEYS[table]
    exists = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()[0]
    if not exists:
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM {staging} WHERE 1=0")
        con.execute(f"ALTER TABLE {table} ADD PRIMARY KEY ({', '.join(pk_cols)})")

    # Deduplicate the staged batch itself (dataset documents ~2% duplicate rows):
    # keep the row with the latest last_updated / transaction_date when available,
    # otherwise an arbitrary single row per key.
    order_col = "last_updated" if "last_updated" in con.execute(f"DESCRIBE {staging}").df()["column_name"].tolist() else None
    partition_by = ", ".join(pk_cols)
    if order_col:
        dedup_sql = f"""
            SELECT * EXCLUDE (_rn) FROM (
                SELECT *, row_number() OVER (PARTITION BY {partition_by} ORDER BY {order_col} DESC) AS _rn
                FROM {staging}
            ) WHERE _rn = 1
        """
    else:
        dedup_sql = f"""
            SELECT * EXCLUDE (_rn) FROM (
                SELECT *, row_number() OVER (PARTITION BY {partition_by}) AS _rn
                FROM {staging}
            ) WHERE _rn = 1
        """
    con.execute(f"CREATE OR REPLACE TEMP TABLE {staging}_dedup AS {dedup_sql}")

    join_cond = " AND ".join(f"{table}.{c} = {staging}_dedup.{c}" for c in pk_cols)
    con.execute(f"DELETE FROM {table} USING {staging}_dedup WHERE {join_cond}")
    con.execute(f"INSERT INTO {table} SELECT * FROM {staging}_dedup")
    return con.execute(f"SELECT count(*) FROM {staging}_dedup").fetchone()[0]


def load_flat_table(con: duckdb.DuckDBPyConnection, table: str) -> LoadResult:
    local_path = fetch_flat_table(table)
    con.execute(f"CREATE OR REPLACE TEMP TABLE stg_{table} AS SELECT * FROM read_csv_auto('{local_path}', union_by_name=true)")
    staged = con.execute(f"SELECT count(*) FROM stg_{table}").fetchone()[0]
    inserted = _upsert(con, table, f"stg_{table}")
    quality = run_quality_checks(con, table)
    return LoadResult(table=table, rows_staged=staged, rows_inserted=inserted, quality=quality)


def load_partitioned_table(
    con: duckdb.DuckDBPyConnection, table: str, only_date: str | None = None
) -> LoadResult:
    dest_root = fetch_partitioned_table(table, only_date=only_date)
    if only_date:
        y, m, d = only_date.split("-")
        glob = str(dest_root / f"year={y}" / f"month={m}" / f"day={d}" / "*.csv")
    else:
        glob = str(dest_root / "**" / "*.csv")
    con.execute(f"CREATE OR REPLACE TEMP TABLE stg_{table} AS SELECT * FROM read_csv_auto('{glob}', union_by_name=true)")
    staged = con.execute(f"SELECT count(*) FROM stg_{table}").fetchone()[0]
    inserted = _upsert(con, table, f"stg_{table}")
    quality = run_quality_checks(con, table)
    return LoadResult(table=table, rows_staged=staged, rows_inserted=inserted, quality=quality)


def run_quality_checks(con: duckdb.DuckDBPyConnection, table: str) -> dict:
    total = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    if total == 0:
        return {"total_rows": 0}

    pk_cols = PRIMARY_KEYS.get(table, [])
    dup_count = 0
    if pk_cols:
        group = ", ".join(pk_cols)
        dup_count = con.execute(
            f"SELECT coalesce(sum(cnt - 1), 0) FROM (SELECT count(*) AS cnt FROM {table} GROUP BY {group}) t WHERE cnt > 1"
        ).fetchone()[0]

    null_rates = {}
    for col in NOT_NULL_COLUMNS.get(table, []):
        nulls = con.execute(f"SELECT count(*) FROM {table} WHERE {col} IS NULL").fetchone()[0]
        null_rates[col] = round(nulls / total, 4)

    orphan_rates = {}
    for fk_col, ref_table, ref_col in FOREIGN_KEYS.get(table, []):
        try:
            ref_count = con.execute(f"SELECT count(*) FROM information_schema.tables WHERE table_name = '{ref_table}'").fetchone()[0]
            if not ref_count:
                continue
            orphans = con.execute(
                f"""SELECT count(*) FROM {table} t
                    WHERE t.{fk_col} IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM {ref_table} r WHERE r.{ref_col} = t.{fk_col})"""
            ).fetchone()[0]
            orphan_rates[f"{fk_col}->{ref_table}.{ref_col}"] = round(orphans / total, 4)
        except duckdb.Error:
            continue

    return {
        "total_rows": total,
        "duplicate_rate": round(dup_count / total, 4) if total else 0.0,
        "null_rates": null_rates,
        "orphan_rates": orphan_rates,
    }


def run_pipeline(tables: list[str] | None = None, only_date: str | None = None) -> list[LoadResult]:
    tables = tables or list(FLAT_TABLES) + list(PARTITIONED_TABLES)
    con = get_connection()
    results = []
    try:
        for table in tables:
            if table in FLAT_TABLES:
                results.append(load_flat_table(con, table))
            elif table in PARTITIONED_TABLES:
                results.append(load_partitioned_table(con, table, only_date=only_date))
            else:
                raise ValueError(f"Unknown table: {table}")
    finally:
        con.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest LATAM Bank dataset from S3 into DuckDB")
    parser.add_argument("--tables", nargs="*", default=None, help="Subset of tables to load")
    parser.add_argument("--date", default=None, help="Only load this transactions partition (YYYY-MM-DD), for idempotency testing")
    parser.add_argument("--report", default="data/quality_report.json", help="Where to write the quality report")
    args = parser.parse_args()

    results = run_pipeline(tables=args.tables, only_date=args.date)
    report = {r.table: {"rows_staged": r.rows_staged, "rows_inserted": r.rows_inserted, "quality": r.quality} for r in results}
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2, default=str))

    for r in results:
        print(f"[{r.table}] staged={r.rows_staged} inserted(after_dedup)={r.rows_inserted} quality={r.quality}")


if __name__ == "__main__":
    main()
