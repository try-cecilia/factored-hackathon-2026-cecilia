"""The evidence table of docs/EVIDENCE.md, generated from the committed reports, and a check that the page still says it.

    python -m eval.evidence_table           # print the table
    python -m eval.evidence_table --write   # rewrite the table and the line numbers of the code links in docs/EVIDENCE.md
    python -m eval.evidence_table --check   # exit 1 and a list of differences, or "docs/EVIDENCE.md matches the reports and the code"

Every cell of the table is read from a field of a report in `eval/reports/` (counts, model, date and the `policy_sha256`
fingerprint each report carries), so regenerating a report and running `--write` is all it takes to update the page. The
fingerprint is shown as the report carries it and compared with the one this checkout computes (eval/fingerprint.py): a
report measured on other code says so in its row instead of passing for current. The caveats are fixed text, taken from
EVALUATION.md and LIMITATIONS.md.

The page's links to code are written as [`symbol`](../path.py#L123). The check parses that file and finds where `symbol` is
defined in its own scope (a def, a class or an assignment at the top of the module; `Class.method` only inside that class),
and fails if the line number is not that one or the symbol is not there. Any other relative link must point to a file that
exists, except the files the public export removes (`ops/export_public.py`, `REMOVE_GLOBS`): the per-case reports. `--write`
moves the line numbers to where the definitions are now, and exits 1 only if something it cannot fix is left.

This module is not part of what the evaluation measures: it only reads reports, and it is outside the fingerprint.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "eval" / "reports"
PAGE = ROOT / "docs" / "EVIDENCE.md"
START, END = "<!-- evidence-table:start -->", "<!-- evidence-table:end -->"
HEADER = ("| Result | Model | Date (UTC) | Fingerprint | Same code as now | n | Figures (k / denominator) | Report | Caveats |\n"
          "|---|---|---|---|---|---|---|---|---|")
CODE_LINK = re.compile(r"\[`([\w.]+)`\]\((\.\./[^)#\s]+)#L(\d+)\)")
FILE_LINK = re.compile(r"\]\(((?:\.\./|\./)?[\w./-]+?)(?:#[\w-]*)?\)")

CAVEATS = {
    "offline": "Scripted ideal model: an upper bound on the model's understanding, with no model latency or cost. 0 observed "
               "bounds the true rate below about 3/n, not at 0.",
    "adversarial": "Scripted bad model written by the team (obeys injections, asks for other customers' products, invents figures): "
                   "it shows that safety does not depend on the model, not what a real bad model would do.",
    "baseline": "Deterministic keyword bot that shares session, policy, tools, ownership checks, tickets and renderer: the gap "
                "isolates understanding. It sends nothing to a model.",
    "reserved": "Team-written cases on 5 fixture customers. Batch 2 was written after seeing batch 1's failures and batch 3 after "
                "the judge was fixed; the fixes came after seeing them, so post-fix figures are regression evidence, not held out. "
                "The records sent to the model are the lowercase, split product id (\"prd fix 0006\"), a documented masking limit.",
    "live": "Stratified sample of the test split (3 cases per case type and language), not all of it. The headline is run 1; "
            "only run 1 keeps per-case rows, so a finding of runs 2 and 3 is known by its count and type, not its case.",
    "live_haiku": "Its one unsafe outcome (run 2) is `text_outside_the_templates`, judged before the judge learned replies of "
                  "several reads; it could not be inspected.",
    "ablation": "Offline, scripted models. Cumulative ladder by groups of controls: no effect is attributed to one control. The "
                "naive variants were built by the team and never open a trace, so the confirmation of the action is not measured.",
    "classifier": "Test utterances written by the team (same-author bias). The keyword baseline and the lexicon-only guard are "
                  "an upper bound: two lexicon patterns were added after the split was scored. Not a policy_sha256 report.",
    "red_team": "One session on the deployed demo by people who did not build the assistant (a teammate and friends of the "
                "team); {burst_turns} turns came in pasted bursts; participants' notes still to come. The report records "
                "neither the model nor a fingerprint.",
}


def _load(name: str, reports: Path) -> dict:
    return json.loads((reports / name).read_text(encoding="utf-8"))


def _kn(metric: dict | None) -> str:
    return f"{metric['k']}/{metric['n']}" if metric and metric.get("n") else "n/a"


def _figures(*pairs: tuple[str, str]) -> str:
    return " · ".join(f"{label} {value}" for label, value in pairs)


def _system(report: dict, prefix: str) -> dict:
    (system,) = [s for name, s in report["systems"].items() if name.startswith(prefix)]
    return system


def _row(result: str, model: str, date: str, fingerprint: str | None, n: str, figures: str, report: str, caveat: str) -> dict:
    return {"result": result, "model": model, "date": date[:10] if date else "not recorded", "fingerprint": fingerprint,
            "n": n, "figures": figures, "report": report, "caveat": caveat}


def _offline_rows(reports: Path) -> list[dict]:
    rows = []
    for name, prefix, label, key, link in (
            ("system_eval.json", "proposed (scripted)", "Offline, ideal model", "offline", "SYSTEM_EVAL.md"),
            ("system_eval_adversarial.json", "proposed (adversarial)", "Offline, adversarial model", "adversarial",
             "SYSTEM_EVAL_ADVERSARIAL.md"),
            ("system_eval.json", "baseline", "Baseline: keyword bot", "baseline", "SYSTEM_EVAL.md")):
        report = _load(name, reports)
        s = _system(report, prefix)
        model = "keyword rules, no model" if key == "baseline" else f"scripted {key if key == 'adversarial' else 'ideal'}, " \
                                                                   f"prompt {report['prompt_version']}"
        figures = _figures(("unsafe", _kn(s["unsafe_outcomes"])),
                           ("records to the model", _kn(s["records_sent_to_model"])),
                           ("safe automated resolution", _kn(s["safe_automated_resolution"])),
                           ("escalation recall", _kn(s["escalation_recall"])),
                           ("handoff completeness", _kn(s["handoff_completeness"])))
        rows.append(_row(label, model, report["generated_at"], report.get("policy_sha256"), f"{s['n_cases']} cases ({report['split']} split)",
                         figures, f"{link}, {name}", CAVEATS[key]))
    return rows


def _reserved_rows(reports: Path) -> list[dict]:
    report, rows = _load("failure_eval.json", reports), []
    reserved = report["reserved"]
    for mode, label in (("scripted", "ideal"), ("adversarial", "adversarial")):
        cell = reserved[mode]["table"]["all"]["all"]
        n = cell["n"]
        figures = _figures(("unsafe", f"{cell['unsafe']}/{n}"), ("crashes", f"{cell['crashed']}/{n}"),
                           ("records to the model", f"{cell['records_sent_to_model']}/{n}"),
                           ("handled", _kn(cell["handled"])), ("safe", _kn(cell["safe"])))
        rows.append(_row(f"Reserved failure set, {label} model", f"scripted {label}, prompt {report['prompt_version']}",
                         report["generated_at"], report.get("policy_sha256"),
                         f"{reserved['n_cases']} cases, {len(reserved['cases_files'])} batches", figures,
                         "FAILURE_EVAL.md, failure_eval.json", CAVEATS["reserved"]))
    return rows


def _worst(system: dict, metric: str) -> str:
    """The highest count of `metric` in any run, from the spread of the repeats (rate × n)."""
    spread = (system.get("repeat_variability") or {}).get(metric)
    n = system[metric]["n"]
    return f"{round(spread['max'] * n)}/{n}" if spread else _kn(system[metric])


def _live_rows(reports: Path) -> list[dict]:
    report, rows = _load("system_eval_live.json", reports), []
    for name, s in report["systems"].items():
        served = ", ".join(s.get("served_by") or {}) or name
        runs = (s.get("repeat_variability") or {}).get("runs", 1)
        figures = _figures(("unsafe, run 1", _kn(s["unsafe_outcomes"])), (f"unsafe, worst of {runs} runs", _worst(s, "unsafe_outcomes")),
                           ("records to the model, worst run", _worst(s, "records_sent_to_model")),
                           ("safe automated resolution, run 1", _kn(s["safe_automated_resolution"])),
                           ("escalation recall, run 1", _kn(s["escalation_recall"])))
        caveat = CAVEATS["live"] + (" " + CAVEATS["live_haiku"] if "haiku" in name else "")
        rows.append(_row(f"Live, {served.split('/')[-1]}", f"{served}, prompt {report['prompt_version']}", report["generated_at"],
                         report.get("policy_sha256"), f"{s['n_cases']} cases × {runs} runs ({report['split']} split)", figures,
                         "SYSTEM_EVAL_LIVE.md, system_eval_live.json", caveat))
    return rows


def _ablation_row(reports: Path) -> dict:
    report = _load("ablation.json", reports)
    meta, res = report["meta"], report["results"]
    figures = _figures(("unsafe with no control, ideal", _kn(res["naive-plain/scripted"]["unsafe_outcomes"])),
                       ("bad", _kn(res["naive-plain/adversarial"]["unsafe_outcomes"])),
                       ("unsafe with every control, ideal", _kn(res["proposed/scripted"]["unsafe_outcomes"])),
                       ("bad", _kn(res["proposed/adversarial"]["unsafe_outcomes"])))
    return _row("Ablation: groups of controls removed", "scripted ideal and bad", meta["generated_at"], meta.get("policy_sha256"),
                f"{meta['n_cases']} cases × {len(res)} variants ({meta['split']} split)", figures, "ABLATION.md, ablation.json",
                CAVEATS["ablation"])


def _classifier_row(reports: Path) -> dict:
    report = _load("intent_classifier.json", reports)
    test = report["test"]
    guard = test["escalation_guard"]["lexicon_or_classifier (runtime)"]
    figures = _figures(("accuracy, learned", _kn(test["learned"]["accuracy"])), ("keywords", _kn(test["baseline_keywords"]["accuracy"])),
                       ("runtime guard recall", _kn(guard["recall"])), ("false escalations", _kn(guard["false_escalation"])))
    model = f"TF-IDF {report['chosen_variant']} + logistic regression, scikit-learn {report['versions']['sklearn']}"
    return _row("Intent classifier (learned component)", model, report["generated_at"], report.get("policy_sha256"),
                f"{test['n']} test utterances", figures, "intent_classifier.md, intent_classifier.json", CAVEATS["classifier"])


def _red_team_row(reports: Path) -> dict:
    report = _load("red_team.json", reports)
    day = datetime.fromtimestamp(report["window"]["first_turn"], tz=timezone.utc).date().isoformat()
    findings = sum(len(v) for v in report["checks"].values())
    figures = _figures(("findings in the records", f"{findings} on {len(report['checks'])} checks"),
                       ("turns on a dead session", str(report["turns_without_session"])), ("tickets", str(report["tickets_opened"])),
                       ("traces opened", str(report["traces_opened"])))
    return _row("Red team of the deployed demo", "deployed demo, not recorded in the report", day, report.get("policy_sha256"),
                f"{report['turns']} turns in {report['sessions']} sessions", figures, "RED_TEAM.md, red_team.json",
                CAVEATS["red_team"].format(burst_turns=report["bursts"]["turns"]))


def rows(reports: Path = REPORTS) -> list[dict]:
    return [*_offline_rows(reports), *_reserved_rows(reports), *_live_rows(reports), _ablation_row(reports),
            _classifier_row(reports), _red_team_row(reports)]


def _report_links(cell: str) -> str:
    return ", ".join(f"[`{name}`](../eval/reports/{name})" for name in cell.split(", "))


def table(reports: Path = REPORTS, current: str | None = None) -> str:
    if current is None:
        from eval.fingerprint import policy_fingerprint
        current = policy_fingerprint()
    lines = [f"Fingerprint of the code in this checkout: `{current[:12]}` (first 12 of 64 hex digits; `eval/fingerprint.py`).", "",
             HEADER]
    for r in rows(reports):
        fp = r["fingerprint"]
        same = "n/a" if fp is None else "yes" if fp == current else "**no**"
        lines.append("| " + " | ".join([r["result"], r["model"], r["date"], f"`{fp[:12]}`" if fp else "not recorded", same, r["n"],
                                         r["figures"], _report_links(r["report"]), r["caveat"]]) + " |")
    return "\n".join(lines)


# --- the page ---------------------------------------------------------------------------------------------------------------

def _defines(node: ast.AST, name: str) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == name
    if isinstance(node, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
    if isinstance(node, ast.AnnAssign):
        return isinstance(node.target, ast.Name) and node.target.id == name
    return False


def definition_line(path: Path, symbol: str) -> int | None:
    """The 1-based line where `symbol` is defined in `path`, scope by scope: the first part at the top of the module, each
    next part directly in the body of the class the previous one names (`A.run` is never `B.run`). A leading part that is
    the module's own name (`router.pre_llm` in router.py) is only a label. None if it is not defined there."""
    parts = symbol.split(".")
    if len(parts) > 1 and parts[0] == path.stem:
        parts = parts[1:]
    if path.suffix != ".py":
        return None
    node: ast.AST = ast.parse(path.read_text(encoding="utf-8"))
    for i, part in enumerate(parts):
        if i and not isinstance(node, ast.ClassDef):
            return None
        found = next((child for child in node.body if _defines(child, part)), None)
        if found is None:
            return None
        node = found
    return node.lineno


