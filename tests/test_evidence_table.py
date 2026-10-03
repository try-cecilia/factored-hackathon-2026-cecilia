"""docs/EVIDENCE.md says what the reports and the code say (eval/evidence_table.py)."""
from __future__ import annotations

import fnmatch
import json
import shutil
from pathlib import Path

import pytest

from eval import evidence_table
from ops.export_public import REMOVE_GLOBS

PER_CASE_REPORTS = pytest.mark.skipif(not Path("eval/reports/system_eval.json").exists(),
                                      reason="per-case reports are not in the public copy")


def _page_text() -> str:
    return evidence_table.PAGE.read_text(encoding="utf-8")


@PER_CASE_REPORTS
def test_the_evidence_page_matches_the_reports_and_the_code():
    assert evidence_table.check() == []


def test_every_code_link_of_the_page_points_at_the_definition_it_names():
    problems: list[str] = []
    evidence_table._fix_code_links(_page_text(), evidence_table.PAGE, problems)
    assert problems == [] and len(evidence_table.CODE_LINK.findall(_page_text())) > 50


def test_every_other_link_of_the_page_points_at_a_file_or_at_a_report_the_public_export_removes():
    assert evidence_table._missing_files(_page_text(), evidence_table.PAGE) == []


def test_in_the_public_copy_only_the_reports_the_export_removes_are_missing_and_the_links_still_pass(tmp_path):
    """The page and every file it links, copied the way ops/export_public.py leaves them (REMOVE_GLOBS applied)."""
    root = evidence_table.ROOT
    removed = []
    for rel in {*evidence_table.FILE_LINK.findall(_page_text()), *(m[1] for m in evidence_table.CODE_LINK.findall(_page_text()))}:
        if "://" in rel:
            continue
        source = (evidence_table.PAGE.parent / rel).resolve()
        target = tmp_path / source.relative_to(root)
        if any(fnmatch.fnmatch(source.relative_to(root).as_posix(), g) for g in REMOVE_GLOBS):
            removed.append(source.name)  # by its name: in the public copy itself it is already gone
        elif not source.exists():
            continue  # the other link test reports it
        elif source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target)
    page = tmp_path / "docs" / "EVIDENCE.md"
    page.write_text(_page_text(), encoding="utf-8")
    assert {"system_eval.json", "system_eval_adversarial.json", "system_eval_live.json"} <= set(removed)
    problems: list[str] = []
    evidence_table._fix_code_links(_page_text(), page, problems)
    assert problems == [] and evidence_table._missing_files(_page_text(), page, tmp_path) == []
    (tmp_path / "LIMITATIONS.md").unlink()  # a file the export keeps is still required
    assert evidence_table._missing_files(_page_text(), page, tmp_path) == ["link to ../LIMITATIONS.md: no such file"]


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


def test_a_method_is_looked_for_only_in_the_class_the_link_names(tmp_path):
    mod = tmp_path / "scope.py"
    mod.write_text("class A:\n    pass\n\nclass B:\n    def run(self):\n        pass\n\n    LIMIT = 2\n\ndef helper():\n    run = 1\n")
    assert evidence_table.definition_line(mod, "B.run") == 5 and evidence_table.definition_line(mod, "B.LIMIT") == 8
    assert evidence_table.definition_line(mod, "A.run") is None  # B.run is not A.run
    assert evidence_table.definition_line(mod, "run") is None  # a method or a local is not a module-level definition
    assert evidence_table.definition_line(mod, "helper.run") is None  # nor inside a function
    assert evidence_table.definition_line(mod, "scope.helper") == 10  # the module's own name is only a label


def _page_copy(tmp_path: Path, text: str) -> Path:
    """A page in a tree that sees the repository's files, so its relative links resolve as the real page's do."""
    root = evidence_table.ROOT
    for entry in root.iterdir():
        if entry.name not in ("docs", ".git"):
            (tmp_path / entry.name).symlink_to(entry)
    (tmp_path / "docs").mkdir()
    for entry in (root / "docs").iterdir():
        if entry.name != "EVIDENCE.md":
            (tmp_path / "docs" / entry.name).symlink_to(entry)
    page = tmp_path / "docs" / "EVIDENCE.md"
    page.write_text(text, encoding="utf-8")
    return page


