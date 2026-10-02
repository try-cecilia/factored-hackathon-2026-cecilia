"""Data and ML good-practice validation: one command, one evidence report.

Runs `tests/test_data_ml_validation.py` (one test per claim in the documents; hermetic: the test warehouse, no S3 and
no keys) and gives the result per criterion: PASS or FAIL, the evidence each test recorded and the command that
reproduces it. A criterion passes only if tests ran and all of them passed: a skipped test, or one that could not be
collected, counts as FAIL.

    python -m eval.validate_data_ml                  # checks and writes nothing; warns if the versioned evidence is out of date
    python -m eval.validate_data_ml --out-dir DIR    # also writes data_ml_validation.{md,json} in DIR
    make evidence                                    # the same with DIR = docs/evidence: the explicit step that versions the evidence

Exits with code 1 if any criterion fails. Checking (the gate, the CI) touches no versioned file: the report's date and
commit change only when someone regenerates the evidence on purpose.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from data.pipeline import _git_sha

ROOT = Path(__file__).resolve().parent.parent
TESTS = "tests/test_data_ml_validation.py"
EVIDENCE_DIR = ROOT / "docs" / "evidence"
NAME = "data_ml_validation"

# test prefix -> criterion, and the document that makes the claim
CRITERIA = [
    ("contracts", "Contracts", "docs/data_quality.md (Pipeline, steps 2-5), data/contracts.py"),
    ("quality", "Quality", "docs/data_quality.md (Pipeline step 4, Findings)"),
    ("lineage", "Lineage", "docs/data_quality.md (Pipeline step 8), data/lineage.py"),
    ("freshness", "Freshness policy", "docs/data_quality.md (Update and freshness policy)"),
    ("learned", "A learned component against a baseline", "EVALUATION.md §2, eval/reports/intent_classifier.md"),
    ("leakage", "No data leakage", "EVALUATION.md §2, eval/leakage.py, LIMITATIONS.md (Data and ML)"),
]

# What these tests do not settle and is declared, so the report does not look like more than it is.
DECLARED = [
    "The training and held-out texts were written by the same team (LIMITATIONS.md, \"No usable text\"): the "
    "difference against the baseline is real on this held-out set, not a measurement on real customers.",
    "The chronological order (training and baseline frozen before the held-out set was written) cannot be proven with "
    "the git history, which starts with a single import; what is proven is that the files have not changed since they "
    "were measured (hashes).",
    "The similarity cut-offs (0.90 and 0.60) were set by looking at the distribution of the whole held-out, dev and test "
    "sets together; one phrase was left out (LIMITATIONS.md).",
    "The decision not to retrain the classifier with trace examples was made after seeing the test split "
    "(LIMITATIONS.md, \"The action\").",
    "A character similarity does not see a paraphrase in other words (eval/leakage.py).",
    "The quality report of the full run (`data/reports/quality_report.json`) comes from the organizer's bucket and is not "
    "regenerated here; these tests check that the document cites it correctly, not that the data are still those.",
]


def run_tests(xml_path: Path) -> subprocess.CompletedProcess:
    # junit_family=legacy: the only family that takes the per-test `evidence` property without a warning
    command = [sys.executable, "-m", "pytest", TESTS, "-q", "-p", "no:cacheprovider", "-o", "junit_family=legacy",
               f"--junitxml={xml_path}"]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def parse(xml_path: Path) -> list[dict]:
    if not xml_path.exists():
        return []
    out = []
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        problem = case.find("failure") if case.find("failure") is not None else case.find("error")
        status = "PASS"
        detail = ""
        if problem is not None:
            status, detail = "FAIL", (problem.get("message") or problem.text or "").strip().splitlines()[0][:300]
        elif case.find("skipped") is not None:
            status, detail = "FAIL", "skipped: a check that does not run does not count as passed"
        evidence = next((p.get("value") for p in case.iter("property") if p.get("name") == "evidence"), "")
        out.append({"test": case.get("name"), "status": status, "evidence": evidence, "detail": detail})
    return out


def summarize(cases: list[dict]) -> list[dict]:
    rows = []
    for prefix, title, source in CRITERIA:
        mine = [c for c in cases if c["test"].startswith(f"test_{prefix}_")]
        ok = bool(mine) and all(c["status"] == "PASS" for c in mine)
        rows.append({"id": prefix, "criterion": title, "source": source, "status": "PASS" if ok else "FAIL", "tests": mine,
                     "command": f"python -m pytest {TESTS} -k test_{prefix}_ -q"})
    return rows


def _title(test: str, prefix: str) -> str:
    return test.removeprefix(f"test_{prefix}_").replace("_", " ")


def to_markdown(rows: list[dict], generated_at: str, code: str, pytest_line: str) -> str:
    verdict = "PASS" if all(r["status"] == "PASS" for r in rows) else "FAIL"
    summary = "\n".join(f"| {r['criterion']} | **{r['status']}** | {sum(t['status'] == 'PASS' for t in r['tests'])}/{len(r['tests'])} | "
                        f"`{r['command']}` |" for r in rows)
    detail = []
    for r in rows:
        lines = "\n".join(f"| {_title(t['test'], r['id'])} | {t['status']} | {t['evidence'] or t['detail']} |" for t in r["tests"])
        detail.append(f"### {r['criterion']}: {r['status']}\n\nClaimed in: {r['source']}.\n\n| Test | Result | Evidence |\n|---|---|---|\n"
                      f"{lines or '| (no test ran) | FAIL | |'}")
    declared = "\n".join(f"- {d}" for d in DECLARED)
    return f"""# Data and ML good-practice validation (generated)

