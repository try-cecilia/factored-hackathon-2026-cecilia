import pytest

from agent.policy.signals import detect_language


@pytest.mark.parametrize("text", ["No", "no", "NO", "no fui yo", "no, gracias", "no reconozco este cargo"])
def test_a_spanish_no_is_not_read_as_portuguese(text):
    """"no" is also Portuguese ("em + o"), so it carries no signal: a bare "No" leaves the conversation's language alone
    and the rest of the sentence decides."""
    assert detect_language(text).language == "es"
    assert detect_language(text).pt_score == 0


@pytest.mark.parametrize("text", ["não", "nao", "não fui eu", "não reconheço"])
def test_a_portuguese_no_is_portuguese(text):
    assert detect_language(text).language == "pt"


def test_portuguese_that_leaned_on_no_stays_portuguese():
    assert detect_language("quantos dias de atraso tenho no financiamento 7445?").language == "pt"  # held by "quantos"


@pytest.mark.parametrize("text", ["sim, por favor", "me passa meus saldos por favor", "por transferencia a terceros"])
def test_por_stays_spanish_so_these_short_answers_tie(text):
    """"por" is Spanish only: a short Spanish answer like "por transferencia a terceros" must not read as Portuguese for
    its "a". The cost is that "sim, por favor" ties too; a tie keeps the conversation's language (test_orchestrator)."""
    guess = detect_language(text)
    assert guess.pt_score == guess.es_score == 1
