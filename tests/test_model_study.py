"""The model study: that it cannot reach the test split, that the shipped model is the one it holds fixed, and its structure."""
from __future__ import annotations

import inspect
import json
import random
from pathlib import Path

import pytest

from agent.llm.intent_classifier import VARIANTS, build_pipeline
from eval import model_study as ms


@pytest.fixture(scope="module")
def data():
    return ms.dev_rows()


def test_the_study_takes_the_training_rows_and_dev_and_nothing_that_could_be_the_test_split():
    assert list(inspect.signature(ms.study).parameters) == ["train_rows", "dev"]
    assert list(inspect.signature(ms.sensitivity).parameters) == ["train_rows", "dev"]
    assert list(inspect.signature(ms.learning_curve).parameters) == ["train_rows", "dev"]


def test_dev_rows_are_disjoint_from_the_test_half_and_from_the_training_text(data):
    from eval.evaluate_intent_classifier import HELDOUT, dev_test_split
    from agent.llm.intent_classifier import load_rows

    train_rows, dev = data
    _, test = dev_test_split(load_rows(HELDOUT))
    assert not {r["utterance"] for r in dev} & {r["utterance"] for r in test}
    assert not {r["utterance"] for r in dev} & {r["utterance"] for r in train_rows}  # the leakage check left the repeats out


def test_the_configuration_the_study_holds_fixed_is_the_one_that_ships():
    shipped = build_pipeline(ms.SHIPPED["variant"]).named_steps["clf"]
    assert shipped.C == ms.SHIPPED["C"] and shipped.class_weight == "balanced"
    report = json.loads(Path("eval/reports/intent_classifier.json").read_text(encoding="utf-8"))
    assert report["chosen_variant"] == ms.SHIPPED["variant"]
    assert (ms.SHIPPED["variant"], ms.SHIPPED["C"]) in {(v, c) for v in VARIANTS for c in ms.C_GRID}


def test_the_grid_has_one_cell_per_configuration_one_of_them_shipped_and_none_equal_to_itself_by_chance(data, monkeypatch):
    monkeypatch.setattr(ms, "RESAMPLES", 30)
    cells = ms.sensitivity(*data)
    assert len(cells) == len(VARIANTS) * len(ms.C_GRID)
    assert [c["shipped"] for c in cells].count(True) == 1
    shipped = next(c for c in cells if c["shipped"])
    assert shipped["vs_shipped"] == 0.0 and shipped["distinguishable_from_shipped"] is False
    for c in cells:
        assert c["vs_shipped_ci95"][0] <= c["vs_shipped_ci95"][1]
        if c["distinguishable_from_shipped"]:
            assert c["vs_shipped_ci95"][0] > 0 or c["vs_shipped_ci95"][1] < 0


def test_a_subsample_keeps_every_class_and_the_full_share_keeps_every_row(data):
    train_rows, _ = data
    classes = {r["intent"] for r in train_rows}
    small = ms._subsample(train_rows, 0.1, random.Random(0))
    assert {r["intent"] for r in small} == classes and len(small) < len(train_rows)
    assert len(ms._subsample(train_rows, 1.0, random.Random(0))) == len(train_rows)


def test_the_learning_curve_covers_every_share_and_is_repeatable(data):
    first, second = ms.learning_curve(*data), ms.learning_curve(*data)
    assert first == second
    assert [r["fraction"] for r in first] == list(ms.FRACTIONS) and first[-1]["runs"] == 1 and first[0]["runs"] == ms.SUBSAMPLES
    assert all(r["dev_macro_f1_min"] <= r["dev_macro_f1_mean"] <= r["dev_macro_f1_max"] for r in first)