def _fix_code_links(text: str, page: Path, problems: list[str]) -> str:
    def fix(m: re.Match) -> str:
        symbol, rel, line = m[1], m[2], int(m[3])
        target = (page.parent / rel).resolve()
        if not target.is_file():
            problems.append(f"{symbol}: {rel} does not exist")
            return m[0]
        found = definition_line(target, symbol)
        if found is None:
            problems.append(f"{symbol}: not defined in {rel}")
            return m[0]
        if found != line:
            problems.append(f"{symbol}: the page says {rel}#L{line}, it is defined at line {found}")
        return f"[`{symbol}`]({rel}#L{found})"
    return CODE_LINK.sub(fix, text)


def _removed_by_export(path: Path, root: Path = ROOT) -> bool:
    """Whether the public export removes this file (it is then missing there by design, and only there)."""
    from ops.export_public import REMOVE_GLOBS
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    return any(fnmatch.fnmatch(rel, glob) for glob in REMOVE_GLOBS)


def _missing_files(text: str, page: Path, root: Path = ROOT) -> list[str]:
    """Relative links to nothing, other than the reports the export removes. `root` is the tree the page belongs to."""
    missing = []
    for rel in dict.fromkeys(FILE_LINK.findall(text)):
        target = (page.parent / rel).resolve()
        if "://" not in rel and not target.exists() and not _removed_by_export(target, root.resolve()):
            missing.append(f"link to {rel}: no such file")
    return missing


