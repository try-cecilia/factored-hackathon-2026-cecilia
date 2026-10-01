"""The README's headline figures against the generated reports: a number edited by hand, or left behind when a report
was regenerated, fails here instead of in front of a reader.

    python -m eval.check_readme        # exit 1 and a list of mismatches, or "README figures match the reports"

It reads the two results tables of the README (offline and live) and compares every figure with the same cell of
`eval/reports/system_eval*.json`; it also flags any case count the README states that is not the reports' count.
Only the headline tables are checked: prose, footnotes and the human-baseline figures are not.
"""
from __future__ import annotations

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


def main() -> int:
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
    print("\n".join(problems) if problems else "README figures match the reports")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
