"""The README's headline figures against the generated reports: a number edited by hand, or left behind when a report
was regenerated, fails here instead of in front of a reader.

    python -m eval.check_readme        # exit 1 and a list of mismatches, or "README figures match the reports"
    python -m eval.check_readme --write-latencies   # first copies the reports' latencies into the docs (make sync-eval-latencies)

It reads the two results tables of the README (offline and live) and compares every figure with the same cell of
`eval/reports/system_eval*.json`; it also flags any case count the README states that is not the reports' count.
Only the headline tables are checked: prose, footnotes and the human-baseline figures are not.

It also checks the latencies per case that EVALUATION.md and the slides cite (LATENCY_ROWS), and the landing's figures
that depend on the machine (LANDING_LATENCIES and LANDING_DATES, in web/src/landing/figures.ts). The offline ones change
with the machine that regenerates the reports, so a regeneration that leaves the docs or the landing behind fails here;
`--write-latencies` (`make sync-eval-latencies`) copies them, touching only those cells and those values.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
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


# The landing (web/src/landing/figures.ts) binds each figure to a field of a report, and its test fails when the two differ.
# The offline latencies and the day of the offline run change with the machine that regenerates the reports, so they are
# written here too. Only these, by name: every other figure of the landing (security, live, ...) is never touched.
LANDING = Path("web/src/landing/figures.ts")
LANDING_SOURCES = {"OFFLINE": "system_eval", "ADVERSARIAL": "system_eval_adversarial"}
LANDING_SYSTEMS = {"KEYWORD": "baseline", "IDEAL": "proposed (scripted)", "ADV": "proposed (adversarial)"}
LANDING_LATENCIES = (
    ("keywordLatencyP50", "system_eval", "baseline", "latency_ms_p50"),
    ("keywordLatencyP95", "system_eval", "baseline", "latency_ms_p95"),
    ("idealLatencyP50", "system_eval", "proposed (scripted)", "latency_ms_p50"),
    ("idealLatencyP95", "system_eval", "proposed (scripted)", "latency_ms_p95"),
    ("adversarialLatencyP50", "system_eval_adversarial", "proposed (adversarial)", "latency_ms_p50"),
    ("adversarialLatencyP95", "system_eval_adversarial", "proposed (adversarial)", "latency_ms_p95"),
)
# The day the landing gives for the offline run, and the reports whose `generated_at` must all fall on it.
LANDING_DATES = (("offlineRunDate", ("system_eval", "system_eval_adversarial")),)
_FIGURE = re.compile(r"  (?P<name>\w+): json\((?P<value>\d+(?:\.\d+)?), (?P<digits>\d), (?P<source>[A-Z]+), \[\.\.\.(?P<system>[A-Z]+), '(?P<field>\w+)'\]\),")
_DAY = re.compile(r"export const (?P<name>\w+): Day = \{ iso: '(?P<iso>\d{4}-\d{2}-\d{2})', source: (?P<source>[A-Z]+), at: \['generated_at'\] \}")


def _fixed(value: float, digits: int) -> str:
    """`value` with `digits` decimals, half up on its decimal form: what the landing's test computes with toFixed."""
    return str(Decimal(repr(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def _one_line(lines: list[str], start: str, pattern: re.Pattern) -> tuple[int, re.Match] | str:
    """The only line that starts with `start`, matched in full by `pattern`; or why it is not there or not as expected."""
    at = [i for i, ln in enumerate(lines) if ln.startswith(start)]
    if len(at) != 1:
        return f"{len(at)} lines start with {start.strip()!r}, expected one"
    match = pattern.fullmatch(lines[at[0]])
    return (at[0], match) if match else f"{lines[at[0]].strip()!r} is not shaped as expected"


def landing(root: Path = Path("."), write: bool = False) -> list[str]:
    """The landing's machine-dependent figures against their reports. With `write`, each value is replaced by the report's,
    and nothing else of the file changes; if any line is missing or not shaped as expected, the file is not written at all."""
    path = root / LANDING
    lines = path.read_text(encoding="utf-8").split("\n")
    problems, stale = [], []
    for name, report, system, field in LANDING_LATENCIES:
        found = _one_line(lines, f"  {name}: ", _FIGURE)
        if isinstance(found, str):
            problems.append(f"{LANDING}: {found}")
            continue
        i, m = found
        if (LANDING_SOURCES.get(m["source"]), LANDING_SYSTEMS.get(m["system"]), m["field"]) != (report, system, field):
            problems.append(f"{LANDING}, {name}: bound to {m['source']} › {m['system']} › {m['field']}, expected {report} › {system} › {field}")
            continue
        want = _fixed(load(report)[system][field], int(m["digits"]))
        if Decimal(m["value"]) != Decimal(want):
            stale.append(f"{LANDING}, {name}: says {m['value']}, {report}.json says {want}")
            lines[i] = lines[i][:m.start("value")] + want + lines[i][m.end("value"):]
    for name, reports in LANDING_DATES:
        found = _one_line(lines, f"export const {name}: Day = ", _DAY)
        if isinstance(found, str):
            problems.append(f"{LANDING}: {found}")
            continue
        i, m = found
        if LANDING_SOURCES.get(m["source"]) != reports[0]:
            problems.append(f"{LANDING}, {name}: cites {m['source']}, expected the report {reports[0]}")
            continue
        days = {json.loads((REPORTS / f"{r}.json").read_text(encoding="utf-8"))["generated_at"][:10] for r in reports}
        if len(days) != 1:
            problems.append(f"{LANDING}, {name}: {', '.join(reports)} were generated on different days ({', '.join(sorted(days))})")
            continue
        want = days.pop()
        if m["iso"] != want:
            stale.append(f"{LANDING}, {name}: says {m['iso']}, the reports were generated on {want}")
            lines[i] = lines[i][:m.start("iso")] + want + lines[i][m.end("iso"):]
    if write and not problems:
        text = "\n".join(lines)
        if text != path.read_text(encoding="utf-8"):
            path.write_text(text, encoding="utf-8")
        return []
    return problems + stale


def check_latencies(root: Path = Path(".")) -> list[str]:
    return latencies(root) + landing(root)


def main(argv: list[str] | tuple = ()) -> int:
    ap = argparse.ArgumentParser(description="the docs' figures against the generated reports")
    ap.add_argument("--write-latencies", action="store_true",
                    help="copy the reports' latencies into the cells of LATENCY_ROWS (EVALUATION.md, the slides) and the "
                         "landing's machine-dependent figures (web/src/landing/figures.ts), then check")
    if ap.parse_args(list(argv)).write_latencies:
        for problem in latencies(write=True) + landing(write=True):
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
