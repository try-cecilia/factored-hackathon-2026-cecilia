"""The data engineering entry page: the layers with their row counts, one row traced end to end, run ids and hashes, and
the quality checks of the last full load.

    python -m eval.data_page        # writes docs/DATA.md

The prose is ours; every figure is read from a committed artifact, so a number on the page cannot drift from its source:
data/reports/quality_report.json (the last full load), docs/evidence/lake_manifest.json (the Parquet export of the full
warehouse), docs/evidence/baseline_metrics.json (the as-of date), docs/evidence/data_ml_validation.json, render.yaml (the
demo's sample) and the code itself (contracts, the quarantine threshold, the gold marts, which modules read which table).
The traced row comes from the hand-made fixture: the real pipeline loads tests/fixtures/raw into a throwaway warehouse,
builds gold on it and follows one transaction, so it needs no S3 and no full warehouse.
tests/test_data_page.py holds the committed page to a fresh render.
"""
from __future__ import annotations

import csv
import json
import os
import re
import tempfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("data/reports/quality_report.json")
MANIFEST = Path("docs/evidence/lake_manifest.json")
BASELINE = Path("docs/evidence/baseline_metrics.json")
VALIDATION = Path("docs/evidence/data_ml_validation.json")
RENDER = Path("render.yaml")
OUT = Path("docs/DATA.md")
FIXTURE = Path("tests/fixtures/raw")
EXAMPLE_TABLE, EXAMPLE_KEY = "transactions", "TXN-FIX0002"

# What each check category means; the categories are the ones data/quality.py assigns.
CATEGORIES = {
    "schema": "Columns against the contract: a missing required column fails the load; missing optional or new columns warn",
    "type": "Every value casts to the dictionary's type without loss (recorded only when a value fails)",
    "not_null": "Columns the dictionary declares NOT NULL",
    "uniqueness": "Primary-key duplicates in the batch, before dedup",
    "domain": "Enums, ranges and business rules per table",
    "contract_sample": "An independent pydantic model of the row, on a sample of up to 1,000 rows",
    "cross_table": "Foreign keys, ownership, dates against the parent rows, unique keys besides the primary key",
    "dependency": "A cross-table check whose parent table is not loaded: recorded as not run, never as passed",
    "gate": "The table's quarantine rate against the rollback threshold",
    "profile": "Null rate of every nullable column (a measurement, no pass or fail)",
}
# Where a table is read, by layer of the code: what the agent answers from, what the demo and API show, what the analysis reads.
READERS = (("agent", "agent"), ("api", "API and demo"), ("analysis", "analysis"))


def _read(path: Path) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def n(x: int) -> str:
    return f"{x:,}"


def readers(names: list[str]) -> dict[str, list[str]]:
    """Per table, the modules under agent/, api/ and analysis/ that query it (`FROM`/`JOIN`, or the mart's name as a literal)."""
    sources = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
               for folder, _ in READERS for p in sorted((ROOT / folder).rglob("*.py"))}
    out = {}
    for name in names:
        pattern = re.compile(rf"""(?:FROM|JOIN)\s+{name}\b|["']{name}["']""" if name.startswith("gold_") else rf"(?:FROM|JOIN)\s+{name}\b")
        out[name] = [path for path, text in sources.items() if pattern.search(text)]
    return out


def demo_sample() -> str:
    """The deployed demo's ingest arguments, as render.yaml sets them."""
    text = (ROOT / RENDER).read_text(encoding="utf-8")
    m = re.search(r"key: INGEST_ARGS\s*\n\s*value: (.+)", text)
    if not m:
        raise ValueError("render.yaml no longer sets INGEST_ARGS")
    return m.group(1).strip()


