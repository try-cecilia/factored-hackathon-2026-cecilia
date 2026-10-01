import pytest

from agent.policy.signals import contains_escalation_signal


@pytest.mark.parametrize("text", [
    "Ese cargo no fui yo", "yo no fui, revisen mi cuenta",
    "Essa compra não fui eu", "eu não fui, bloqueiem o cartão",
])
def test_not_me_phrases_escalate(text):
    assert contains_escalation_signal(text)


def test_plain_status_query_does_not_escalate():
    assert not contains_escalation_signal("¿Cuándo llega mi transferencia?")
