"""Contract execution and data-quality measurement for one staged batch.

Flow for every table load (driven by data/pipeline.py):
  raw staging (all columns as read) --schema_drift-->
  typed staging (TRY_CAST to COLUMN_TYPES, plus `_row_errors`) --measure-->
  quarantine rows with any error-level violation --> clean rows go to upsert.
Every check becomes a CheckResult persisted to `_dq_results` and the JSON
report, with an explicit severity: `error` quarantines rows (and fails the
load above a quarantine-rate threshold), `warn` is measured and reported,
`info` is a profile metric with no pass/fail.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import duckdb

from data.contracts import (
    COLUMN_TYPES,
    CROSS_TABLE_CHECKS,
    DOMAIN_RULES,
    NOT_NULL_COLUMNS,
    PRIMARY_KEYS,
    ROW_MODELS,
)

LINEAGE_COLUMNS = ("_source_file", "_run_id", "_ingested_at")


class DataQualityError(Exception):
    pass


@dataclass
class CheckResult:
    table: str
    check: str
    category: str
    severity: str  # error | warn | info
    failed: int
    total: int
    detail: str = ""

    @property
    def rate(self) -> float:
        return round(self.failed / self.total, 6) if self.total else 0.0

    @property
    def passed(self) -> bool | None:
        return None if self.severity == "info" else self.failed == 0

    def as_dict(self) -> dict:
        return {**asdict(self), "rate": self.rate, "passed": self.passed}


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _columns(con: duckdb.DuckDBPyConnection, relation: str) -> list[str]:
    return [r[0] for r in con.execute(f"DESCRIBE {relation}").fetchall()]


def schema_drift(con, raw: str, table: str) -> list[CheckResult]:
    raw_cols = set(_columns(con, raw)) - set(LINEAGE_COLUMNS)
    contract_cols = set(COLUMN_TYPES[table])
    required = set(NOT_NULL_COLUMNS.get(table, [])) | set(PRIMARY_KEYS[table])
    missing_required = sorted(required - raw_cols)
    missing_optional = sorted((contract_cols - required) - raw_cols)
    extra = sorted(raw_cols - contract_cols)
    n = len(contract_cols)
    return [
        CheckResult(table, "schema_missing_required_columns", "schema", "error", len(missing_required), n, ",".join(missing_required)),
        CheckResult(table, "schema_missing_optional_columns", "schema", "warn", len(missing_optional), n, ",".join(missing_optional)),
        CheckResult(table, "schema_new_columns", "schema", "warn", len(extra), n, ",".join(extra)),
    ]


def build_typed_staging(con, raw: str, typed: str, table: str) -> None:
    """TRY_CAST every contract column; unknown raw columns (schema evolution)
    pass through untouched so they aren't silently dropped."""
    raw_cols = set(_columns(con, raw))
    select = []
    for col, typ in COLUMN_TYPES[table].items():
        select.append(f"TRY_CAST({_q(col)} AS {typ}) AS {_q(col)}" if col in raw_cols else f"CAST(NULL AS {typ}) AS {_q(col)}")
    for col in sorted(raw_cols - set(COLUMN_TYPES[table]) - set(LINEAGE_COLUMNS)):
        select.append(_q(col))
    select += [_q(c) for c in LINEAGE_COLUMNS if c in raw_cols]

    # Row-level error list, computed in the same scan as the casts (so it's
    # row-aligned by construction): cast failures and NOT NULL violations
    # judged on raw values, then error-level domain rules on typed values.
    raw_errs = []
    for col in COLUMN_TYPES[table]:
        if col in raw_cols:
            raw_errs.append(
                f"CASE WHEN {_q(col)} IS NOT NULL AND TRY_CAST({_q(col)} AS {COLUMN_TYPES[table][col]}) IS NULL "
                f"THEN 'cast:{col}' END"
            )
    for col in NOT_NULL_COLUMNS.get(table, []):
        raw_errs.append(f"CASE WHEN {_q(col)} IS NULL THEN 'not_null:{col}' END" if col in raw_cols else f"'not_null:{col}'")
    step1 = f"{typed}__s1"
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE {step1} AS SELECT {', '.join(select)}, "
        f"concat_ws(',', {', '.join(raw_errs) if raw_errs else 'NULL'}) AS _raw_errors FROM {raw}"
    )
    domain_errs = [
        f"CASE WHEN NOT coalesce(({pred}), false) THEN 'rule:{name}' END"
        for name, pred, sev in DOMAIN_RULES.get(table, []) if sev == "error"
    ]
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {typed} AS
        SELECT * EXCLUDE (_raw_errors),
               concat_ws(',', {', '.join(domain_errs) if domain_errs else 'NULL'},
                         NULLIF(_raw_errors, '')) AS _row_errors
        FROM {step1}
    """)
    con.execute(f"DROP TABLE {step1}")


def measure(con, raw: str, typed: str, table: str) -> list[CheckResult]:
    total = con.execute(f"SELECT count(*) FROM {typed}").fetchone()[0]
    out: list[CheckResult] = []
    if total == 0:
        return [CheckResult(table, "row_count", "profile", "info", 0, 0, "empty batch")]

    pk = ", ".join(_q(c) for c in PRIMARY_KEYS[table])
    dups = con.execute(f"SELECT coalesce(sum(c - 1), 0) FROM (SELECT count(*) c FROM {typed} GROUP BY {pk}) WHERE c > 1").fetchone()[0]
    out.append(CheckResult(table, "pk_duplicates_in_batch", "uniqueness", "warn", int(dups), total,
                           "exact-key duplicates before dedup (latest record wins)"))

    raw_cols = set(_columns(con, raw))
    for col, typ in COLUMN_TYPES[table].items():
        if col not in raw_cols:
            continue
        failed = con.execute(
            f"SELECT count(*) FROM {raw} WHERE {_q(col)} IS NOT NULL AND TRY_CAST({_q(col)} AS {typ}) IS NULL"
        ).fetchone()[0]
        if failed:
            out.append(CheckResult(table, f"type_cast:{col}", "type", "error", failed, total, f"expected {typ}"))

    for col in NOT_NULL_COLUMNS.get(table, []):
        failed = con.execute(f"SELECT count(*) FROM {typed} WHERE {_q(col)} IS NULL").fetchone()[0]
        out.append(CheckResult(table, f"not_null:{col}", "not_null", "error", failed, total))

    not_null = set(NOT_NULL_COLUMNS.get(table, []))
    for col in COLUMN_TYPES[table]:
        if col in not_null:
            continue
        nulls = con.execute(f"SELECT count(*) FROM {typed} WHERE {_q(col)} IS NULL").fetchone()[0]
        out.append(CheckResult(table, f"null_rate:{col}", "profile", "info", nulls, total))

    for name, pred, sev in DOMAIN_RULES.get(table, []):
        failed = con.execute(f"SELECT count(*) FROM {typed} WHERE NOT coalesce(({pred}), false)").fetchone()[0]
        out.append(CheckResult(table, f"rule:{name}", "domain", sev, failed, total, pred))
    return out


def quarantine(con, typed: str, table: str, run_id: str) -> int:
    bad = con.execute(f"SELECT count(*) FROM {typed} WHERE _row_errors <> ''").fetchone()[0]
    if bad:
        qt = f"_quarantine_{table}"
        con.execute(f"CREATE TABLE IF NOT EXISTS {qt} AS SELECT *, CAST(NULL AS VARCHAR) AS _quarantine_run FROM {typed} WHERE 1=0")
        con.execute(f"INSERT INTO {qt} BY NAME SELECT *, '{run_id}' AS _quarantine_run FROM {typed} WHERE _row_errors <> ''")
    return bad


def pydantic_sample(con, clean: str, table: str, n: int = 1000) -> CheckResult:
    model = ROW_MODELS[table]
    cur = con.execute(f"SELECT * FROM {clean} USING SAMPLE {n} ROWS")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    failures, first = 0, ""
    for row in rows:
        try:
            model.model_validate(dict(zip(cols, row)))
        except Exception as exc:  # noqa: BLE001 - pydantic ValidationError; we only count
            failures += 1
            first = first or str(exc).splitlines()[0]
    return CheckResult(table, "pydantic_row_contract_sample", "contract_sample", "error", failures, len(rows), first)


def cross_table(con, table: str) -> list[CheckResult]:
    existing = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    out = []
    for name, needs, sql in CROSS_TABLE_CHECKS.get(table, []):
        if not set(needs) <= existing:
            continue
        failed, total = con.execute(sql).fetchone()
        out.append(CheckResult(table, f"cross:{name}", "cross_table", "warn", int(failed or 0), int(total or 0)))
    return out