@PER_CASE_REPORTS
def test_write_exits_0_after_fixing_moved_lines_and_1_only_for_what_it_cannot_fix(tmp_path, monkeypatch, capsys):
    text = _page_text()
    moved = text.replace("[`chat`](../api/main.py#L", "[`chat`](../api/main.py#L1")  # every link to `chat`, one line off
    assert moved != text
    page = _page_copy(tmp_path, moved)
    monkeypatch.setattr(evidence_table, "PAGE", page)
    assert evidence_table.main(["--check"]) == 1
    assert evidence_table.main(["--write"]) == 0 and page.read_text(encoding="utf-8") == text
    assert evidence_table.main(["--check"]) == 0

    page.write_text(text.replace("[`chat`](../api/main.py#L", "[`no_such_chat`](../api/main.py#L"), encoding="utf-8")
    assert evidence_table.main(["--write"]) == 1 and "no_such_chat: not defined" in capsys.readouterr().out


@PER_CASE_REPORTS
def test_a_report_measured_on_other_code_says_so_in_its_row():
    rows = evidence_table.table(current="0" * 64).splitlines()
    assert rows[0].startswith("Fingerprint of the code in this checkout: `000000000000`")
    data = [r for r in rows if r.startswith("| ") and not r.startswith("| Result")]
    assert data and all("| **no** |" in r or "| n/a |" in r for r in data)


@PER_CASE_REPORTS
def test_a_changed_report_breaks_the_check_until_the_page_is_written_again(tmp_path):
    reports = tmp_path / "reports"
    shutil.copytree(evidence_table.REPORTS, reports, ignore=shutil.ignore_patterns("*.md"))
    live = json.loads((reports / "system_eval_live.json").read_text(encoding="utf-8"))
    live["policy_sha256"] = "f" * 64
    (reports / "system_eval_live.json").write_text(json.dumps(live), encoding="utf-8")
    problems = evidence_table.check(reports=reports)
    assert len(problems) == 1 and "--write" in problems[0]
    new, problems = evidence_table.render_page(_page_text(), reports, evidence_table.PAGE)
    assert problems == [] and "`ffffffffffff`" in new


def _live_caveats(reports: Path) -> dict[str, str]:
    return {r["result"]: r["caveat"] for r in evidence_table._live_rows(reports)}


@PER_CASE_REPORTS
def test_each_live_caveat_names_the_unsafe_outcomes_and_the_runs_the_report_keeps():
    """What a live row says about its runs is read from system_eval_live.json, so it cannot outlive the report."""
    live = json.loads((evidence_table.REPORTS / "system_eval_live.json").read_text(encoding="utf-8"))
    caveats = _live_caveats(evidence_table.REPORTS)
    assert len(caveats) == len(live["systems"])
    for name, system in live["systems"].items():
        (caveat,) = [c for result, c in caveats.items() if result.endswith(next(iter(system["served_by"])).split("/")[-1])]
        runs = [r["repeat"] for r in system["repeats"]]
        rows = live["cases"][name]
        assert sorted({r["repeat"] for r in rows}) == runs and f"keeps the per-case rows of all {len(runs)} runs" in caveat
        assert "Only run" not in caveat
        unsafe = [r for r in rows if r["unsafe"]]
        assert caveat.count("case `") == len(unsafe)
        for r in unsafe:
            assert f"run {r['repeat']}, case `{r['case_id']}`" in caveat and all(f"`{t}`" in caveat for t in r["unsafe"])
        for run in system["repeats"]:  # the per-run counts and the rows agree on what is cited
            assert sum(run["unsafe_by_type"].values()) == sum(len(r["unsafe"]) for r in unsafe if r["repeat"] == run["repeat"])
        assert ("No unsafe outcome in any run." in caveat) == (not unsafe)


@PER_CASE_REPORTS
def test_a_live_caveat_follows_the_report_when_its_rows_or_its_findings_change(tmp_path):
    reports = tmp_path / "reports"
    shutil.copytree(evidence_table.REPORTS, reports, ignore=shutil.ignore_patterns("*.md"))
    path = reports / "system_eval_live.json"
    live = json.loads(path.read_text(encoding="utf-8"))
    name = next(iter(live["systems"]))
    first = next(r for r in live["cases"][name] if r["repeat"] == 1)
    first["unsafe"] = ["text_outside_the_templates"]
    live["systems"][name]["repeats"][1]["unsafe_by_type"] = {"hallucinated_number_shown": 2}
    live["cases"][name] = [r for r in live["cases"][name] if r["repeat"] == 1]  # only run 1 keeps its rows
    path.write_text(json.dumps(live), encoding="utf-8")
    caveat = _live_caveats(reports)[f"Live, {next(iter(live['systems'][name]['served_by'])).split('/')[-1]}"]
    assert "Only run 1 keeps per-case rows" in caveat and "all 3 runs" not in caveat
    assert f"run 1, case `{first['case_id']}` ({first['template']}, {first['language']}), `text_outside_the_templates`" in caveat
    assert "run 2, 2 × `hallucinated_number_shown`" in caveat and "No unsafe outcome" not in caveat
    assert any("--write" in p for p in evidence_table.check(reports=reports))
