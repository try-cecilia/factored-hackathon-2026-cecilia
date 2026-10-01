"""Gold: business-ready marts built from the silver tables, each reconciled to the rows it summarizes.

    python -m data.gold                        # build every mart the warehouse has the sources for (DUCKDB_PATH)
    python -m data.gold --verify               # re-check the built marts against silver; exit 1 if one has drifted

Silver is what data/pipeline.py loads (typed, validated, de-duplicated). A mart is a deterministic query over silver, with
a declared grain and two kinds of check run inside the same transaction that writes it:

- the grain is unique (no two rows share the grain columns, NULLs included);
- the mart adds up to the silver rows it summarizes (row counts, and amounts where it carries them).

If any check fails the transaction rolls back and the previous version of the mart is kept. Each build writes one row per
mart to `_gold_log` with the SQL's SHA-256, the silver loads it read (`_ingestion_log` run ids) and the code version, and
stamps every mart row with `_gold_run_id` and `_built_at`. A mart whose source tables are not in the warehouse is skipped
and said so: the serving warehouse of the deployment has no contact-center tables.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import duckdb

from data.pipeline import _git_sha


class GoldError(RuntimeError):
    pass


@dataclass(frozen=True)
class Mart:
    name: str
    grain: tuple[str, ...]
    sources: tuple[str, ...]
    sql: str
    # (name, SQL returning the mart's figure, SQL returning the silver figure it must equal)
    reconcile: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    doc: str = ""


MARTS: tuple[Mart, ...] = (
    Mart(
        name="gold_daily_activity",
        grain=("activity_date", "transaction_country", "currency", "transaction_type", "transaction_status"),
        sources=("transactions",),
        doc="Movements per day, country, currency, type and status: the daily volume and value the agent's data holds.",
        sql="""SELECT CAST(transaction_date AS DATE) AS activity_date, transaction_country, currency, transaction_type, transaction_status,
                      count(*) AS n_transactions, count(DISTINCT customer_id) AS n_customers,
                      sum(abs(amount)) AS total_abs_amount, avg(abs(amount)) AS avg_abs_amount
               FROM transactions GROUP BY 1, 2, 3, 4, 5""",
        reconcile=(
            ("n_transactions", "SELECT coalesce(sum(n_transactions), 0) FROM gold_daily_activity", "SELECT count(*) FROM transactions"),
            ("total_abs_amount", "SELECT coalesce(sum(total_abs_amount), 0) FROM gold_daily_activity", "SELECT coalesce(sum(abs(amount)), 0) FROM transactions"),
        ),
    ),
    Mart(
        name="gold_customer_summary",
        grain=("customer_id",),
        sources=("transactions",),
        doc="One row per customer with movements: how many, over what span, through how many channels, countries and products.",
        sql="""SELECT customer_id, count(*) AS n_transactions, min(transaction_date) AS first_transaction_at,
                      max(transaction_date) AS last_transaction_at, count(DISTINCT channel) AS n_channels,
                      count(DISTINCT transaction_country) AS n_countries, count(DISTINCT currency) AS n_currencies,
                      count(DISTINCT product_id) AS n_products
               FROM transactions GROUP BY customer_id""",
        reconcile=(
            ("n_transactions", "SELECT coalesce(sum(n_transactions), 0) FROM gold_customer_summary", "SELECT count(*) FROM transactions"),
            ("customers", "SELECT count(*) FROM gold_customer_summary", "SELECT count(DISTINCT customer_id) FROM transactions"),
        ),
    ),
    Mart(
        name="gold_contact_demand",
        grain=("month", "country", "channel", "reason_category"),
        sources=("call_center_interactions", "customers"),
        doc="Contacts per month, customer country, channel and reason category, with resolution, follow-up and handling time: the demand the assistant would face.",
        sql="""SELECT CAST(date_trunc('month', c.interaction_date) AS DATE) AS month, cu.country, c.channel, c.reason_category,
                      count(*) AS n_contacts, count(*) FILTER (WHERE c.was_resolved) AS n_resolved,
                      count(*) FILTER (WHERE c.requires_followup) AS n_followup,
                      avg(c.duration_seconds) AS avg_duration_seconds, avg(c.wait_time_seconds) AS avg_wait_seconds
               FROM call_center_interactions c LEFT JOIN customers cu USING (customer_id) GROUP BY 1, 2, 3, 4""",
        reconcile=(
            ("n_contacts", "SELECT coalesce(sum(n_contacts), 0) FROM gold_contact_demand", "SELECT count(*) FROM call_center_interactions"),
            ("n_resolved", "SELECT coalesce(sum(n_resolved), 0) FROM gold_contact_demand",
             "SELECT count(*) FROM call_center_interactions WHERE was_resolved"),
        ),
    ),
)


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()}


def _ensure_log(con) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS _gold_log (
        gold_run_id VARCHAR, mart VARCHAR, status VARCHAR, detail VARCHAR, n_rows BIGINT, grain VARCHAR, sql_sha256 VARCHAR,
        source_runs VARCHAR, code_version VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP)""")