@contextmanager
def _env(**values: str):
    before = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in before.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def collect_example(workdir: Path) -> dict:
    """Load the fixture with the real pipeline into `workdir`, build gold, and follow one row. Only what does not change
    between runs is kept: the run id, the load times, the code version and the machine are left out."""
    from data.contracts import CONTRACT_VERSION, DOMAIN_RULES, NOT_NULL_COLUMNS
    from data.gold import MARTS, build
    from data.lineage import trace_row
    from data.pipeline import TABLES, RunConfig, run_pipeline

    db = workdir / "fixture.duckdb"
    serving = [t.name for t in TABLES if t.profile == "serving"]
    with _env(DUCKDB_PATH=str(db)):
        run_pipeline(serving, RunConfig(source="local", raw_dir=ROOT / FIXTURE))
    con = duckdb.connect(str(db))
    try:
        con.execute("SET TimeZone = 'UTC'")
        build(con)
        traced = trace_row(con, EXAMPLE_TABLE, EXAMPLE_KEY)
        cur = con.execute(f"SELECT * FROM {EXAMPLE_TABLE} WHERE transaction_id = ?", [EXAMPLE_KEY])
        row = dict(zip([d[0] for d in cur.description], cur.fetchone()))
        rules = []
        for col in NOT_NULL_COLUMNS[EXAMPLE_TABLE]:
            rules.append(("not_null", col, "error", row[col] is not None))
        for name, pred, sev in DOMAIN_RULES[EXAMPLE_TABLE]:
            ok = con.execute(f"SELECT coalesce(({pred}), false) FROM {EXAMPLE_TABLE} WHERE transaction_id = ?", [EXAMPLE_KEY]).fetchone()[0]
            rules.append(("domain", name, sev, bool(ok)))
        batch = con.execute("SELECT check_name, failed, total FROM _dq_results WHERE run_id = ? AND table_name = ? AND category = 'cross_table' "
                            "ORDER BY check_name", [traced["run_id"], EXAMPLE_TABLE]).fetchall()
        quarantined = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE '_quarantine_%'").fetchall()]
        size = con.execute("SELECT n_bytes FROM _source_files WHERE run_id = ? AND table_name = ? AND source_file = ?",
                           [traced["run_id"], EXAMPLE_TABLE, traced["source_file"]]).fetchone()[0]
        mart = {m.name: m for m in MARTS}["gold_daily_activity"]
        grain = {"activity_date": row["transaction_date"].date(), **{c: row[c] for c in mart.grain[1:]}}
        daily = con.execute("SELECT n_transactions, n_customers, total_abs_amount FROM gold_daily_activity WHERE "
                            + " AND ".join(f"{c} = ?" for c in grain), list(grain.values())).fetchone()
        summary = con.execute("SELECT n_transactions, n_products FROM gold_customer_summary WHERE customer_id = ?", [row["customer_id"]]).fetchone()
        as_of = con.execute("SELECT max(process_date) FROM transactions").fetchone()[0]
    finally:
        con.close()
    source = ROOT / FIXTURE / traced["source_file"]
    lines = source.read_text(encoding="utf-8").splitlines()
    line_no = next(i for i, line in enumerate(lines, 1) if line.startswith(EXAMPLE_KEY + ","))
    return {
        "source_file": traced["source_file"], "sha256": traced["source_sha256"], "bytes": size,
        "header": lines[0], "line": lines[line_no - 1], "line_no": line_no,
        "load": {"mode": traced["load"]["mode"], "contract_version": traced["load"]["contract_version"]},
        "contract_version": CONTRACT_VERSION,
        "row": {c: str(row[c]) for c in ("transaction_id", "transaction_date", "customer_id", "product_id", "transaction_type",
                                          "amount", "currency", "transaction_status")},
        "rules": rules, "batch_cross_checks": batch, "quarantine_tables": quarantined,
        "gold_daily_activity": {"grain": {k: str(v) for k, v in grain.items()},
                                "n_transactions": daily[0], "n_customers": daily[1], "total_abs_amount": str(daily[2])},
        "gold_customer_summary": {"customer_id": row["customer_id"], "n_transactions": summary[0], "n_products": summary[1]},
        "as_of": str(as_of),
    }


