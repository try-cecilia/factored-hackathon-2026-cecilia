"""The small live sample (a free-tier model, a few dozen cases), reproducible from versioned artifacts.

    python -m eval.live_sample select                 # -> eval/reports/live_sample_selection.json (the ids, and the rule)
    python -m eval.live_sample run --part reserved    # live model on the selected reserved cases, fixture warehouse
    python -m eval.live_sample run --part generated   # the same on the selected generated cases, full warehouse
    python -m eval.live_sample report                 # rebuilds the tables from the per-case rows

`select` needs no warehouse and no key: it reads the committed case files and applies a fixed rule, so the selection is a
function of the case files and the file it writes is checked against it (tests/test_live_sample.py). `run` needs the API
key of the model, paces the calls (a free tier limits tokens per minute) and appends one row per case to
`eval/reports/live_sample_groq_rows.jsonl`, the rows `eval.run_system_eval.judge` produces. `report` reads only those rows,
so every number of a sample's table comes from a file in the repository.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from eval import heldout
from eval import run_system_eval as rse
from eval.categories import CATEGORIES, LABEL, LANGS, cell, table
from eval.stats import fmt
from eval.workload import Case, load

REPORTS = Path("eval/reports")
SELECTION = REPORTS / "live_sample_selection.json"
ROWS = REPORTS / "live_sample_groq_rows.jsonl"
GENERATED_CASES = Path("eval/workload/cases_test.jsonl")
MODEL = "groq:openai/gpt-oss-120b"
PER_CELL = 2  # reserved cases per category and language
RULE = ("reserved: in each category and language, the first %d cases in file order (batch 1, then batch 2) whose ideal-model script has "
        "a step that calls the model; generated: one case per case type (types in alphabetical order), languages alternating ES, PT, "
        "taking the first case of the type in file order in the wanted language, or in the other one if the type has none." % PER_CELL)


def _calls_the_model(case: Case) -> bool:
    return any(step for step in case.script)


def select(reserved: list[Case] | None = None, generated: list[Case] | None = None) -> dict:
    reserved = reserved if reserved is not None else [c for path in (heldout.OUT, heldout.OUT2) for c in load(path)]
    generated = generated if generated is not None else load(GENERATED_CASES)
    picked_reserved: list[str] = []
    for category in CATEGORIES:
        for lang in LANGS:
            picked_reserved += [c.case_id for c in reserved if c.category == category and c.language == lang and _calls_the_model(c)][:PER_CELL]
    picked_generated: list[str] = []
    for i, template in enumerate(sorted({c.template for c in generated})):
        of_type = [c for c in generated if c.template == template]
        wanted = LANGS[i % 2]
        picked_generated.append(next((c for c in of_type if c.language == wanted), of_type[0]).case_id)
    return {"rule": RULE, "model": MODEL, "reserved": picked_reserved, "generated": picked_generated}


def write_selection(path: Path = SELECTION) -> dict:
    selection = select()
    path.write_text(json.dumps(selection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return selection


def cases_of(part: str, selection: dict) -> list[Case]:
    pool = [c for p in (heldout.OUT, heldout.OUT2) for c in load(p)] if part == "reserved" else load(GENERATED_CASES)
    by_id = {c.case_id: c for c in pool}
    return [by_id[i] for i in selection[part]]


def run_part(part: str, out: Path = ROWS, pace_s: float = 20.0, selection: dict | None = None) -> int:
    """The selected cases of one part, one at a time with a pause between them, each row appended as it is judged."""
    from agent.llm.client import LLMClient

    selection = selection or json.loads(SELECTION.read_text(encoding="utf-8"))
    provider, model = MODEL.split(":", 1)
    if not os.environ.get(f"{provider.upper()}_API_KEY"):
        sys.exit(f"{provider.upper()}_API_KEY is not set: nothing was run")
    os.environ["LLM_PROVIDERS"], os.environ[f"{provider.upper()}_MODEL"] = provider, model
    if part == "reserved":  # the fixture warehouse, as `make eval-failures` builds it
        os.environ["DUCKDB_PATH"] = str(Path(tempfile.mkdtemp(prefix="live_sample_")) / "fixture.duckdb")
        heldout.build_warehouse(Path(os.environ["DUCKDB_PATH"]))
    cases, client, n = cases_of(part, selection), LLMClient(), 0
    for case in cases:
        _, (row,) = rse.run("proposed", "live", [case], client)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"part": part, "model": MODEL, "row": row}, default=str, ensure_ascii=False) + "\n")
        n += 1
        time.sleep(pace_s)
    return n


def load_rows(path: Path = ROWS) -> dict[str, list[dict]]:
    parts: dict[str, list[dict]] = {"reserved": [], "generated": []}
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        parts[entry["part"]].append(entry["row"])
    return parts


def _pct(r: dict) -> str:
    return f"{fmt(r).rsplit(' (n=', 1)[0]} ({r['k']}/{r['n']})" if r["n"] else "n/a"


def report(rows: dict[str, list[dict]]) -> str:
    """The sample's tables, from its rows alone (handled as eval/categories.py defines it)."""
    md = []
    if rows["reserved"]:
        t = table(rows["reserved"])
        md += [f"## Failure categories: reserved set, {len(rows['reserved'])} cases\n", "| Category | ES | PT | Unsafe |", "|---|---|---|---|"]
        for cat in [*CATEGORIES, "all"]:
            es, pt, both = (t[cat][lang] for lang in (*LANGS, "all"))
            md.append(f"| {'**All**' if cat == 'all' else LABEL[cat]} | {_pct(es['handled'])} | {_pct(pt['handled'])} | {both['unsafe']} of {both['n']} |")
        md.append("\nNot handled:\n")
        failures = cell(rows["reserved"])["failures"]
        md += [f"- `{f['template']}` ({f['language']}): expected {f['expected']}, got {f['actual']}"
               + (f", unsafe: {', '.join(f['unsafe'])}" if f["unsafe"] else "") for f in failures] or ["None."]
    if rows["generated"]:
        m = rse.metrics(rows["generated"])
        md += [f"\n## Generated test workload: {len(rows['generated'])} cases, one per case type\n", "| | Result |", "|---|---|",
               f"| Safe automated resolution | {_pct(m['safe_automated_resolution'])} |", f"| Correct disposition | {_pct(m['disposition_accuracy'])} |",
               f"| Escalation recall | {_pct(m['escalation_recall'])} |", f"| Unsafe outcomes | {_pct(m['unsafe_outcomes'])} |",
               f"| Records sent to the model | {_pct(m['records_sent_to_model'])} |"]
    md.append("\nA small sample: one run, no repeats. With n this small the intervals are very wide and only say what it cannot rule out.")
    return "\n".join(md) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["select", "run", "report"])
    ap.add_argument("--part", choices=["reserved", "generated"])
    ap.add_argument("--rows", default=str(ROWS))
    ap.add_argument("--pace", type=float, default=20.0, help="seconds between cases (free tiers limit tokens per minute)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.action == "select":
        s = write_selection()
        print(f"{SELECTION}: {len(s['reserved'])} reserved and {len(s['generated'])} generated cases")
    elif a.action == "run":
        if not a.part:
            sys.exit("--part reserved|generated is required")
        print(f"{run_part(a.part, Path(a.rows), a.pace)} rows appended to {a.rows}")
    else:
        if not Path(a.rows).exists():
            sys.exit(f"{a.rows} does not exist: no live sample has been run with per-case rows yet (python -m eval.live_sample run)")
        print(report(load_rows(Path(a.rows))))


if __name__ == "__main__":
    main()
