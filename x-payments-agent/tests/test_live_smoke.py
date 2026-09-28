"""The live smoke report grades each turn against the outcome written for it; the grader must not flatter."""
from __future__ import annotations

import pytest

from agent.core.orchestrator import TurnResult
from ops.live_smoke import _as_intended

EXPECTED = ("AUTO_RESOLVE", "get_account_summary", "PRD-FIX0002", "150.00")


def turn(disposition="AUTO_RESOLVE", tool="get_account_summary", product="PRD-FIX0002", reply="- Cuenta Ahorro ···0002: saldo 150.00 USD"):
    facts = [{"tool": tool, "args": {"product_id": product}, "result": {}}] if tool else []
    return TurnResult("t", disposition, reply, "es", verified_facts=facts)


def test_the_intended_outcome_passes():
    assert _as_intended(turn(), EXPECTED)


@pytest.mark.parametrize("wrong", [
    turn(disposition="CLARIFY"),
    turn(tool="list_transactions"),
    turn(product="PRD-FIX0001"),  # right question, another of the customer's products
    turn(reply="- Cuenta Ahorro ···0001: saldo 2,455.81 USD"),
])
def test_any_mismatch_fails(wrong):
    assert not _as_intended(wrong, EXPECTED)