def _flow(report: dict, manifest: dict, threshold: float, sample: str) -> list[str]:
    from data.gold import MARTS
    from data.pipeline import TABLES

    t = report["tables"]
    profile = {s.name: s.profile for s in TABLES}
    loaded = lambda name: t[name]["rows_new"] + t[name]["rows_updated"]  # noqa: E731
    lines = lambda names: "<br>".join(f"{name} {n(loaded(name))}" for name in names)  # noqa: E731
    serving = [name for name in t if profile[name] == "serving"]
    analysis = [name for name in t if profile[name] == "analysis"]
    gold = [f"{f['table']} {n(f['rows'])}" for f in manifest["files"] if f["layer"] == "gold"]
    gold = "<br>".join(gold + [m.name for m in MARTS if m.name not in {f["table"] for f in manifest["files"]}])
    staged = sum(v["rows_staged"] for v in t.values())
    quarantined = sum(v["rows_quarantined"] for v in t.values())
    parts = sum(v["partitions"] for v in t.values())
    return [
        "```mermaid",
        "flowchart LR",
        f'  B["<b>Bronze</b><br>organizer CSVs, S3 or local<br>never rewritten<br>{len(t)} tables<br>{n(parts)} daily partitions or flat files<br>SHA-256 of every file"]',
        '  B --> C["<b>Contracts</b><br>schema drift<br>TRY_CAST to the dictionary<br>NOT NULL, domain rules"]',
        f'  C -- "error-level rule broken" --> Q["<b>Quarantine</b><br>one _quarantine_ table per table<br>{n(quarantined)} of {n(staged)} rows<br>in the last full load"]',
        f'  Q -. "over {threshold:.0%} of a table" .-> RB["<b>Rollback</b><br>the warehouse keeps<br>its previous state"]',
        '  C -- "clean rows" --> D["dedup: latest record wins<br>upsert by primary key"]',
        f'  D --> SS["<b>Silver, serving</b><br>{lines(serving)}"]',
        f'  D --> SA["<b>Silver, analysis</b><br>{lines(analysis)}"]',
        "  SS --> X[\"cross-table checks<br>FKs, ownership, dates\"]",
        "  SA --> X",
        f'  SS --> G["<b>Gold</b><br>{gold}"]',
        "  SA --> G",
        '  SS ==> AG(["<b>Agent tools</b><br>read-only, silver"])',
        f'  SS ==> DM(["<b>Demo on Render</b><br>a sample of silver<br>{_sample_short(sample)}"])',
        '  G ==> AN(["<b>Baseline report</b><br>reads gold_contact_demand"])',
        '  SS --> PQ[("<b>Parquet copy</b><br>data/lake + manifest<br>rows and SHA-256 per file")]',
        "  G --> PQ",
        '  D -.-> LN[("<b>Lineage tables</b><br>_ingestion_log, _source_files<br>_partition_log, _dq_results<br>_gold_log")]',
        "  G -.-> LN",
        "```",
    ]


def _sample_short(sample: str) -> str:
    customers = re.search(r"--sample-customers (\d+)", sample)
    since = re.search(r"--since (\S+)", sample)
    if not (customers and since):
        raise ValueError(f"render.yaml's sample is no longer customers since a date: {sample}")
    return f"{n(int(customers.group(1)))} customers since {since.group(1)}"


def _layers(report: dict, manifest: dict, read_by: dict[str, list[str]]) -> list[str]:
    from data.pipeline import TABLES

    profile = {s.name: s.profile for s in TABLES}
    exported = {f["table"]: f["rows"] for f in manifest["files"]}

    def who(name: str) -> str:
        found = [f"[`{Path(p).name}`](../{p})" for p in read_by.get(name, [])]
        return ", ".join(found) or "none"

    L = ["| Layer | Table | Rows loaded in the last full load | Rows in the Parquet export | Quarantined | Read by |",
         "|---|---|---|---|---|---|"]
    for name, v in report["tables"].items():
        L.append(f"| Silver ({profile[name]}) | `{name}` | {n(v['rows_new'] + v['rows_updated'])} | "
                 f"{n(exported[name]) if name in exported else 'not in the export'} | {n(v['rows_quarantined'])} | {who(name)} |")
    for f in (f for f in manifest["files"] if f["layer"] == "gold"):
        L.append(f"| Gold | `{f['table']}` | built from silver | {n(f['rows'])} | rolls back instead | {who(f['table'])} |")
    from data.gold import MARTS

    for name in (m.name for m in MARTS if m.name not in exported):
        L.append(f"| Gold | `{name}` | built from silver | not in the export | rolls back instead | {who(name)} |")
    return L