def _source_runs(con, sources: tuple[str, ...]) -> dict[str, str | None]:
    """The latest successful silver load of each source table: the exact data the mart summarizes."""
    if "_ingestion_log" not in _tables(con):
        return dict.fromkeys(sources)
    runs = {}
    for table in sources:
        row = con.execute("SELECT run_id FROM _ingestion_log WHERE table_name = ? AND status = 'success' ORDER BY finished_at DESC LIMIT 1", [table]).fetchone()
        runs[table] = row[0] if row else None
    return runs


def _check(con, mart: Mart) -> list[str]:
    problems = []
    n, distinct = con.execute(f"SELECT count(*), (SELECT count(*) FROM (SELECT DISTINCT {', '.join(mart.grain)} FROM {mart.name})) FROM {mart.name}").fetchone()
    if n != distinct:
        problems.append(f"the grain ({', '.join(mart.grain)}) is not unique: {n} rows, {distinct} distinct")
    for name, gold_sql, silver_sql in mart.reconcile:
        got, expected = con.execute(gold_sql).fetchone()[0], con.execute(silver_sql).fetchone()[0]
        if got != expected:
            problems.append(f"{name}: the mart adds up to {got}, silver has {expected}")
    return problems


def build(con, only: tuple[str, ...] | None = None) -> list[dict]:
    """Build every mart the warehouse has the sources for. Raises GoldError, after logging it, if a check fails."""
    _ensure_log(con)
    gold_run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    results = []
    for mart in MARTS:
        if only and mart.name not in only:
            continue
        started = datetime.now(timezone.utc).replace(tzinfo=None)
        sha = hashlib.sha256(mart.sql.encode()).hexdigest()
        missing = sorted(set(mart.sources) - _tables(con))
        entry = {"mart": mart.name, "status": "skipped", "detail": f"missing source tables: {', '.join(missing)}" if missing else "", "n_rows": None}
        if not missing:
            runs = _source_runs(con, mart.sources)
            con.execute("BEGIN")
            try:
                con.execute(f"CREATE OR REPLACE TABLE {mart.name} AS SELECT m.*, ? AS _gold_run_id, ? AS _built_at FROM ({mart.sql}) AS m", [gold_run_id, started])
                problems = _check(con, mart)
                if problems:
                    raise GoldError(f"{mart.name}: " + "; ".join(problems))
                entry.update(status="built", n_rows=con.execute(f"SELECT count(*) FROM {mart.name}").fetchone()[0])
                con.execute("COMMIT")
            except Exception as exc:
                con.execute("ROLLBACK")
                entry.update(status="failed", detail=str(exc))
            entry["source_runs"] = runs
        _log(con, gold_run_id, mart, entry, sha, started)
        results.append(entry)
        if entry["status"] == "failed":
            raise GoldError(entry["detail"])
    return results


def _log(con, gold_run_id: str, mart: Mart, entry: dict, sha: str, started: datetime) -> None:
    con.execute("INSERT INTO _gold_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [gold_run_id, mart.name, entry["status"], entry["detail"], entry["n_rows"], ",".join(mart.grain), sha,
                 json.dumps(entry.get("source_runs", {})), _git_sha(), started, datetime.now(timezone.utc).replace(tzinfo=None)])


def verify(con) -> list[str]:
    """Re-run the checks on the marts as they are now: a silver reload after the build shows up here as a mismatch."""
    present = _tables(con)
    problems = []
    for mart in MARTS:
        if mart.name in present:
            problems += [f"{mart.name}: {p}" for p in _check(con, mart)]
    return problems


def main() -> None:
    p = argparse.ArgumentParser(description="Build the gold marts from the silver tables and reconcile them")
    p.add_argument("--db", default=os.environ.get("DUCKDB_PATH", "data/warehouse/full.duckdb"))
    p.add_argument("--verify", action="store_true", help="only re-check the marts already built; exit 1 on drift")
    a = p.parse_args()
    con = duckdb.connect(a.db, read_only=a.verify)
    try:
        if a.verify:
            problems = verify(con)
            print("\n".join(problems) or "every built mart still adds up to silver")
            sys.exit(1 if problems else 0)
        for r in build(con):
            print(f"[{r['mart']}] {r['status']}" + (f" rows={r['n_rows']:,}" if r["n_rows"] is not None else "") + (f" ({r['detail']})" if r["detail"] else ""))
    except GoldError as exc:
        raise SystemExit(f"FAILED: {exc}") from exc
    finally:
        con.close()


if __name__ == "__main__":
    main()