def render_page(text: str, reports: Path = REPORTS, page: Path = PAGE, current: str | None = None) -> tuple[str, list[str]]:
    """The page as it should be, and every problem found on the way (a link that cannot be fixed is a problem too)."""
    problems: list[str] = []
    if START not in text or END not in text:
        return text, [f"{page.name}: the table markers {START} and {END} are missing"]
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    new = f"{head}{START}\n{table(reports, current)}\n{END}{tail}"
    new = _fix_code_links(new, page, problems)
    return new, problems + _missing_files(new, page)


def check(page: Path = PAGE, reports: Path = REPORTS, current: str | None = None) -> list[str]:
    text = page.read_text(encoding="utf-8")
    new, problems = render_page(text, reports, page, current)
    if new != text:
        problems.append(f"{page.name} differs from what the reports and the code give: run `python -m eval.evidence_table --write`")
    return problems


def write(page: Path | None = None, reports: Path = REPORTS, current: str | None = None) -> list[str]:
    """Rewrite the page; what is still wrong after that (a symbol or a file that is not there) is returned. A line number
    that moved is fixed, not a problem."""
    page = page or PAGE
    new, _ = render_page(page.read_text(encoding="utf-8"), reports, page, current)
    page.write_text(new, encoding="utf-8")
    return render_page(new, reports, page, current)[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="rewrite the table and the code-link line numbers in the page")
    group.add_argument("--check", action="store_true", help="exit 1 if the page differs from the reports or the code")
    args = ap.parse_args(argv)
    if args.write:
        problems = write(PAGE)
        print("\n".join(problems) if problems else f"wrote {PAGE.name}")
        return 1 if problems else 0
    if args.check:
        problems = check(PAGE)
        print("\n".join(problems) if problems else f"{PAGE.name} matches the reports and the code")
        return 1 if problems else 0
    print(table())
    return 0


if __name__ == "__main__":
    sys.exit(main())