def _example(ex: dict, read_by: dict[str, list[str]]) -> list[str]:
    header = next(csv.reader([ex["header"]]))
    values = next(csv.reader([ex["line"]]))
    errors = [r for r in ex["rules"] if r[2] == "error"]
    warns = [r for r in ex["rules"] if r[2] == "warn"]
    gd, gs = ex["gold_daily_activity"], ex["gold_customer_summary"]
    agent = [f"[`{Path(p).name}`](../{p})" for p in read_by[EXAMPLE_TABLE] if p.startswith("agent/")]
    if any(p.startswith("agent/") for name, paths in read_by.items() if name.startswith("gold_") for p in paths):
        raise ValueError("an agent module now reads a gold mart: the page says the agent reads silver only")
    shown = dict(zip(header, values))
    return [
        f"Transaction `{EXAMPLE_KEY}` of the hand-made fixture, loaded by the real pipeline. "
        "Anyone can rebuild it without S3 (commands below). On a full warehouse the same command traces any row; the copy "
        "the export below was written from was loaded before `_source_files` existed, so `make lineage` fails on it until it "
        "is loaded again, and the hashed example is the fixture's.", "",
        "**1. Bronze: the delivered bytes.** Line "
        f"{ex['line_no']} of [`{ex['source_file']}`](../{FIXTURE.as_posix()}/{ex['source_file']}), "
        f"{n(ex['bytes'])} bytes, SHA-256 `{ex['sha256']}`:", "",
        "```csv", ex["header"], ex["line"], "```", "",
        f"**2. Contracts it passed** (contract {ex['contract_version']}, [`data/contracts.py`](../data/contracts.py)). "
        f"Every value cast to its dictionary type. The row's own values against its table's rules:", "",
        "| Rule | Severity | This row |", "|---|---|---|",
        *(f"| NOT NULL on {len([r for r in errors if r[0] == 'not_null'])} columns "
          f"({', '.join(f'`{r[1]}`' for r in errors if r[0] == 'not_null')}) | error | "
          f"{'pass' if all(r[3] for r in errors if r[0] == 'not_null') else 'FAIL'} |",),
        *(f"| `{r[1]}` | {r[2]} | {'pass' if r[3] else 'fails (kept, counted)' if r[2] == 'warn' else 'FAIL'} |"
          for r in errors + warns if r[0] == "domain"), "",
        "An error-level failure would have sent the row to `_quarantine_transactions` with the rule's name. "
        f"This load quarantined nothing ({'no' if not ex['quarantine_tables'] else ', '.join(ex['quarantine_tables'])} quarantine table). "
        "Its batch-level cross-table checks: "
        + ", ".join(f"`{c}` {f}/{t} failed" for c, f, t in ex["batch_cross_checks"]) + ". "
        + _cross_note(ex), "",
        f"**3. Silver: the typed row and its lineage.** `transactions` row `{EXAMPLE_KEY}`: "
        + ", ".join(f"`{k}` = {v}" for k, v in ex["row"].items() if k != "transaction_id")
        + f". It carries `_source_file` = `{ex['source_file']}`, `_run_id` (the load's id) and `_ingested_at`. "
        f"The load's row in `_ingestion_log` records mode `{ex['load']['mode']}`, contract `{ex['load']['contract_version']}`, the code "
        "version, the parameters and the machine; `_source_files` records the file with the same SHA-256.", "",
        "**4. Gold: the marts it adds to.** In `gold_daily_activity`, the row for "
        + ", ".join(f"`{k}` = {v}" for k, v in gd["grain"].items())
        + f" counts {gd['n_transactions']} movement(s) of {gd['n_customers']} customer(s), {gd['total_abs_amount']} in absolute amount. "
        f"In `gold_customer_summary`, `{gs['customer_id']}` has {gs['n_transactions']} movements on {gs['n_products']} products.", "",
        f"**5. The agent.** {', '.join(agent)} reads `transactions` from silver, never gold: `list_transactions` returns this "
        f"movement to `{shown['customer_id']}` once the session is bound to that customer, with the warehouse's as-of date.", "",
    ]


