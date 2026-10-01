"""The model card is rendered from the reports: the committed one must be what they give today, and must say what it must not be used for."""
from __future__ import annotations

import json
from pathlib import Path

from eval import model_card


def _inputs():
    return [json.loads(p.read_text(encoding="utf-8")) for p in (model_card.REPORT, model_card.STUDY, model_card.META)]


def test_the_committed_card_is_what_the_reports_render_today():
    committed = Path("docs/MODEL_CARD.md").read_text(encoding="utf-8")
    assert committed == model_card.render(*_inputs()), (
        "docs/MODEL_CARD.md is stale: a report it reads changed. Run `python -m eval.model_card` and commit it")


def test_every_headline_figure_in_the_card_is_the_one_in_the_report():
    report, _, _ = _inputs()
    card = model_card.render(*_inputs())
    learned, keywords = report["test"]["learned"], report["test"]["baseline_keywords"]
    assert model_card.pct(learned["accuracy"]) in card and model_card.pct(keywords["accuracy"]) in card
    runtime = report["test"]["escalation_guard"]["lexicon_or_classifier (runtime)"]["recall"]
    assert model_card.pct(runtime) in card


def test_the_card_states_the_limits_that_must_travel_with_the_model():
    card = model_card.render(*_inputs())
    for must_say in ("does not decide outcomes", "detect fraud", "Scored on text the team wrote", "scored once", "No real customer text"):
        assert must_say in card
