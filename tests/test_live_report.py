"""Every aggregate the committed live report publishes comes from the per-case rows it keeps, run by run."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval import run_system_eval as rse

LIVE = json.loads(Path("eval/reports/system_eval_live.json").read_text(encoding="utf-8"))
SYSTEMS = list(LIVE["systems"])


def _as_saved(value):
    """What the JSON report holds for a value computed now (tuples become lists)."""
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def _runs(name: str) -> list[tuple[dict, list[dict]]]:
    rows = LIVE["cases"][name]
    return [(_as_saved(rse.metrics(rse.rows_of_repeat(rows, r["repeat"]))), rse.rows_of_repeat(rows, r["repeat"]))
            for r in LIVE["systems"][name]["repeats"]]


@pytest.mark.parametrize("name", SYSTEMS)
def test_each_runs_published_figures_are_computed_from_its_rows(name):
    for (m, rows), published in zip(_runs(name), LIVE["systems"][name]["repeats"]):
        assert len(rows) == LIVE["n_cases"]
        assert {k: m[k] for k in rse.REPEAT_SUMMARY if k != "served_by"} == {k: published[k] for k in rse.REPEAT_SUMMARY if k != "served_by"}
        assert dict(rse.Counter(r["model"] for r in rows if r["model"])) == published["served_by"]


@pytest.mark.parametrize("name", SYSTEMS)
def test_the_headline_table_is_run_1_and_the_spread_is_every_run(name):
    system, runs = LIVE["systems"][name], _runs(name)
    m, rows = runs[0]
    headline = {k: v for k, v in system.items() if k not in ("repeats", "repeat_variability", "by_template", "by_category",
                                                               "by_language", "by_segment", "by_country", "served_by", "error_analysis")}
    assert headline == m
    for key in ("template", "category", "language", "segment", "country"):
        assert system[f"by_{key}"] == _as_saved(rse.breakdown(rows, key))
    assert system["error_analysis"] == _as_saved(rse.error_analysis(rows))
    assert system["repeat_variability"] == _as_saved(rse.variability(runs))


def test_every_run_was_measured_on_the_code_the_report_names():
    for system in LIVE["systems"].values():
        assert {r["policy_sha256"] for r in system["repeats"]} == {LIVE["policy_sha256"]}
        assert {r["code_sha"] for r in system["repeats"]} == {LIVE["code_sha"]} and LIVE["code_dirty"] is False