def _cross_note(ex: dict) -> str:
    failing = [c for c, f, _ in ex["batch_cross_checks"] if f]
    if not failing:
        return "All of them pass."
    if all(c.endswith("_not_updated_after_as_of") for c in failing):
        return (f"The failing ones count dimension rows last updated after the fixture's as-of date ({ex['as_of']}); "
                "they are warnings and change nothing.")
    raise ValueError(f"the fixture's cross-table checks fail in a way this page does not explain: {failing}")


def _quality(report: dict, validation: dict) -> list[str]:
    checks = report["checks"]
    by = Counter()
    for c in checks:
        state = "not run" if c["category"] == "dependency" else "info" if c["passed"] is None else "pass" if c["passed"] else "fail"
        by[(c["category"], c["severity"], state)] += 1
    s = report["summary"]
    failed = [c for c in checks if c["passed"] is False]
    errors_failed = sum(1 for c in failed if c["severity"] == "error")
    if (len(checks) - s["checks_not_run"], s["checks_not_run"], errors_failed, len(failed) - errors_failed) != (
            s["checks_run"], sum(1 for c in checks if c["category"] == "dependency"), s["errors_failed"], s["warnings_failed"]):
        raise ValueError(f"{REPORT}: the checks do not add up to the report's summary {s}")
    L = ["| Category | What it checks | Severity | Checks | Passed | Failed | Not run |", "|---|---|---|---|---|---|---|"]
    keys = sorted({(c, sev) for c, sev, _ in by}, key=lambda k: (list(CATEGORIES).index(k[0]), k[1]))
    seen = set()
    for cat, sev in keys:
        what, _ = ("" if cat in seen else CATEGORIES[cat]), seen.add(cat)
        count = sum(v for (c, sv, _), v in by.items() if (c, sv) == (cat, sev))
        passed = by[(cat, sev, "pass")] if sev != "info" else "–"
        fail = by[(cat, sev, "fail")] if sev != "info" else "–"
        L.append(f"| `{cat}` | {what} | {sev} | {count} | {passed} | {fail} | {by[(cat, sev, 'not run')]} |")
    L.append(f"| **Total** | | | **{len(checks)}** | | **{len(failed)}** | **{s['checks_not_run']}** |")
    L += ["", f"Last full load `{report['run_id']}` ({report['generated_at'][:10]}, contract {report['contract_version']}, code "
          f"`{report['code_version']}`): **{s['checks_run']} checks run, {s['errors_failed']} errors failed, "
          f"{s['warnings_failed']} warnings failed, {s['checks_not_run']} not run**, status `{s['status']}`. "
          "No `type` check appears because one is recorded only when a value fails its cast. The failed warnings, "
          "each kept and counted rather than quarantined (what the system does about each one is in "
          "[data_quality.md](data_quality.md#findings-on-the-supplied-data)):", "",
          "| Table | Check | Failed | Of |", "|---|---|---|---|"]
    L += [f"| `{c['table']}` | `{c['check']}` | {n(c['failed'])} | {n(c['total'])} |" for c in failed]
    crit = validation["criteria"]
    L += ["", f"`make validate-data-ml` (part of `make gate` and CI) holds the claims about contracts, quality, lineage and "
          f"freshness, and the classifier's claims, to tests: the committed evidence ([data_ml_validation.md](evidence/data_ml_validation.md), "
          f"{validation['generated_at'][:10]}, code `{validation['code_version']}`) has "
          + ", ".join(f"{c['id']} {c['status']} ({len(c['tests'])} tests)" for c in crit) + "."]
    return L


