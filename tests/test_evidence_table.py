"""docs/EVIDENCE.md says what the reports and the code say (eval/evidence_table.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from eval import evidence_table

PER_CASE_REPORTS = pytest.mark.skipif(not Path("eval/reports/system_eval.json").exists(),
                                      reason="per-case reports are not in the public copy")


@PER_CASE_REPORTS
def test_the_evidence_page_matches_the_reports_and_the_code():
    assert evidence_table.check() == []


def test_every_code_link_of_the_page_points_at_the_definition_it_names():
    text = evidence_table.PAGE.read_text(encoding="utf-8")
    problems: list[str] = []
    evidence_table._fix_code_links(text, evidence_table.PAGE, problems)
    assert problems == [] and evidence_table._missing_files(text, evidence_table.PAGE) == []
    assert len(evidence_table.CODE_LINK.findall(text)) > 50


def test_a_link_to_code_that_moved_is_reported_and_rewritten(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "mod.py").write_text("X = 1\n\nclass A:\n    def run(self):\n        pass\n\ndef run():\n    pass\n")
    page = tmp_path / "docs" / "PAGE.md"
    problems: list[str] = []
    fixed = evidence_table._fix_code_links("[`A.run`](../mod.py#L1) [`run`](../mod.py#L7) [`X`](../mod.py#L1) [`gone`](../mod.py#L1)",
                                           page, problems)
    assert fixed.startswith("[`A.run`](../mod.py#L4) [`run`](../mod.py#L7) [`X`](../mod.py#L1)")  # `run`: the module's, not the method
    assert problems == ["A.run: the page says ../mod.py#L1, it is defined at line 4", "gone: not defined in ../mod.py"]
    assert evidence_table._missing_files("[a](../nowhere.md) [b](../mod.py) [c](https://x.y/z)", page) == [
        "link to ../nowhere.md: no such file"]


@PER_CASE_REPORTS
def test_a_report_measured_on_other_code_says_so_in_its_row():
    current = "0" * 64
    rows = evidence_table.table(current=current).splitlines()
    assert rows[0].startswith("Fingerprint of the code in this checkout: `000000000000`")
    data = [r for r in rows if r.startswith("| ") and not r.startswith("| Result")]
    assert data and all("| **no** |" in r or "| n/a |" in r for r in data)


@PER_CASE_REPORTS
def test_a_changed_report_breaks_the_check_until_the_page_is_written_again(tmp_path):
    import json
    import shutil

    reports = tmp_path / "reports"
    shutil.copytree(evidence_table.REPORTS, reports, ignore=shutil.ignore_patterns("*.md"))
    live = json.loads((reports / "system_eval_live.json").read_text(encoding="utf-8"))
    live["policy_sha256"] = "f" * 64
    (reports / "system_eval_live.json").write_text(json.dumps(live), encoding="utf-8")
    problems = evidence_table.check(reports=reports)
    assert len(problems) == 1 and "--write" in problems[0]
    page = tmp_path / "EVIDENCE.md"
    page.write_text(evidence_table.PAGE.read_text(encoding="utf-8"), encoding="utf-8")
    new, problems = evidence_table.render_page(page.read_text(encoding="utf-8"), reports, evidence_table.PAGE)
    assert problems == [] and "`ffffffffffff`" in new
