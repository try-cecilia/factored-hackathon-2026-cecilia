"""The experiment on the "no fui yo" pattern (docs/preregistration.md, section 1c) is reproducible and its inputs are what was registered."""
from __future__ import annotations

import csv
import json
import re

import pytest

from agent.policy import signals
from agent.policy.signals import normalize
from eval import not_me_experiment as exp


def rows():
    with exp.SET.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_the_set_is_the_one_that_was_registered_before_the_rule_was_run():
    assert exp.sha256_of(exp.SET) == exp.SET_SHA256
    labels = [r["label"] for r in rows()]
    assert labels.count("disavows") == labels.count("innocent") == 48
    assert {(r["label"], r["language"]) for r in rows()} == {(l, g) for l in ("disavows", "innocent") for g in ("es", "pt")}


def test_every_sentence_has_the_not_me_family_and_no_other_lexicon_cue():
    family = re.compile("|".join(exp.CURRENT))
    other = [re.compile(p) for cat, pats in signals.ESCALATION_PATTERNS.items() for p in pats if p not in exp.CURRENT]
    for r in rows():
        text = normalize(r["utterance"])
        assert family.search(text), r["id"]
        assert not any(p.search(text) for p in other), r["id"]


def test_no_sentence_comes_from_the_training_dev_test_or_trace_sets():
    from eval.evaluate_intent_classifier import HELDOUT, TRACE_HELDOUT, TRAIN

    seen = set()
    for path in (TRAIN, HELDOUT, TRACE_HELDOUT):
        seen |= {normalize(r["utterance"]) for r in csv.DictReader(open(path, encoding="utf-8"))}
    assert not [r["id"] for r in rows() if normalize(r["utterance"]) in seen]


@pytest.mark.parametrize("text, expected", [
    ("Ese cargo no fui yo", True),                                    # stands alone, and names a movement
    ("yo no fui, revisen mi cuenta", True),                           # stands alone
    ("No fui yo", True),
    ("No fui yo quien hizo esa transferencia", True),                 # names a movement
    ("Eu não fui quem sacou esse dinheiro", True),                    # names an act on one
    ("No fui yo al banco ayer, quiero saber mi saldo", False),        # "I did not go to"
    ("Yo no fui al banco, ¿puedo ver mis movimientos?", False),       # names a movement, but it is "I did not go to"
    ("Eu não fui ao banco ontem, qual é meu saldo?", False),
    ("No fui yo quien pidió consultar el saldo; fue mi esposa", False),
    ("¿Cuándo llega mi transferencia?", False),
])
def test_the_candidate_follows_the_registered_rule(text, expected):
    assert exp.fires(text, exp.CANDIDATE) is expected


def test_the_candidate_never_matches_what_the_current_entries_do_not():
    for r in rows():
        assert not (exp.fires(r["utterance"], exp.CANDIDATE) and not exp.fires(r["utterance"], exp.CURRENT)), r["id"]


def test_swapping_the_entries_leaves_the_lexicon_as_it_was():
    before = signals._COMPILED["fraud"]
    with exp.lexicon(exp.CANDIDATE):
        assert signals._COMPILED["fraud"] is not before
    assert signals._COMPILED["fraud"] is before


def test_the_published_report_is_what_the_experiment_gives_today():
    committed = json.loads(exp.OUT_JSON.read_text(encoding="utf-8"))
    assert exp.run() == committed
    assert exp.OUT_MD.read_text(encoding="utf-8") == exp.render(committed)