def _hashes(report: dict, manifest: dict, as_of: str, ex: dict) -> list[str]:
    runs = sorted(set(manifest["silver_runs"].values()))
    gold_runs = sorted(set(manifest["gold_runs"].values()))
    total = sum(f["bytes"] for f in manifest["files"])
    L = [
        "Every pipeline invocation gets one run id, `YYYYMMDDTHHMMSSZ-` plus six hex characters (UTC start time and a random "
        f"suffix; the last full load is `{report['run_id']}`). It is written to every row it loads (`_run_id`), to "
        "`_ingestion_log`, `_source_files`, `_partition_log` and `_dq_results`, and to quarantined rows (`_quarantine_run`). "
        "A gold build has its own id in `_gold_log` and on every mart row (`_gold_run_id`).", "",
        f"**As-of.** The warehouse's as-of date is the last processed day of `transactions`: **{as_of}** for the organizer's "
        f"data ([baseline_metrics.json](evidence/baseline_metrics.json)), {ex['as_of']} for the fixture. Every answer states it, "
        "and the freshness policy is in [data_quality.md](data_quality.md#update-and-freshness-policy).", "",
        "**Source hashes.** `_source_files` keeps the size and SHA-256 of every file a load read, flat tables included. "
        "`make lineage` (`python -m data.lineage --verify --raw-dir $RAW_DATA_DIR`) exits 1 if a served row has no lineage, "
        "names a run that did not succeed or a file with no hash, or if a file on disk no longer has the recorded hash.", "",
        f"**Export hashes.** [`lake_manifest.json`](evidence/lake_manifest.json) is the manifest `make lake` wrote for the "
        f"warehouse copy described above ({manifest['generated_at'][:10]}, code `{manifest['code_version']}`): silver from load "
        f"{', '.join(f'`{r}`' for r in runs)}, gold from build {', '.join(f'`{r}`' for r in gold_runs)}, "
        f"{len(manifest['files'])} files, {n(total)} bytes.", "",
        "| File | Rows | Bytes | SHA-256 (first 16) |", "|---|---|---|---|",
        *(f"| `{f['path']}` | {n(f['rows'])} | {n(f['bytes'])} | `{f['sha256'][:16]}` |" for f in manifest["files"]), "",
        "`make lake VERIFY=1` re-hashes each file, reads its rows and schema back and, with the warehouse, compares the row "
        "counts; an edited, truncated, swapped or missing file fails. The Parquet files are not in the repository, and a new "
        "export has other bytes (its rows carry their run ids and build times), so these hashes check that export, not a re-run.",
    ]
    return L


