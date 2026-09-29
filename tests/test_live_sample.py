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
    path.write_text("".join(json.dumps({"part": "reserved" if i % 2 else "generated", "model": live_sample.MODEL, "row": r}, default=str) + "\n"
                            for i, r in enumerate(rows)), encoding="utf-8")
    parts = live_sample.load_rows(path)
    assert len(parts["reserved"]) + len(parts["generated"]) == len(rows) == 20
    md = live_sample.report(parts)
    assert f"reserved set, {len(parts['reserved'])} cases" in md and "Generated test workload" in md and "very wide" in md
    only_reserved = live_sample.report({"reserved": rows, "generated": []})
    assert f"0 of {len(rows)}" in only_reserved  # the scripted ideal model: nothing unsafe


def test_run_without_a_key_runs_nothing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="GROQ_API_KEY"):
        live_sample.run_part("reserved", selection=live_sample.select())
