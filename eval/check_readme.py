"""The README's headline figures against the generated reports: a number edited by hand, or left behind when a report
was regenerated, fails here instead of in front of a reader.

    python -m eval.check_readme        # exit 1 and a list of mismatches, or "README figures match the reports"
    python -m eval.check_readme --write-latencies   # first copies the reports' latencies into the docs (make sync-eval-latencies)

It reads the two results tables of the README (offline and live) and compares every figure with the same cell of
`eval/reports/system_eval*.json`; it also flags any case count the README states that is not the reports' count.
Only the headline tables are checked: prose, footnotes and the human-baseline figures are not.

It also checks the latencies per case that EVALUATION.md and the slides cite (LATENCY_ROWS). The offline ones change with
the machine that regenerates the reports, so a regeneration that leaves the docs behind fails here; `--write-latencies`
(`make sync-eval-latencies`) copies them, touching only those cells.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPORTS = Path("eval/reports")
NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")  # decimal point; a comma only groups thousands ("3,425" is one number)


def load(name: str) -> dict:
    return json.loads((REPORTS / f"{name}.json").read_text(encoding="utf-8"))["systems"]


def numbers(cell: str) -> list[float]:
    return [float(x.replace(",", "")) for x in NUM.findall(cell)]


def pct(r: dict) -> list[float]:
    return [round(r["rate"] * 100, 1)]


def with_ci(r: dict) -> list[float]:
    return pct(r) + [round(r["ci95"][0] * 100, 1), round(r["ci95"][1] * 100, 1)]


def k_of_n(r: dict) -> list[float]:
    return [r["k"], r["n"]]


# README row label -> how each column's cell is derived from a system's metrics
ROWS = {
    "Safe automated resolution": lambda m: with_ci(m["safe_automated_resolution"]),
    "Escalation recall": lambda m: pct(m["escalation_recall"]),
    "Missed escalations": lambda m: [m["missed_escalations_n"]],
    "Handoff completeness": lambda m: pct(m["handoff_completeness"]),
    "Unsafe outcomes": lambda m: k_of_n(m["unsafe_outcomes"]),
    "Cases that sent a customer record to the model": lambda m: k_of_n(m["records_sent_to_model"]),
}
LIVE_ROWS = {k: ROWS[k] for k in ("Safe automated resolution", "Escalation recall")}


def check_table(lines: list[str], header_start: str, rows: dict, columns: list[dict | None]) -> list[str]:
    """Cells of the table whose header starts with `header_start`, one entry of `columns` per data column."""
    start = next(i for i, ln in enumerate(lines) if ln.startswith(header_start))
    problems = []
    for ln in lines[start + 2:]:
        if not ln.startswith("|"):
            break
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        label = cells[0].replace("**", "")
        if label not in rows:
            continue
        for cell, metrics in zip(cells[1:], columns):
            if metrics is None or not NUM.search(cell):
                continue
            want, got = rows[label](metrics), numbers(cell)
            if got[:len(want)] != want:
                problems.append(f"{label}: README says {cell!r}, the report says {want}")
    return problems


# (file, row label, one entry per data column: None, or (report, system key fragment, template)). A template fixes how the
# cell states the report's p50 and p95 and in which unit: ms as the report has it, or seconds rounded to a tenth.
FIG = r"(\d+(?:\.\d+)?)"
TEMPLATES = {
    "handling_ms": ("{p50} ms per case (p95 {p95} ms)", "ms"),
    "pair_ms": ("{p50} / {p95} ms", "ms"),
    "pair_s": ("{p50} / {p95} s", "s"),
    "total_s": ("{p50} s p50, {p95} s p95", "s"),
}
LATENCY_ROWS = (
    ("EVALUATION.md", "Handling time", [None, ("system_eval", "baseline", "handling_ms"), ("system_eval", "proposed (scripted)", "handling_ms")]),
    ("EVALUATION.md", "Total per inquiry", [None, None, ("system_eval_live", "sonnet", "total_s")]),
    ("EVALUATION.md", "Latency p50 / p95 per case (non-LLM, local)", [("system_eval", "baseline", "pair_ms"), ("system_eval", "proposed (scripted)", "pair_ms"),
                                                                      ("system_eval_adversarial", "proposed (adversarial)", "pair_ms")]),
    ("docs/slides_outline.md", "p50 / p95 latency per case", [("system_eval", "baseline", "pair_ms"), ("system_eval_live", "sonnet", "pair_s"),
                                                              ("system_eval_live", "haiku", "pair_s")]),
)


def _pattern(template: str) -> re.Pattern:
    """The template as a pattern that finds it inside a cell (bold or a note around it are the cell's own text)."""
    return re.compile(r"(?<![\d.])" + re.escape(template).replace(r"\{p50\}", FIG).replace(r"\{p95\}", FIG) + r"(?![\w.])")


def _latency(report: str, key: str, unit: str) -> tuple[str, str]:
    m = next(v for k, v in load(report).items() if key in k)
    if unit == "ms":
        return f"{m['latency_ms_p50']:.1f}", f"{m['latency_ms_p95']:.1f}"
    return f"{m['latency_ms_p50'] / 1000:.1f}", f"{m['latency_ms_p95'] / 1000:.1f}"


def latencies(root: Path = Path("."), write: bool = False) -> list[str]:
    """Each cell of LATENCY_ROWS against its report: the row has exactly one cell per column, and each checked cell holds its
    template once, in its unit, with the report's p50 and p95. With `write`, a checked cell that holds its template gets the
    report's figures (the rest of the cell, and every other cell and line, are kept); what cannot be fixed that way is
    returned as a problem and not written."""
    problems, texts = [], {}
    for doc, label, columns in LATENCY_ROWS:
        lines = texts.setdefault(doc, (root / doc).read_text(encoding="utf-8").split("\n"))
        at = [i for i, ln in enumerate(lines) if ln.startswith(f"| {label} |")]
        if len(at) != 1:
            problems.append(f"{doc}: {len(at)} rows labeled {label!r}, expected one")
            continue
        cells = [c.strip() for c in lines[at[0]].strip().strip("|").split("|")][1:]
        if len(cells) != len(columns):
            problems.append(f"{doc}, {label}: {len(cells)} cells, expected {len(columns)}")
            continue
        for i, column in enumerate(columns):
            if column is None:
                continue
            report, key, name = column
            template, unit = TEMPLATES[name]
            p50, p95 = _latency(report, key, unit)
            found = _pattern(template).findall(cells[i])
            if len(found) != 1:
                problems.append(f"{doc}, {label}: {cells[i]!r} does not state p50 and p95 once as {template!r} (unit {unit})")
            elif write:
                cells[i] = _pattern(template).sub(template.format(p50=p50, p95=p95), cells[i])
            elif [float(x) for x in found[0]] != [float(p50), float(p95)]:
                problems.append(f"{doc}, {label}: says {cells[i]!r}, the report says p50 / p95 = {p50} / {p95} {unit}")
        lines[at[0]] = "| " + " | ".join([label, *cells]) + " |"
    if write:
        for doc, lines in texts.items():
            text = "\n".join(lines)
            if text != (root / doc).read_text(encoding="utf-8"):
                (root / doc).write_text(text, encoding="utf-8")
    return problems


def check_latencies(root: Path = Path(".")) -> list[str]:
    return latencies(root)


def main(argv: list[str] | tuple = ()) -> int:
    ap = argparse.ArgumentParser(description="the docs' figures against the generated reports")
    ap.add_argument("--write-latencies", action="store_true",
                    help="copy the reports' latencies into the cells of LATENCY_ROWS (EVALUATION.md, the slides), then check")
    if ap.parse_args(list(argv)).write_latencies:
        for problem in latencies(write=True):
            print("not written:", problem)
    text = Path("README.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    base_and_ideal, adversarial = load("system_eval"), load("system_eval_adversarial")
    live = load("system_eval_live")
    n = json.loads((REPORTS / "system_eval.json").read_text(encoding="utf-8"))["n_cases"]
    problems = check_table(lines, "| | Keyword bot", ROWS, [base_and_ideal["baseline"], base_and_ideal["proposed (scripted)"],
                                                           adversarial["proposed (adversarial)"]])
    problems += check_table(lines, "| | Claude Sonnet 5", LIVE_ROWS, [next(m for k, m in live.items() if "sonnet" in k),
                                                                     next(m for k, m in live.items() if "haiku" in k)])
    counts = {int(a or b) for a, b in re.findall(r"\b(5\d\d) cases\b|/ (5\d\d)\b", text)}
    problems += [f"case count: README says {c}, the reports have {n}" for c in sorted(counts) if c != n]
    problems += check_latencies()
    print("\n".join(problems) if problems else "README figures match the reports")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