def render(report: dict, manifest: dict, baseline: dict, validation: dict, example: dict) -> str:
    from data.gold import MARTS
    from data.pipeline import RunConfig

    threshold = RunConfig.__dataclass_fields__["max_quarantine_rate"].default
    sample = demo_sample()
    names = list(report["tables"]) + [m.name for m in MARTS]
    read_by = readers(names)
    t = report["tables"]
    exported = {f["table"] for f in manifest["files"]}
    if disagree := [f["table"] for f in manifest["files"] if f["table"] in t and f["rows"] != t[f["table"]]["rows_new"] + t[f["table"]]["rows_updated"]]:
        raise ValueError(f"the export and the last full load disagree on the rows of {disagree}: the page says they agree")
    exported_silver = [f["table"] for f in manifest["files"] if f["layer"] == "silver"]
    L = [
        "# Data engineering at a glance", "",
        "<!-- Generated by `python -m eval.data_page`; tests/test_data_page.py fails if this page differs. Do not edit by hand. -->", "",
        "How the organizer's files become the rows the agent answers from, and how each step can be checked. Every figure is "
        "read from a committed report: [`quality_report.json`](../data/reports/quality_report.json) (the last full load), "
        "[`lake_manifest.json`](evidence/lake_manifest.json) (the Parquet export) and the code. The detail behind each section: "
        "[data_engineering.md](data_engineering.md) (layers, measured load times, guarantees and their tests, what is not built), "
        "[data_quality.md](data_quality.md) (contract, checks, findings, freshness), "
        "[data-validation-catalog.md](data-validation-catalog.md) (each defect of the dataset and its rule) and "
        "[dataset-audit.md](dataset-audit.md).", "",
        "## The flow", "",
        *_flow(report, manifest, threshold, sample), "",
        f"A table rolls back when more than {threshold:.0%} of its batch is quarantined (`--max-quarantine-rate`) or a required "
        "column is missing; the warehouse keeps its previous state. A gold mart that fails its column contract, its grain or "
        "its reconciliation to silver rolls back the same way. The agent reads silver; only the baseline report reads gold. "
        f"The demo on Render loads a sample, `{sample}` ([render.yaml](../render.yaml)), so the counts below are not the demo's.", "",
        "## Each layer in numbers", "",
        f"Silver from the last full load (`{report['run_id']}`, {len(t)} tables, "
        f"{n(sum(v['rows_new'] + v['rows_updated'] for v in t.values()))} rows). Gold and the export come from the Parquet copy "
        f"of a full-data warehouse with {len(exported_silver)} of those tables ({', '.join(f'`{x}`' for x in exported_silver)})"
        + (", so `gold_contact_demand`, which needs `call_center_interactions`, is not there (its one measured row count is in "
           "[data_engineering.md](data_engineering.md#the-gold-marts))" if "gold_contact_demand" not in exported else "")
        + ". Where both have a table, its rows agree.", "",
        *_layers(report, manifest, read_by), "",
        "Bronze is not copied: the files stay where they were delivered and the hash in `_source_files` proves what was read. "
        "\"Read by\" lists the modules under `agent/`, `api/` and `analysis/` that query the table.", "",
        "## One row, end to end", "",
        *_example(example, read_by),
        "## Run ids, as-of and hashes", "",
        *_hashes(report, manifest, baseline["serving_data_facts"]["data_as_of"], example), "",
        "## Quality checks of the last full load", "",
        "Rules are declared in [`data/contracts.py`](../data/contracts.py) and run by [`data/quality.py`](../data/quality.py), "
        "inside each table's load transaction ([`data/pipeline.py`](../data/pipeline.py)). Tests: "
        "[`test_pipeline.py`](../tests/test_pipeline.py) (contracts, quarantine, rollback, late partitions, schema evolution), "
        "[`test_cross_checks.py`](../tests/test_cross_checks.py), [`test_data_ml_validation.py`](../tests/test_data_ml_validation.py) "
        "(one test per documented claim), [`test_gold.py`](../tests/test_gold.py), [`test_lake.py`](../tests/test_lake.py) and "
        "[`test_data_page.py`](../tests/test_data_page.py) (this page).", "",
        *_quality(report, validation), "",
        "## Reproduce", "",
        "```bash",
        "# The whole chain on the fixture, no S3 and no keys; /tmp keeps the committed report untouched",
        "make pipeline INGEST=ingest-local RAW_DATA_DIR=tests/fixtures/raw DUCKDB_PATH=/tmp/cecilai.duckdb QUALITY_REPORT=/tmp/quality.json",
        f"DUCKDB_PATH=/tmp/cecilai.duckdb python -m data.lineage --row {EXAMPLE_TABLE} {EXAMPLE_KEY}   # the row above",
        "DUCKDB_PATH=/tmp/cecilai.duckdb python -m data.lineage                           # per table: last load, files, hashes",
        "",
        "# The full dataset: ingest -> gold -> gold VERIFY -> lineage -> lake -> lake VERIFY, stopping at the first failure",
        "make pipeline                                            # from the organizer's S3 bucket",
        "make pipeline INGEST=ingest-local RAW_DATA_DIR=data/raw  # from a local copy",
        "",
        "make validate-data-ml   # contracts, quality, lineage and freshness as PASS/FAIL; writes nothing",
        "python -m eval.data_page   # regenerate this page",
        "```", "",
        "`make pipeline` with no variables writes the warehouse to `DUCKDB_PATH` and the report to "
        "`data/reports/quality_report.json`, the committed one this page reads.", "",
    ]
    return "\n".join(L)


def inputs(example: dict | None = None) -> tuple:
    if example is None:
        with tempfile.TemporaryDirectory() as tmp:
            example = collect_example(Path(tmp))
    return _read(REPORT), _read(MANIFEST), _read(BASELINE), _read(VALIDATION), example


def main() -> None:
    page = render(*inputs())
    (ROOT / OUT).write_text(page, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
