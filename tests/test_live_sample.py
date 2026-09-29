"""The small live sample is reproducible from versioned artifacts: the selection is a function of the case files, and its
tables are rebuilt from per-case rows (no live model here: rows come from the scripted run on the fixture warehouse)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from eval import heldout, live_sample
from eval import run_system_eval as rse
from eval.workload import load


def test_the_committed_selection_is_what_the_selector_produces():
    committed = json.loads(live_sample.SELECTION.read_text(encoding="utf-8"))
    assert committed == live_sample.select(), "run python -m eval.live_sample select"
    assert len(set(committed["reserved"])) == len(committed["reserved"]) and len(set(committed["generated"])) == len(committed["generated"])


def test_the_selection_takes_two_model_calling_cases_per_category_and_language_and_one_generated_case_per_type():
    selection = live_sample.select()
    reserved = {c.case_id: c for p in (heldout.OUT, heldout.OUT2) for c in load(p)}
    chosen = [reserved[i] for i in selection["reserved"]]
    for category in heldout.CATEGORIES:
        for lang in ("es", "pt"):
            assert sum(c.category == category and c.language == lang for c in chosen) == live_sample.PER_CELL, (category, lang)
    assert all(live_sample._calls_the_model(c) for c in chosen)
    generated = {c.case_id: c for c in load(live_sample.GENERATED_CASES)}
    types = [generated[i].template for i in selection["generated"]]
    assert sorted(types) == sorted({c.template for c in generated.values()})


def test_the_tables_are_rebuilt_from_the_rows_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "fixture.duckdb"))
    heldout.build_warehouse(Path(os.environ["DUCKDB_PATH"]))
    try:
        cases = live_sample.cases_of("reserved", live_sample.select())
        _, rows = rse.run("proposed", "scripted", cases)
    finally:
        from agent.tools import db

        db.close_all()
    path = tmp_path / "rows.jsonl"
    path.write_text("".join(json.dumps({"run_id": "r0", "part": "reserved" if i % 2 else "generated", "model": live_sample.MODEL, "row": r}, default=str) + "\n"
                            for i, r in enumerate(rows)), encoding="utf-8")
    run_id, parts = live_sample.load_rows(path)
    assert run_id == "r0" and len(parts["reserved"]) + len(parts["generated"]) == len(rows) == 20
    md = live_sample.report(parts, run_id)
    assert f"reserved set, {len(parts['reserved'])} cases" in md and "Generated test workload" in md and "very wide" in md
    only_reserved = live_sample.report({"reserved": rows, "generated": []}, "r0")
    assert f"0 of {len(rows)}" in only_reserved  # the scripted ideal model: nothing unsafe


def test_run_without_a_key_runs_nothing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="GROQ_API_KEY"):
        live_sample.run_part("reserved", selection=live_sample.select())


def _entry(run_id, part, case_id, **row):
    return json.dumps({"run_id": run_id, "part": part, "model": live_sample.MODEL, "row": {"case_id": case_id, **row}}) + "\n"


def test_repeating_the_sample_does_not_mix_runs_and_the_report_says_which_one_it_uses(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text(_entry("20260929T100000Z", "reserved", "a") + _entry("20260929T100000Z", "reserved", "b")
                    + _entry("20260930T100000Z", "reserved", "a") + _entry("20260930T100000Z", "generated", "g"), encoding="utf-8")
    run_id, parts = live_sample.load_rows(path)
    assert run_id == "20260930T100000Z" and [r["case_id"] for r in parts["reserved"]] == ["a"] and len(parts["generated"]) == 1  # the latest
    run_id, parts = live_sample.load_rows(path, "20260929T100000Z")
    assert run_id == "20260929T100000Z" and [r["case_id"] for r in parts["reserved"]] == ["a", "b"]
    with pytest.raises(SystemExit, match="20261231"):
        live_sample.load_rows(path, "20261231")


def test_a_case_twice_in_one_run_is_refused(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text(_entry("r1", "reserved", "a") + _entry("r1", "reserved", "a"), encoding="utf-8")
    with pytest.raises(ValueError, match="more than once"):
        live_sample.load_rows(path)
    path.write_text(_entry("r1", "reserved", "a") + _entry("r2", "reserved", "a"), encoding="utf-8")  # the same case in two runs is fine
    live_sample.load_rows(path, "r1")


def test_the_runner_skips_what_its_run_already_has_and_a_row_without_a_run_id_is_refused(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text(_entry("r1", "reserved", "a"), encoding="utf-8")
    assert live_sample.done_in_run(path, "r1", "reserved") == {"a"} and live_sample.done_in_run(path, "r2", "reserved") == set()
    path.write_text(json.dumps({"part": "reserved", "row": {"case_id": "a"}}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="run_id"):
        live_sample.load_rows(path)


def test_the_report_names_its_run(tmp_path):
    md = live_sample.report({"reserved": [], "generated": []}, run_id="20260930T100000Z")
    assert "20260930T100000Z" in md