Generated by `make evidence` (`python -m eval.validate_data_ml --out-dir docs/evidence`) at {generated_at} on code `{code}`.
Rubric: "Data and ML good practice: contracts, quality, lineage, a freshness policy, and at least one learned component
against a baseline, without data leakage". Overall result: **{verdict}**. {pytest_line}

Each row is a test in `{TESTS}`: hermetic (the test warehouse in `tests/fixtures`, no S3 and no keys), and it fails if the
sentence of the document it cites stops being true. The evidence figures come from the test itself, not written by hand.

| Criterion | Result | Tests | Command |
|---|---|---|---|
{summary}

{(chr(10) * 2).join(detail)}

## What this does not settle (declared)

{declared}
"""


def shape(rows: list[dict]) -> list[tuple[str, str, str]]:
    """What must agree between the committed evidence and a fresh run: each test and its verdict (not the figures or the date)."""
    return sorted((r["criterion"], t["test"], t["status"]) for r in rows for t in r["tests"])


def stale_evidence(rows: list[dict], committed: Path = EVIDENCE_DIR / f"{NAME}.json") -> str | None:
    """Why the versioned evidence no longer describes these tests, or None when it does."""
    if not committed.exists():
        return f"{committed.relative_to(ROOT)} does not exist"
    try:
        before = shape(json.loads(committed.read_text(encoding="utf-8"))["criteria"])
    except (ValueError, KeyError, TypeError):
        return f"{committed.relative_to(ROOT)} cannot be read"
    now = shape(rows)
    if before == now:
        return None
    changed = sorted({t for t in set(before) ^ set(now)})
    return f"{committed.relative_to(ROOT)} does not match today's tests ({len(changed)} difference(s), e.g. {changed[0][1]})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", type=Path, help=f"write {NAME}.md and {NAME}.json here (without it nothing is written)")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "junit.xml"
        proc = run_tests(xml_path)
        cases = parse(xml_path)
    rows = summarize(cases)
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    pytest_line = f"pytest: {lines[-1].strip('= ')}." if lines else "pytest gave no output."
    for r in rows:
        print(f"{r['status']}  {r['criterion']}  ({sum(t['status'] == 'PASS' for t in r['tests'])}/{len(r['tests'])})")
    failed = [r for r in rows if r["status"] != "PASS"]
    if proc.returncode != 0 or failed:
        print(proc.stdout[-3000:])
    if args.out_dir:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / f"{NAME}.md").write_text(to_markdown(rows, generated_at, _git_sha(), pytest_line), encoding="utf-8")
        (args.out_dir / f"{NAME}.json").write_text(
            json.dumps({"generated_at": generated_at, "code_version": _git_sha(), "pytest": pytest_line, "criteria": rows},
                       indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"evidence: {args.out_dir / (NAME + '.md')}")
    elif (why := stale_evidence(rows)):
        print(f"warning: {why}; `make evidence` regenerates it")
    return 1 if failed or proc.returncode != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
