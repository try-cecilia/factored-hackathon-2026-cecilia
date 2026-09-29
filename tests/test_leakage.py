"""Fuga entre entrenamiento y held-out: la comprobación exacta anterior dejaba pasar una frase idéntica salvo un signo."""
from __future__ import annotations

from agent.llm.intent_classifier import load_rows
from eval import leakage

TRAIN = "eval/test_cases/intent_dataset.csv"
HELDOUT = "eval/test_cases/heldout_utterances.csv"


def test_a_phrase_that_differs_only_in_case_accents_or_punctuation_is_the_same_phrase():
    assert leakage.similarity("Quantos pesos vale um dólar?", "quantos pesos vale um dolar") == 1.0
    assert leakage.similarity("¿Cuál es mi saldo?", "cual es mi saldo") == 1.0


def test_the_old_exact_check_missed_it_and_the_new_one_does_not():
    train, held = "Quantos pesos vale um dólar?", "quantos pesos vale um dólar"
    assert held.strip().lower() != train.strip().lower()          # what the check compared: it let this through
    rep = leakage.report([train, "otra frase sin relación alguna"], [held])
    assert leakage.excluded_utterances(rep) == {held}


def test_a_shorter_form_of_a_template_is_reviewed_not_excluded_and_unrelated_phrases_are_neither():
    train = ["Qual é a cotação do dólar hoje?", "Consultar saldo da conta corrente"]
    rep = leakage.report(train, ["cotação do dólar hoje", "vou processar o banco"])
    assert leakage.excluded_utterances(rep) == set()
    assert leakage.review_utterances(rep) == {"cotação do dólar hoje"}


def test_the_report_summarizes_the_distribution_and_lists_only_what_needs_a_person_to_look():
    rep = leakage.report(["saldo da conta", "tipo de cambio hoy"], ["saldo da conta", "cambio hoy", "algo distinto por completo"])
    assert rep["n"] == 3 and rep["max"] == 1.0 and rep["counts_at_least"]["0.9"] == 1
    assert [p["heldout"] for p in rep["excluded"]] == ["saldo da conta"]
    assert all(p["similarity"] >= leakage.REVIEW_AT for p in rep["excluded"] + rep["review"])


def test_on_the_real_data_the_leaked_phrase_is_found_and_nothing_left_is_identical_to_training():
    train = [r["utterance"] for r in load_rows(TRAIN)]
    held = [r["utterance"] for r in load_rows(HELDOUT)]
    rep = leakage.report(train, held)
    assert "quantos pesos vale um dólar" in leakage.excluded_utterances(rep)
    kept = [h for h in held if h not in leakage.excluded_utterances(rep)]
    assert all(s < leakage.EXCLUDE_AT for s, _ in leakage.nearest(train, kept))
