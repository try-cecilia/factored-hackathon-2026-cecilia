"""Buenas prácticas de datos y ML, una afirmación por prueba: contratos, calidad, linaje, frescura, un componente
aprendido contra una línea base y ausencia de fuga.

Cada prueba corresponde a una frase de docs/data_quality.md, EVALUATION.md §2 o LIMITATIONS.md, y falla si esa frase
deja de ser cierta. El prefijo del nombre (`test_contracts_`, `test_quality_`, `test_lineage_`, `test_freshness_`,
`test_learned_`, `test_leakage_`) es el criterio; `python -m eval.validate_data_ml` corre solo este archivo y escribe
docs/evidence/data_ml_validation.md con el resultado y la evidencia (`record_property("evidence", ...)`) de cada una.

Herméticas: warehouse de prueba (tests/fixtures), sin S3 ni claves. Las pruebas que miran un reporte versionado
(data/reports/quality_report.json, eval/reports/intent_classifier.json) lo comparan con el documento que lo cita o lo
vuelven a calcular desde los datos del repo.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import inspect
import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pytest

from agent.llm import intent_classifier
from agent.llm.intent_classifier import load_rows
from agent.policy import intent_guard
from agent.policy.signals import contains_escalation_signal
from agent.tools import account_tools as tools
from agent.tools.errors import DataUnavailable
from data import lineage, pipeline, quality
from data.contracts import (
    COLUMN_TYPES,
    CONTRACT_DEVIATIONS,
    CONTRACT_VERSION,
    DOMAIN_RULES,
    NOT_NULL_COLUMNS,
    PRIMARY_KEYS,
    ROW_MODELS,
)
from data.pipeline import SPECS, PipelineError, RunConfig, file_sha256, run_pipeline, write_report
from eval import evaluate_intent_classifier as evaluation
from eval import leakage
from eval.fake_llm import FakeLLMClient, tool_call_response
from eval.stats import fmt, paired_accuracy
from tests.conftest import FIXTURES, SERVING, build_fixture_warehouse
from tests.test_orchestrator import make

ROOT = Path(__file__).resolve().parent.parent
DATA_QUALITY_DOC = (ROOT / "docs" / "data_quality.md").read_text(encoding="utf-8")
EVALUATION_DOC = (ROOT / "EVALUATION.md").read_text(encoding="utf-8")
LIMITATIONS_DOC = (ROOT / "LIMITATIONS.md").read_text(encoding="utf-8")
QUALITY_REPORT = ROOT / "data" / "reports" / "quality_report.json"
CLASSIFIER_REPORT = ROOT / "eval" / "reports" / "intent_classifier.json"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    path = tmp_path / "w.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(path))
    return path


@pytest.fixture
def own_raw(tmp_path):
    """A private copy of the base fixture, so a test can load it and then change or delete the files."""
    dest = tmp_path / "raw"
    shutil.copytree(FIXTURES / "raw", dest)
    return dest


def q(path, sql, params=None):
    con = duckdb.connect(str(path), read_only=True)
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


def section(doc: str, start: str, end: str) -> str:
    return doc.split(start, 1)[1].split(end, 1)[0]


def thousands(n: int) -> str:
    return f"{n:,}"


# ---------------------------------------------------------------- 1. Contratos


def test_contracts_every_table_has_types_key_row_model_and_they_agree(record_property):
    tables = sorted(SPECS)
    for registry in (COLUMN_TYPES, PRIMARY_KEYS, ROW_MODELS):
        assert sorted(registry) == tables
    for table in tables:
        columns = set(COLUMN_TYPES[table])
        assert set(PRIMARY_KEYS[table]) <= columns, f"{table}: key outside the columns"
        assert set(NOT_NULL_COLUMNS.get(table, [])) <= columns, f"{table}: NOT NULL outside the columns"
        model = ROW_MODELS[table]
        assert set(model.model_fields) <= columns, f"{table}: pydantic field the SQL contract does not know"
        required = {n for n, f in model.model_fields.items() if f.is_required()}
        # The second implementation may not demand what the first lets through, or the sample check would flag valid rows.
        assert required <= set(NOT_NULL_COLUMNS.get(table, [])) | set(PRIMARY_KEYS[table]), f"{table}: {required}"
        for name, _, severity in DOMAIN_RULES.get(table, []):
            assert severity in ("error", "warn"), f"{table}.{name}"
    record_property("evidence", f"{len(tables)} tables: types, key, NOT NULL and pydantic model agree; contract {CONTRACT_VERSION}")
    assert f"contract version {CONTRACT_VERSION}" in DATA_QUALITY_DOC


def test_contracts_the_served_tables_have_the_dictionary_types_and_keys(fresh_db, record_property):
    build_fixture_warehouse()
    checked = 0
    for table in SERVING:
        types = dict(q(fresh_db, "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ?", [table]))
        for column, expected in COLUMN_TYPES[table].items():
            assert types[column] == expected, f"{table}.{column}: {types[column]} instead of {expected}"
            checked += 1
        assert q(fresh_db, "SELECT count(*) FROM (SELECT 1 FROM " + table + " GROUP BY " + ", ".join(PRIMARY_KEYS[table])
                 + " HAVING count(*) > 1)") == [(0,)], f"{table}: duplicate key in the served table"
    record_property("evidence", f"{checked} columns of {len(SERVING)} served tables with the dictionary's type; no repeated keys")


def test_contracts_a_violating_row_is_quarantined_with_its_reason_and_appears_in_the_report(fresh_db, tmp_path, record_property):
    build_fixture_warehouse()
    served_before = q(fresh_db, "SELECT count(*) FROM transactions")[0][0]
    cfg = RunConfig(source="local", raw_dir=FIXTURES / "raw_bad", max_quarantine_rate=0.5)
    run_id, results = run_pipeline(["transactions"], cfg)
    report = write_report(run_id, results, str(tmp_path / "report.json"))

    reasons = dict(q(fresh_db, "SELECT transaction_id, _row_errors FROM _quarantine_transactions"))
    assert set(reasons) == {"TXN-FIX0102", "TXN-FIX0103"}
    assert "rule:status_enum" in reasons["TXN-FIX0102"] and "cast:amount" in reasons["TXN-FIX0103"]
    # Neither reached the served table; the valid rows of the same batch did.
    assert q(fresh_db, "SELECT count(*) FROM transactions WHERE transaction_id IN ('TXN-FIX0102', 'TXN-FIX0103')") == [(0,)]
    assert q(fresh_db, "SELECT count(*) FROM transactions")[0][0] == served_before + 3
    # And the report says so, with the failed error-level checks that caused it.
    on_disk = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert on_disk["tables"]["transactions"]["rows_quarantined"] == 2 and report["summary"]["errors_failed"] >= 2
    failed = {c["check"] for c in on_disk["checks"] if c["severity"] == "error" and c["passed"] is False}
    assert {"rule:status_enum", "type_cast:amount"} <= failed
    assert q(fresh_db, "SELECT DISTINCT _quarantine_run FROM _quarantine_transactions") == [(run_id,)]  # which load set them aside
    persisted = {r[0] for r in q(fresh_db, "SELECT check_name FROM _dq_results WHERE run_id = ? AND passed = false AND severity = 'error'", [run_id])}
    assert {"rule:status_enum", "type_cast:amount"} <= persisted
    record_property("evidence", "2 of 5 rows of the bad batch in _quarantine_transactions with a reason (rule:status_enum, cast:amount); "
                                "failed error checks in the JSON report and in _dq_results; the 3 valid ones were loaded")


def test_contracts_over_the_quarantine_threshold_the_load_stops_and_the_previous_state_stays(fresh_db, tmp_path, monkeypatch, capsys, record_property):
    assert RunConfig().max_quarantine_rate == 0.01 and "1% of the batch" in DATA_QUALITY_DOC
    build_fixture_warehouse()
    before = q(fresh_db, "SELECT md5(string_agg(transaction_id || amount::VARCHAR, ',' ORDER BY transaction_id)) FROM transactions")
    with pytest.raises(PipelineError) as exc:
        run_pipeline(["transactions"], RunConfig(source="local", raw_dir=FIXTURES / "raw_bad"))
    assert "quarantine rate" in str(exc.value.cause)
    assert q(fresh_db, "SELECT md5(string_agg(transaction_id || amount::VARCHAR, ',' ORDER BY transaction_id)) FROM transactions") == before
    assert q(fresh_db, "SELECT count(*) FROM information_schema.tables WHERE table_name = '_quarantine_transactions'") == [(0,)]
    failed_loads = q(fresh_db, "SELECT error FROM _ingestion_log WHERE status = 'failed'")
    assert len(failed_loads) == 1 and "quarantine rate" in failed_loads[0][0]

    # The command a person or a cron job runs: it exits non-zero and leaves a report that says why.
    report = tmp_path / "failed.json"
    monkeypatch.setattr("sys.argv", ["pipeline", "--tables", "transactions", "--source", "local", "--raw-dir",
                                     str(FIXTURES / "raw_bad"), "--report", str(report)])
    with pytest.raises(SystemExit) as stop:
        pipeline.main()
    assert "FAILED at transactions" in str(stop.value)
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["summary"]["status"] == "failed" and body["failure"]["table"] == "transactions"
    capsys.readouterr()
    record_property("evidence", "a batch with 40% quarantined (threshold 1%): PipelineError, served table identical (same md5), "
                                "load 'failed' in _ingestion_log, `python -m data.pipeline` exits with an error and the report says status=failed")


def test_contracts_a_missing_required_column_fails_the_load(fresh_db, own_raw, record_property):
    build_fixture_warehouse()
    for path in (own_raw / "transactions").glob("year=*/month=*/day=*/*.csv"):
        rows = list(csv.reader(open(path, encoding="utf-8")))
        drop = rows[0].index("amount")
        path.write_text("\n".join(",".join(v for i, v in enumerate(r) if i != drop) for r in rows) + "\n", encoding="utf-8")
    before = q(fresh_db, "SELECT count(*) FROM transactions")
    with pytest.raises(PipelineError) as exc:
        run_pipeline(["transactions"], RunConfig(source="local", raw_dir=own_raw))
    assert "missing required columns" in str(exc.value.cause) and "amount" in str(exc.value.cause)
    assert q(fresh_db, "SELECT count(*) FROM transactions") == before
    record_property("evidence", "without the required column `amount` the load fails ('missing required columns') and the table does not change")


def test_contracts_a_value_that_would_be_rounded_to_fit_its_type_is_quarantined_not_stored_rounded(fresh_db, own_raw, record_property):
    """Read from a real CSV, where the reader picks the column type itself (not the all-text table of the unit test)."""
    build_fixture_warehouse(raw_dir=own_raw)
    day = next((own_raw / "transactions").glob("year=2024/month=01/day=16/*.csv"))
    rows = list(csv.reader(open(day, encoding="utf-8")))
    at = rows[0].index("amount")
    rows[1][at] = "200000.005"
    rows[2][at] = "54.500"  # trailing zeros beyond the scale are the same number
    with open(day, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    victim, same = rows[1][0], rows[2][0]
    before = q(fresh_db, "SELECT amount FROM transactions WHERE transaction_id = ?", [victim])
    _, [result] = run_pipeline(["transactions"], RunConfig(source="local", raw_dir=own_raw, only_date=datetime(2024, 1, 16).date(),
                                                          max_quarantine_rate=0.5))
    (reason,), = q(fresh_db, "SELECT _row_errors FROM _quarantine_transactions WHERE transaction_id = ?", [victim])
    assert "cast:amount" in reason
    assert q(fresh_db, "SELECT amount FROM transactions WHERE transaction_id = ?", [victim]) == before  # not overwritten with 200000.01
    assert q(fresh_db, "SELECT amount FROM transactions WHERE transaction_id = ?", [same])[0][0] == pytest.approx(54.5)
    assert any(c.check == "type_cast:amount" and c.failed == 1 and c.severity == "error" for c in result.checks)
    record_property("evidence", "amount='200000.005' in a real CSV: error type_cast:amount, the row is quarantined and not stored as 200000.01; '54.500' is accepted")


def test_contracts_valid_amounts_of_any_magnitude_are_stored_exactly_and_only_a_rounding_one_is_rejected(fresh_db, own_raw, record_property):
    """DuckDB reads a bare 8995304.28 as a DOUBLE, which cannot hold it exactly: the check has to judge the text."""
    import random
    from decimal import Decimal

    build_fixture_warehouse(raw_dir=own_raw)
    template = next((own_raw / "transactions").glob("year=2024/month=01/day=16/*.csv"))
    rows = list(csv.reader(open(template, encoding="utf-8")))
    header, base = rows[0], rows[1]
    rng = random.Random(20260929)
    amounts = ["8995304.28", "9999999999999.99", "0.01", "0.10", "1234567.80", "100", "54.5", "3.00"]
    amounts += [f"{rng.randrange(1, 10 ** rng.randrange(3, 16))}.{rng.randrange(100):02d}" for _ in range(600)]
    amounts = sorted({a for a in amounts if len(a.split(".")[0]) <= 13})
    ids = {f"TXN-SWP{i:04d}": a for i, a in enumerate(amounts)}
    ids["TXN-SWPBAD"] = "200000.005"
    part = own_raw / "transactions" / "year=2024" / "month=01" / "day=18"
    part.mkdir(parents=True)
    out = []
    for txn, amount in ids.items():
        row = list(base)
        row[header.index("transaction_id")], row[header.index("amount")] = txn, amount
        row[header.index("transaction_date")], row[header.index("process_date")] = "2024-01-18 10:00:00", "2024-01-18"
        row[header.index("currency")] = "USD"
        row[header.index("amount_usd")] = ""
        out.append(row)
    with open(part / "transactions_20240118.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([header, *out])
    _, [result] = run_pipeline(["transactions"], RunConfig(source="local", raw_dir=own_raw, only_date=datetime(2024, 1, 18).date(),
                                                          max_quarantine_rate=0.5))
    assert result.rows_quarantined == 1
    assert dict(q(fresh_db, "SELECT transaction_id, _row_errors FROM _quarantine_transactions")) == {"TXN-SWPBAD": "cast:amount"}
    served = {t: a for t, a in q(fresh_db, "SELECT transaction_id, amount::VARCHAR FROM transactions WHERE transaction_id LIKE 'TXN-SWP%'")}
    assert set(served) == set(ids) - {"TXN-SWPBAD"}
    assert all(Decimal(served[t]) == Decimal(ids[t]) for t in served)  # stored as delivered, to the cent
    assert [c.failed for c in result.checks if c.check == "type_cast:amount"] == [1]
    record_property("evidence", f"{len(served)} valid amounts from 0.01 to 9999999999999.99 (8995304.28 included) loaded exactly; "
                                "200000.005 rejected with cast:amount; a single row quarantined")


def test_contracts_the_fixture_warehouse_loads_without_a_single_cast_error(fresh_db, record_property):
    _, results = build_fixture_warehouse()
    assert not [(r.table, c.check) for r in results for c in r.checks if c.check.startswith("type_cast:") or c.check.startswith("cast:")]
    assert sum(r.rows_quarantined for r in results) == 0
    record_property("evidence", f"the fixture's load with no type_cast and no row quarantined ({sum(r.rows_staged for r in results)} rows read)")


def test_contracts_a_truncated_file_cannot_replace_the_rows_it_cuts_off(fresh_db, own_raw, record_property):
    build_fixture_warehouse(raw_dir=own_raw)
    served = q(fresh_db, "SELECT transaction_id, amount FROM transactions ORDER BY transaction_id")
    day = next((own_raw / "transactions").glob("year=2024/month=01/day=15/*.csv"))
    day.write_bytes(day.read_bytes()[:-60])  # cut in the middle of the last row: an interrupted download
    with pytest.raises(PipelineError):  # under the default threshold the load stops
        run_pipeline(["transactions"], RunConfig(source="local", raw_dir=own_raw))
    assert q(fresh_db, "SELECT transaction_id, amount FROM transactions ORDER BY transaction_id") == served
    # Even when every quarantine is tolerated the damaged file's rows do not reach the served table. The CSV reader
    # cannot align a file whose last row is short, so all of that file's rows are set aside (fail closed, not just the cut row).
    _, [result] = run_pipeline(["transactions"], RunConfig(source="local", raw_dir=own_raw, max_quarantine_rate=1.0))
    files = {f for f, in q(fresh_db, "SELECT DISTINCT _source_file FROM _quarantine_transactions")}
    assert result.rows_quarantined > 0 and files == {str(day.relative_to(own_raw))}
    assert q(fresh_db, "SELECT transaction_id, amount FROM transactions ORDER BY transaction_id") == served
    record_property("evidence", f"a file cut in the middle of its last row: with the default threshold the load stops; even tolerating everything, "
                                f"its {result.rows_quarantined} rows go to quarantine (with their source file) and the served table stays identical")


def test_contracts_the_documented_severities_are_the_ones_the_code_assigns(fresh_db, record_property):
    _, results = build_fixture_warehouse()
    _, [bad] = run_pipeline(["transactions"], RunConfig(source="local", raw_dir=FIXTURES / "raw_bad", max_quarantine_rate=0.5))
    seen: dict[str, set[str]] = {}
    for r in [*results, bad]:
        for c in r.checks:
            seen.setdefault(c.category, set()).add(c.severity)
    code = {"Primary-key duplicates in the batch": seen["uniqueness"], "Type conformance": seen["type"],
            "NOT NULL": seen["not_null"], "Null rate of every nullable column": seen["profile"],
            "Domain rules (enums, ranges)": seen["domain"],
            "Pydantic row contract on a 1,000-row sample (an independent second implementation of the contract)": seen["contract_sample"]}
    documented = {}
    for line in section(DATA_QUALITY_DOC, "| Check | Severity |", "5. **Quarantine.**").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] not in ("", "Check") and not set(cells[0]) <= {"-"}:
            documented[cells[0]] = cells[1]
    assert set(documented) == set(code), f"the doc's check table and the code's categories differ: {set(documented) ^ set(code)}"
    expected = {"warn": {"warn"}, "error": {"error"}, "info": {"info"}, "error or warn": {"error", "warn"}}
    for name, severity in documented.items():
        assert code[name] == expected[severity], f"{name}: the doc says {severity}, the code assigns {sorted(code[name])}"
    sample_default = inspect.signature(quality.pydantic_sample).parameters["n"].default
    assert sample_default == 1000
    record_property("evidence", "severity table in docs/data_quality.md == the severities measure/pydantic_sample/quarantine assign; pydantic sample = 1000")


def test_contracts_each_documented_deviation_is_still_measured_as_a_warning(record_property):
    for d in CONTRACT_DEVIATIONS:
        rules = [(n, sev) for n, pred, sev in DOMAIN_RULES[d["table"]] if d["column"] in pred or d["column"] in n]
        assert rules and all(sev == "warn" for _, sev in rules), f"{d['table']}.{d['column']}: {rules}"
        assert d["column"] in DATA_QUALITY_DOC, f"{d['column']} is a deviation the doc does not mention"
    record_property("evidence", f"{len(CONTRACT_DEVIATIONS)} contract deviations: each one is a `warn` rule measured on every load and listed in docs/data_quality.md")


# ---------------------------------------------------------------- 2. Calidad


def test_quality_every_check_is_persisted_and_the_report_counts_them(fresh_db, tmp_path, record_property):
    run_id, results = build_fixture_warehouse()
    report = write_report(run_id, results, str(tmp_path / "r.json"))
    rows = q(fresh_db, "SELECT table_name, check_name, severity, passed FROM _dq_results WHERE run_id = ?", [run_id])
    assert len(rows) == len(report["checks"]) == sum(len(r.checks) for r in results)
    assert all(sev in ("error", "warn", "info") for _, _, sev, _ in rows)
    assert all((passed is None) == (sev == "info") for _, _, sev, passed in rows)
    run = [c for c in report["checks"] if c["category"] != "dependency"]
    assert report["summary"]["checks_run"] == len(run)
    assert report["summary"]["warnings_failed"] == sum(c["severity"] == "warn" and c["passed"] is False for c in run)
    assert report["summary"]["errors_failed"] == sum(c["severity"] == "error" and c["passed"] is False for c in run)
    # A warning is measured and reported without blocking: the card missing days_past_due is served and counted.
    assert q(fresh_db, "SELECT failed FROM _dq_results WHERE run_id = ? AND check_name = 'rule:credit_fields_present'", [run_id]) == [(1,)]
    assert q(fresh_db, "SELECT count(*) FROM products WHERE product_id = 'PRD-FIX0007'") == [(1,)]
    record_property("evidence", f"{len(rows)} checks of the fixture's run: all {len(rows)} in _dq_results and in the JSON; summary counts recomputed")


def test_quality_the_committed_full_run_report_is_the_one_the_doc_quotes(record_property):
    report = json.loads(QUALITY_REPORT.read_text(encoding="utf-8"))
    s, checks = report["summary"], {(c["table"], c["check"]): c for c in report["checks"]}
    rows = sum(t["rows_staged"] for t in report["tables"].values())
    assert report["run_id"].split("-")[0] in DATA_QUALITY_DOC
    for claim in (f"{len(report['tables'])} tables, {rows / 1e6:.2f}M rows", f"{s['checks_run']} checks",
                  f"**{s['errors_failed']} errors, {s['warnings_failed']} warnings**"):
        assert claim in DATA_QUALITY_DOC, f"the doc no longer matches the committed report: {claim}"
    findings = section(DATA_QUALITY_DOC, "## Findings on the supplied data", "The quality gate was exercised")
    counted = {  # doc row -> (table, check) whose failed count the row quotes
        "usd_amount_present": ("transactions", "rule:usd_amount_present"),
        "credit_fields_present": ("products", "rule:credit_fields_present"),
        "closed_has_zero_balance": ("products", "rule:closed_has_zero_balance"),
        "fk_registration_branch": ("customers", "cross:fk_registration_branch"),
        "tx_not_before_product_opening": ("transactions", "cross:tx_not_before_product_opening"),
        "tx_not_before_customer_registration": ("transactions", "cross:tx_not_before_customer_registration"),
        "contact_not_before_registration": ("call_center_interactions", "cross:contact_not_before_registration"),
        "products_not_updated_after_as_of": ("transactions", "cross:products_not_updated_after_as_of"),
        "customers_not_updated_after_as_of": ("transactions", "cross:customers_not_updated_after_as_of"),
        "dictionary_not_null:duration_seconds": ("call_transcripts", "rule:dictionary_not_null:duration_seconds"),
    }
    for name, key in counted.items():
        row = next(line for line in findings.splitlines() if f"`{name}`" in line or f"`cross:{name}`" in line)
        check = checks[key]
        assert thousands(check["failed"]) in row or f"{100 * check['rate']:.1f}%" in row, f"{name}: {row[:120]} vs {check['failed']}"
    # Every warning the report lists as failed has a row in the doc (nothing that failed goes unexplained).
    failed = {c["check"].removeprefix("rule:").removeprefix("cross:") for c in report["checks"]
              if c["passed"] is False and c["failed"] and c["check"] != "pydantic_row_contract_sample"}
    unexplained = sorted(n for n in failed if f"`{n}`" not in findings and f"`cross:{n}`" not in findings)
    assert not unexplained, f"the report has failed checks the doc's findings do not mention: {unexplained}"
    record_property("evidence", f"quality_report.json ({report['run_id']}): {s['checks_run']} checks, {s['errors_failed']} errors, "
                                f"{s['warnings_failed']} warnings, {rows:,} rows; {len(counted)} counts in the doc == the report's")


# ---------------------------------------------------------------- 3. Linaje


def test_lineage_every_served_row_traces_to_a_run_a_file_and_its_hash(fresh_db, own_raw, record_property):
    build_fixture_warehouse(raw_dir=own_raw)
    con = duckdb.connect(str(fresh_db), read_only=True)
    try:
        assert lineage.verify(con, own_raw) == []
        traced = lineage.trace(con)
        for table in SERVING:
            t = traced[table]
            assert t["last_load"]["contract_version"] == CONTRACT_VERSION and t["last_load"]["code_version"]
            assert t["files"] and all(f["sha256"] == file_sha256(own_raw / f["source_file"]) for f in t["files"])
            assert t["runs_in_rows"] == [t["last_load"]["run_id"]]
        row = lineage.trace_row(con, "transactions", "TXN-FIX0004")
        assert row["source_file"].endswith("transactions_20240115.csv") and row["source_sha256"] == file_sha256(
            own_raw / row["source_file"])
        assert lineage.trace_row(con, "products", "PRD-FIX0001")["load"]["run_id"] == traced["products"]["last_load"]["run_id"]
        assert lineage.trace_row(con, "transactions", "TXN-NOPE") is None
    finally:
        con.close()
    n_files = sum(len(traced[t]["files"]) for t in SERVING)
    record_property("evidence", f"{len(SERVING)} served tables: row -> run -> contract/code -> file -> SHA-256 (recomputed from disk, {n_files} files); "
                                "`python -m data.lineage --verify` with no problems")


def test_lineage_a_broken_chain_is_detected(fresh_db, own_raw, record_property):
    build_fixture_warehouse(raw_dir=own_raw)
    source = next((own_raw / "transactions").glob("year=2024/month=01/day=15/*.csv"))

    def problems(after=None):
        con = duckdb.connect(str(fresh_db))
        try:
            if after:
                con.execute(after)
            return lineage.verify(con, own_raw)
        finally:
            con.close()

    assert problems() == []
    cases = {
        "a row without its run": ("UPDATE transactions SET _run_id = NULL WHERE transaction_id = 'TXN-FIX0004'", "without _run_id"),
        "a run that never succeeded": ("UPDATE _ingestion_log SET status = 'failed' WHERE table_name = 'branches'", "not a successful load"),
        "a file whose hash was not recorded": ("DELETE FROM _source_files WHERE table_name = 'customers'", "no file with a hash"),
    }
    for label, (sql, expected) in cases.items():
        with pytest.MonkeyPatch.context():
            other = fresh_db.with_name(f"{label.replace(' ', '_')}.duckdb")
            shutil.copy(fresh_db, other)
            con = duckdb.connect(str(other))
            con.execute(sql)
            found = lineage.verify(con, own_raw)
            con.close()
        assert any(expected in p for p in found), f"{label}: {found}"
    # The source changes after the load: the recorded hash no longer matches the bytes.
    source.write_text(source.read_text(encoding="utf-8").replace("200000.00", "200001.00"), encoding="utf-8")
    assert any("other bytes" in p for p in problems())
    source.unlink()
    assert any("no longer under" in p for p in problems())
    record_property("evidence", "the chain is broken in 5 ways (a row with no run, a failed run, a file with no hash, changed bytes, a deleted file) and verify() says so; "
                                "without raw_dir it also requires a 64-character hex sha256, size, URI, contract and code versions, mode and times not empty (10 negative cases)")


@pytest.mark.parametrize("statement, expected", [
    ("UPDATE _source_files SET sha256 = NULL WHERE table_name = 'customers'", "malformed sha256"),
    ("UPDATE _source_files SET sha256 = 'abc123' WHERE table_name = 'customers'", "malformed sha256"),
    ("UPDATE _source_files SET sha256 = upper(sha256) WHERE table_name = 'customers'", "malformed sha256"),
    ("UPDATE _source_files SET n_bytes = NULL WHERE table_name = 'customers'", "n_bytes"),
    ("UPDATE _source_files SET source_uri = '' WHERE table_name = 'customers'", "source_uri"),
    ("UPDATE _ingestion_log SET contract_version = NULL WHERE table_name = 'customers'", "contract_version"),
    ("UPDATE _ingestion_log SET contract_version = '  ' WHERE table_name = 'customers'", "contract_version"),
    ("UPDATE _ingestion_log SET code_version = NULL WHERE table_name = 'customers'", "code_version"),
    ("UPDATE _ingestion_log SET finished_at = NULL WHERE table_name = 'customers'", "finished_at"),
    ("UPDATE _ingestion_log SET mode = NULL WHERE table_name = 'customers'", "mode"),
])
def test_lineage_an_incomplete_record_fails_verification_even_without_the_raw_files(fresh_db, statement, expected, record_property):
    build_fixture_warehouse()
    con = duckdb.connect(str(fresh_db))
    try:
        assert lineage.verify(con) == []  # no raw_dir: presence and format only
        con.execute(statement)
        found = lineage.verify(con)
    finally:
        con.close()
    assert found and all(p.startswith("customers:") for p in found) and any(expected in p for p in found), found
    record_property("evidence", f"{statement.split(' SET ')[1].split(' WHERE')[0]} -> verify() without raw_dir: {found[0]}")


def test_lineage_a_corrected_partition_shows_which_file_and_hash_each_row_came_from(fresh_db, own_raw, record_property):
    first_run, _ = build_fixture_warehouse(raw_dir=own_raw)
    late_dir = own_raw.parent / "late"
    shutil.copytree(FIXTURES / "raw_late", late_dir)
    late_run, _ = run_pipeline(["transactions"], RunConfig(source="local", raw_dir=late_dir, only_date=datetime(2024, 1, 16).date()))
    con = duckdb.connect(str(fresh_db), read_only=True)
    try:
        corrected, untouched = (lineage.trace_row(con, "transactions", k) for k in ("TXN-FIX0009", "TXN-FIX0004"))
        assert corrected["run_id"] == late_run and corrected["source_sha256"] == file_sha256(next(late_dir.rglob("*.csv")))
        assert untouched["run_id"] == first_run and untouched["source_sha256"] != corrected["source_sha256"]
        assert corrected["load"]["params"]["only_date"] == "2024-01-16"
        assert {r for r, in con.execute("SELECT DISTINCT _run_id FROM transactions").fetchall()} == {first_run, late_run}
        assert lineage.verify(con) == []  # each row's run still has its file, though two runs read a file of the same name
    finally:
        con.close()
    record_property("evidence", "after a corrected partition, the corrected row points to the run and hash of raw_late and the others to those of the first run")


# ---------------------------------------------------------------- 4. Frescura


def _fixed_today(monkeypatch, day: str):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)

    monkeypatch.setattr(tools, "datetime", Clock)


def test_freshness_the_documented_defaults_and_the_as_of_date(monkeypatch, record_property):
    monkeypatch.delenv("FRESHNESS_ENFORCE", raising=False)
    assert tools.freshness_enforced() is True and tools.freshness_slo_hours() == 36.0
    assert "`FRESHNESS_SLO_HOURS` (default 36)" in DATA_QUALITY_DOC and "By default" in DATA_QUALITY_DOC
    with pytest.raises(DataUnavailable) as exc:
        tools.get_account_summary("CLI-FIX0004")
    assert exc.value.field == "as_of" and str(tools.data_as_of()) == "2024-01-16"
    assert RunConfig().lookback_days == 3 and "default 3" in DATA_QUALITY_DOC
    assert hasattr(tools._as_of_for, "cache_clear") and "read once per process" in DATA_QUALITY_DOC
    record_property("evidence", "without FRESHNESS_ENFORCE the 2024 fixture data is rejected by default; SLO 36 h; lookback 3 days")


def test_freshness_stale_data_is_unavailable_on_the_gated_tools_and_only_on_them(monkeypatch, record_property):
    monkeypatch.setenv("FRESHNESS_ENFORCE", "1")
    gated = [lambda: tools.get_account_summary("CLI-FIX0001"), lambda: tools.list_transactions("CLI-FIX0001"),
             lambda: tools.get_payment_status("CLI-FIX0001", "PRD-FIX0005")]
    for call in gated:
        with pytest.raises(DataUnavailable) as exc:
            call()
        assert exc.value.field == "as_of" and "2024-01-16" in str(exc.value) and "36h" in str(exc.value)
    # Not gated, as the doc says: the customer's own profile and the exchange rate (which states the date it used).
    assert tools.get_customer_profile("CLI-FIX0001")["as_of"].isoformat() == "2024-01-16"
    assert tools.get_exchange_rate("CLI-FIX0001", "MXN", "USD", on_date="2024-01-15")["used_date"]
    for name in ("balance", "transaction", "payment"):
        assert name in section(DATA_QUALITY_DOC, "- **Freshness SLO.**", "## Findings")
    record_property("evidence", "FRESHNESS_ENFORCE=1: balance, movements and payment status -> DataUnavailable(as_of); profile and exchange rate keep working")


def test_freshness_the_limit_is_the_slo_in_hours_measured_from_the_data_date(monkeypatch, record_property):
    monkeypatch.setenv("FRESHNESS_ENFORCE", "1")
    _fixed_today(monkeypatch, "2024-01-17")  # 24 h after the as-of date
    assert tools.get_account_summary("CLI-FIX0004")["items"]
    _fixed_today(monkeypatch, "2024-01-18")  # 48 h
    with pytest.raises(DataUnavailable):
        tools.get_account_summary("CLI-FIX0004")
    monkeypatch.setenv("FRESHNESS_SLO_HOURS", "48")  # exactly at the limit is fresh, as `>` says
    assert tools.get_account_summary("CLI-FIX0004")["items"]
    monkeypatch.setattr(tools, "data_as_of", lambda: None)  # a warehouse with no data has no date: never fresh
    with pytest.raises(DataUnavailable):
        tools.get_account_summary("CLI-FIX0004")
    record_property("evidence", "as_of 2024-01-16: today+1 day (24 h) serves; today+2 (48 h) blocks with SLO 36; with SLO 48 it serves; with no date it blocks")


def test_freshness_a_stale_warehouse_ends_in_an_escalation_not_an_answer(monkeypatch, record_property):
    ask = "¿Cuál es el saldo de mi cuenta de ahorros terminada en 0001?"
    orch, token, _ = make([tool_call_response("get_account_summary", {"product_id": "PRD-FIX0001"})])
    fresh = orch.handle_message(token, ask)
    assert fresh.disposition == "AUTO_RESOLVE" and "16/01/2024" in fresh.response_text  # answers state the as-of date

    monkeypatch.setenv("FRESHNESS_ENFORCE", "1")
    orch, token, _ = make([tool_call_response("get_account_summary", {"product_id": "PRD-FIX0001"})])
    stale = orch.handle_message(token, ask)
    assert stale.disposition == "ESCALATE" and stale.category == "data_unavailable" and stale.ticket_id
    assert "2,455.81" not in stale.response_text  # the stale figure is not shown
    record_property("evidence", "the same question: without the policy, AUTO_RESOLVE with 'al 16/01/2024'; with stale data, ESCALATE/data_unavailable with a ticket and without the figure")


def test_stale_warehouse_is_handed_off_by_default(monkeypatch):
    monkeypatch.delenv("FRESHNESS_ENFORCE", raising=False)
    orch, token, _ = make([tool_call_response("get_account_summary", {"product_id": "PRD-FIX0001"})])
    stale = orch.handle_message(token, "balance de mi cuenta terminada en 0001")
    assert stale.disposition == "ESCALATE" and stale.category == "data_unavailable" and stale.ticket_id
    assert "2,455.81" not in stale.response_text


# ---------------------------------------------------------------- 5. Componente aprendido contra una línea base


@pytest.fixture(scope="module")
def committed() -> dict:
    return json.loads(CLASSIFIER_REPORT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rebuilt() -> tuple[dict, object]:
    return evaluation.build_report(load_rows(evaluation.TRAIN), load_rows(evaluation.HELDOUT))


def test_learned_beats_the_keyword_baseline_on_the_same_test_split_with_intervals(committed, record_property):
    t = committed["test"]
    learned, base, paired = t["learned"]["accuracy"], t["baseline_keywords"]["accuracy"], t["paired_vs_keywords"]
    assert learned["n"] == base["n"] == paired["n"] == t["n"] == committed["test_n"]  # one held-out, both systems
    assert learned["ci95"][0] > base["ci95"][1], "the two Wilson intervals overlap"
    assert paired["diff_ci95"][0] > 0 and paired["mcnemar_p"] < 0.01
    assert t["learned"]["macro_f1"] > t["baseline_keywords"]["macro_f1"]
    assert learned["rate"] > t["baseline_majority"]["accuracy"]["rate"]
    record_property("evidence", f"test n={t['n']}: learned {fmt(learned).split(' (')[0]} vs keywords {fmt(base).split(' (')[0]}; "
                                f"paired difference {100 * paired['diff']:+.1f} pts [{100 * paired['diff_ci95'][0]:+.1f}, {100 * paired['diff_ci95'][1]:+.1f}], "
                                f"McNemar p={paired['mcnemar_p']}; majority floor {fmt(t['baseline_majority']['accuracy']).split(' (')[0]}")


VOLATILE = {"generated_at", "versions"}  # when it ran and with which library; the data hashes are checked against the files below
MD_TIMESTAMP = re.compile(r"^Generated by `python -m eval.evaluate_intent_classifier` at \S+\.$", re.M)


def as_published(report: dict) -> dict:
    """The report as it is written to eval/reports/intent_classifier.json (numpy scalars and all)."""
    return json.loads(json.dumps(report, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def differences(a, b, path: str = "") -> list[str]:
    """Every place two published reports differ, at any depth; only the top-level VOLATILE keys are left out."""
    if isinstance(a, dict) and isinstance(b, dict):
        keys = (set(a) | set(b)) - (VOLATILE if not path else set())
        return [d for k in sorted(keys) for d in (differences(a[k], b[k], f"{path}/{k}") if k in a and k in b else [f"{path}/{k}"])]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}[len {len(a)} vs {len(b)}]"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}[{i}]")]
    same = math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12) if isinstance(a, float) and isinstance(b, float) else a == b and type(a) is type(b)
    return [] if same else [path]


def numeric_leaves(node, path: str = "") -> list[tuple[str, list]]:
    """(path, keys) of every number in a report, except under the volatile keys."""
    if isinstance(node, dict):
        return [x for k, v in node.items() if path or k not in VOLATILE for x in numeric_leaves(v, f"{path}/{k}")]
    if isinstance(node, list):
        return [x for i, v in enumerate(node) for x in numeric_leaves(v, f"{path}[{i}]")]
    return [(path, [])] if isinstance(node, (int, float)) and not isinstance(node, bool) else []


def altered(report: dict, path: str) -> dict:
    """A copy of the report with the number at `path` replaced by 0 (by 1 when it already is 0)."""
    copy = json.loads(json.dumps(report))
    node = copy
    steps = re.findall(r"/([^/\[]+)|\[(\d+)\]", path)
    for key, index in steps[:-1]:
        node = node[int(index)] if index else node[key]
    key, index = steps[-1]
    slot = int(index) if index else key
    node[slot] = 1 if node[slot] == 0 else 0
    return copy


def test_learned_the_committed_report_is_what_the_code_and_data_produce(committed, rebuilt, record_property):
    report = as_published(rebuilt[0])
    assert differences(report, committed) == [], "eval/reports/intent_classifier.json is not what `make train-eval` gives"
    # Also every number the Markdown report prints: it is written from the same dict.
    rendered = evaluation.to_markdown({**rebuilt[0], "generated_at": committed["generated_at"]})
    written = (ROOT / "eval" / "reports" / "intent_classifier.md").read_text(encoding="utf-8")
    assert MD_TIMESTAMP.sub("", rendered) == MD_TIMESTAMP.sub("", written), "intent_classifier.md is not what `make train-eval` writes"
    versions = committed["versions"]
    assert versions["train_sha256"] == hashlib.sha256(Path(evaluation.TRAIN).read_bytes()).hexdigest()
    assert versions["heldout_sha256"] == hashlib.sha256(Path(evaluation.HELDOUT).read_bytes()).hexdigest()
    leaves = numeric_leaves(committed)
    record_property("evidence", f"build_report() over the repository's CSVs reproduces the {len(leaves)} figures of the versioned JSON report and the full text of the "
                                "Markdown (only the generation time and the sklearn version are excluded); data hashes == the files'")


def test_learned_altering_any_published_metric_makes_the_comparison_fail(committed, rebuilt, record_property):
    report = as_published(rebuilt[0])
    leaves = [path for path, _ in numeric_leaves(committed)]
    assert len(leaves) > 500
    missed = [path for path in leaves if differences(report, altered(committed, path)) != [path]]
    assert not missed, f"a change to these numbers goes unnoticed: {missed[:5]}"
    named = ("/test/learned/macro_f1", "/test/learned/by_language/pt/rate", "/test_without_templated_phrases/learned_accuracy/rate")
    assert all(n in leaves for n in named)
    # And the Markdown: a figure changed there is a different text.
    written = (ROOT / "eval" / "reports" / "intent_classifier.md").read_text(encoding="utf-8")
    assert MD_TIMESTAMP.sub("", written) != MD_TIMESTAMP.sub("", written.replace(f"| {committed['test']['learned']['macro_f1']} |", "| 0 |", 1))
    record_property("evidence", f"each of the report's {len(leaves)} figures (learned macro-F1, PT accuracy and accuracy without template phrases included), "
                                "altered one at a time, makes the comparison fail at exactly that path")


def test_learned_the_deployed_model_is_the_one_that_was_selected_and_reported(committed, rebuilt, record_property):
    _, fresh = rebuilt
    deployed = joblib.load(ROOT / "eval" / "models" / "intent_clf.joblib")
    meta = json.loads((ROOT / "eval" / "models" / "intent_clf_meta.json").read_text(encoding="utf-8"))
    texts = [r["utterance"] for r in load_rows(evaluation.HELDOUT)] + [r["utterance"] for r in load_rows(evaluation.TRAIN)]
    assert list(deployed.classes_) == list(fresh.classes_)
    assert np.allclose(deployed.predict_proba(texts), fresh.predict_proba(texts), atol=1e-9)
    assert meta["variant"] == committed["chosen_variant"] and meta["escalation_threshold"] == committed["escalation_threshold"]
    assert meta["train_sha256"] == committed["versions"]["train_sha256"]
    record_property("evidence", f"eval/models/intent_clf.joblib gives the same probabilities as the retrained model ({len(texts)} phrases, tol 1e-9); "
                                f"meta: {meta['variant']}, τ={meta['escalation_threshold']}, same training hash")


def test_learned_the_paired_statistics_agree_with_a_hand_worked_case(record_property):
    y = ["a"] * 10
    worse = ["b"] * 4 + ["a"] * 6          # 6/10 right
    better = ["a"] * 9 + ["b"]             # 9/10 right; right on 4 the other misses, wrong on 1 that it gets
    out = paired_accuracy(y, worse, better, resamples=2000, seed=1)
    assert (out["only_b_right"], out["only_a_right"], out["diff"]) == (4, 1, 0.3)
    assert out["mcnemar_p"] == pytest.approx(2 * (1 + 5) / 32)  # exact: 5 discordant pairs, 1 against
    assert out["diff_ci95"][0] <= out["diff"] <= out["diff_ci95"][1]
    assert paired_accuracy(y, worse, better, resamples=2000, seed=1) == out  # seeded, so the committed report can be checked
    assert paired_accuracy(y, better, better)["mcnemar_p"] == 1.0
    record_property("evidence", "paired difference and exact McNemar checked by hand on a 10-item case (4 for, 1 against, p = 12/32); the bootstrap is reproducible with a seed")


# ---------------------------------------------------------------- 6. Sin fuga


def _selection(report: dict) -> dict:
    return {k: report[k] for k in ("chosen_variant", "escalation_threshold", "model_selection_dev", "threshold_sweep_dev")}


def test_leakage_nothing_chosen_moves_when_the_test_split_changes(rebuilt, monkeypatch, record_property):
    original, _ = rebuilt
    real_split = evaluation.dev_test_split

    def split_with(perturb_dev=False, perturb_test=False):
        def split(rows):
            dev, test = real_split(rows)
            rotate = lambda part: [dict(r, intent=i) for r, i in zip(part, [p["intent"] for p in part][7:] + [p["intent"] for p in part][:7])]  # noqa: E731
            return (rotate(dev) if perturb_dev else dev), (rotate(test) if perturb_test else test)
        return split

    with monkeypatch.context() as m:
        m.setattr(evaluation, "dev_test_split", split_with(perturb_test=True))
        changed_test, _ = evaluation.build_report(load_rows(evaluation.TRAIN), load_rows(evaluation.HELDOUT))
    assert _selection(changed_test) == _selection(original)  # variant, τ, dev scores and the whole sweep
    assert changed_test["test"]["learned"]["accuracy"] != original["test"]["learned"]["accuracy"]  # the change did reach the test scoring
    # Positive control: the same change on dev does move the selection, so the check above could have failed.
    with monkeypatch.context() as m:
        m.setattr(evaluation, "dev_test_split", split_with(perturb_dev=True))
        changed_dev, _ = evaluation.build_report(load_rows(evaluation.TRAIN), load_rows(evaluation.HELDOUT))
    assert _selection(changed_dev) != _selection(original)
    record_property("evidence", f"with the test labels rotated: variant ({original['chosen_variant']}), τ ({original['escalation_threshold']}), "
                                "dev F1 and sweep identical, and the test accuracy changes; rotating dev does change the selection (positive control)")


def test_leakage_near_duplicates_between_train_dev_and_test(committed, record_property):
    train = [r["utterance"] for r in load_rows(evaluation.TRAIN)]
    held = load_rows(evaluation.HELDOUT)
    dropped = leakage.excluded_utterances(committed["leakage"])
    dev, test = evaluation.dev_test_split(held)
    dev, test = ([r["utterance"] for r in part if r["utterance"] not in dropped] for part in (dev, test))
    assert (len(dev), len(test)) == (committed["dev_n"], committed["test_n"])
    worst = {}
    for name, part, reference in (("dev↔train", dev, train), ("test↔train", test, train), ("test↔dev", test, dev)):
        worst[name] = round(max(s for s, _ in leakage.nearest(reference, part)), 3)
        assert worst[name] < leakage.EXCLUDE_AT, f"{name}: a near-duplicate is being scored"
    assert committed["leakage_dev_vs_test"]["excluded"] == []
    normalized = lambda texts: {leakage.normalize(t) for t in texts}  # noqa: E731
    assert not normalized(train) & (normalized(dev) | normalized(test))
    record_property("evidence", f"maximum character-trigram similarity (excludes ≥ {leakage.EXCLUDE_AT}): {worst}; "
                                f"phrases excluded from the score: {len(dropped)} of {committed['heldout_n']}")


def test_leakage_the_check_catches_a_copy_of_a_training_phrase_and_keeps_it_out_of_the_scores(committed, record_property):
    train, held = load_rows(evaluation.TRAIN), load_rows(evaluation.HELDOUT)
    copy = "  " + train[10]["utterance"].upper().rstrip("?.") + " ¡!"  # same words, other case, punctuation and spaces
    report, _ = evaluation.build_report(train, held + [{**held[0], "utterance": copy, "source": "injected"}])
    assert copy in leakage.excluded_utterances(report["leakage"])
    assert report["dev_n"] + report["test_n"] == len(held) + 1 - len(report["leakage"]["excluded"])
    record_property("evidence", "a copy of a training phrase (other capitalization, punctuation and spaces) is detected and does not enter the score")


def test_leakage_the_only_input_of_the_learned_component_is_the_customers_words(record_property):
    assert list(inspect.signature(intent_guard.read).parameters) == ["text"]
    train_src = ast.parse(inspect.getsource(intent_classifier.train))
    keys = {n.slice.value for n in ast.walk(train_src) if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)}
    assert keys == {"utterance", "intent"}, f"train() reads other columns: {keys}"
    rows = load_rows(evaluation.TRAIN)
    clean = intent_classifier.train([{"utterance": r["utterance"], "intent": r["intent"]} for r in rows], "char+word")
    noisy = intent_classifier.train([{**r, "language": "x", "template_id": r["intent"]} for r in rows], "char+word")
    probe = [r["utterance"] for r in load_rows(evaluation.HELDOUT)]
    assert np.array_equal(clean.predict_proba(probe), noisy.predict_proba(probe))
    for module in (intent_classifier, intent_guard):
        imported = {a.name for n in ast.walk(ast.parse(inspect.getsource(module))) if isinstance(n, (ast.Import, ast.ImportFrom))
                    for a in n.names} | {n.module for n in ast.walk(ast.parse(inspect.getsource(module))) if isinstance(n, ast.ImportFrom)}
        assert not {i for i in imported if i and (i.split(".")[0] in ("duckdb", "data") or i.startswith("agent.tools"))}, module.__name__
    record_property("evidence", "features = the customer's text: train() reads only `utterance` and `intent`; retraining with junk columns gives the same "
                                "probabilities; neither the classifier nor the guard imports duckdb, tools or the warehouse (no information from after the outcome)")


def test_leakage_the_two_datasets_are_the_ones_frozen_before_measuring_and_the_workloads_do_not_share_cases(committed, record_property):
    meta = json.loads((ROOT / "eval" / "models" / "intent_clf_meta.json").read_text(encoding="utf-8"))
    assert meta["train_sha256"] == committed["versions"]["train_sha256"] == hashlib.sha256(Path(evaluation.TRAIN).read_bytes()).hexdigest()
    assert {r["source"] for r in load_rows(evaluation.HELDOUT)} <= {"team_heldout", "dataset_transcript"}
    cases = {s: [json.loads(line) for line in open(ROOT / "eval" / "workload" / f"cases_{s}.jsonl", encoding="utf-8")] for s in ("dev", "test")}
    keys = {s: {(c["template"], c["customer_id"]) for c in cs} for s, cs in cases.items()}
    assert not keys["dev"] & keys["test"] and not {c["case_id"] for c in cases["dev"]} & {c["case_id"] for c in cases["test"]}
    train = [r["utterance"] for r in load_rows(evaluation.TRAIN)]
    worst = {s: round(leakage.report(train, sorted({t for c in cs for t in c["turns"]}))["max"], 3) for s, cs in cases.items()}
    assert all(w < leakage.EXCLUDE_AT for w in worst.values()), worst
    record_property("evidence", f"training and held-out hashes == those of the report and of the deployed model; dev/test workloads share no (template, customer) "
                                f"pair; maximum similarity of the workload's turns to the training set: {worst}")


def test_leakage_the_workload_generator_rejects_a_training_phrase_with_other_punctuation(record_property):
    from types import SimpleNamespace

    from eval import workload

    train = load_rows(evaluation.TRAIN)[3]["utterance"]
    disguised = train.upper().rstrip("?.") + " !"
    assert disguised.strip().lower() != train.strip().lower()  # what the generator used to compare
    assert workload.leakage_check([SimpleNamespace(turns=[disguised, "algo que no se parece a nada del entrenamiento"])]) == [disguised]
    assert workload.leakage_check([SimpleNamespace(turns=[])]) == []
    record_property("evidence", "the workload generator rejects a turn that is a training phrase with other capitalization or punctuation "
                                "(before, it only compared strip().lower())")


def test_leakage_the_test_misses_were_reported_not_tuned_away(committed, record_property):
    misses = committed["test"]["guard_misses"]
    assert misses, "no recorded miss: either the guard is perfect on test (say so in the docs) or it was tuned on it"
    tau = committed["escalation_threshold"]
    probs = intent_guard.read
    for utterance in misses:
        assert not contains_escalation_signal(utterance), f"{utterance!r} is now in the lexicon: it was added after seeing test"
        assert probs(utterance).p_escalation < tau
        assert utterance in EVALUATION_DOC and utterance.split()[0] in LIMITATIONS_DOC
    record_property("evidence", f"{len(misses)} missed escalation(s) in test, {misses}: still outside the lexicon and under τ={tau}; declared in EVALUATION.md and LIMITATIONS.md")


def test_leakage_evaluation_doc_section_2_quotes_the_committed_report(committed, record_property):
    text = " ".join(section(EVALUATION_DOC, "## 2. Learned component: intent classifier", "## 3. System evaluation").split())
    t, short = committed["test"], lambda r: fmt(r).split(" (n=")[0]  # noqa: E731
    lang = t["learned"]["by_language"]["pt"], t["baseline_keywords"]["by_language"]["pt"]
    guard = t["escalation_guard"]
    expected = [f"{committed['train_n']} team-authored", f"{committed['heldout_n']} utterances",
                f"**dev** ({committed['dev_n']})", f"**test** ({committed['test_n']})", f"τ = {committed['escalation_threshold']}",
                short(t["baseline_keywords"]["accuracy"]), f"**{short(t['learned']['accuracy'])}**",
                f"{t['baseline_keywords']['macro_f1']:.2f}", f"**{t['learned']['macro_f1']:.2f}**",
                f"{100 * lang[1]['rate']:.1f}%", f"{100 * lang[0]['rate']:.1f}%",
                f"{100 * guard['lexicon_only']['recall']['rate']:.1f}%", f"{100 * guard['classifier_only']['recall']['rate']:.1f}%",
                f"**{100 * guard['lexicon_or_classifier (runtime)']['recall']['rate']:.1f}%**"]
    expected += [f"{v['dev_macro_f1']:.2f}" for v in committed["model_selection_dev"].values()]
    pr, without = t["paired_vs_keywords"], committed["test_without_templated_phrases"]
    expected += [f"**{100 * pr['diff']:+.1f} points**", f"[{100 * pr['diff_ci95'][0]:+.1f}, {100 * pr['diff_ci95'][1]:+.1f}]",
                 f"on {pr['only_b_right']} utterances and the reverse on {pr['only_a_right']}", f"p = {pr['mcnemar_p']:.4f}",
                 short(t["baseline_majority"]["accuracy"]), f"{without['n']} of {t['n']} left",
                 f"learned {100 * without['learned_accuracy']['rate']:.1f}%, keywords {100 * without['baseline_accuracy']['rate']:.1f}%",
                 f"highest similarity of {committed['leakage_dev_vs_test']['max']:.2f}", f"({len(committed['leakage']['excluded'])} of {committed['heldout_n']}"]
    missing = [e for e in expected if e not in text]
    assert not missing, f"EVALUATION.md §2 does not match eval/reports/intent_classifier.json: {missing}"
    # The same headline in the other documents that repeat it.
    learned, base = t["learned"]["accuracy"]["rate"], t["baseline_keywords"]["accuracy"]["rate"]
    assert f"**{100 * learned:.1f}% vs {100 * base:.1f}%**" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{100 * learned:.1f}% vs {100 * base:.1f}% for keywords" in (ROOT / "docs" / "slides_outline.md").read_text(encoding="utf-8")
    assert f"{committed['test_n']} utterances in the classifier test split" in LIMITATIONS_DOC
    record_property("evidence", f"{len(expected)} figures in EVALUATION.md §2 == eval/reports/intent_classifier.json; the headline matches in README, slides_outline and LIMITATIONS")
