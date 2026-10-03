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


@pytest.mark.parametrize("text", [
    "quantos dias de atraso tenho no financiamento 7445?",  # held by "quantos" now that "no" is neutral
    "sim, por favor", "me passa meus saldos por favor",  # "por" is as much Portuguese as Spanish
])
def test_portuguese_that_shares_words_with_spanish_stays_portuguese(text):
    assert detect_language(text).language == "pt"


def test_a_message_of_shared_words_only_carries_no_signal():
    """No signal at all: the orchestrator keeps the conversation's language."""
    guess = detect_language("no por ahora")
    assert (guess.pt_score, guess.es_score) == (0, 0)
