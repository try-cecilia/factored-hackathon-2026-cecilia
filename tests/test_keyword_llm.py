"""The keyword stand-in for the model (eval/keyword_llm.py) that ops/serve_fixture.py runs. It is shared by every
session of the process, so what it decides can only come from the messages it is handed, never from what an earlier
caller asked."""
from __future__ import annotations

from agent.core.orchestrator import Orchestrator
from agent.session.auth import SessionStore
from eval.keyword_llm import KeywordModel

CUSTOMER = "CLI-FIX0001"  # two savings accounts: ···0001 and ···0002


def make():
    model = KeywordModel()  # one instance, as in the running server
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: model)
    attrs = {"segment": "Premium", "country": "México", "customer_status": "Active"}

    def login() -> str:
        return orch.session_store.issue(CUSTOMER, attrs).token

    return orch, login


def test_a_product_chosen_after_a_clarification_repeats_that_sessions_own_lookup():
    orch, login = make()
    a, b = login(), login()
    assert orch.handle_message(a, "saldo de mi cuenta de ahorros").disposition == "CLARIFY"
    assert orch.handle_message(b, "movimientos de mi cuenta de ahorros").disposition == "CLARIFY"

    balance = orch.handle_message(a, "Cuenta Ahorro ···0002")  # A asked for a balance, not for transactions
    assert balance.disposition == "AUTO_RESOLVE"
    assert "saldo" in balance.response_text and "movimientos" not in balance.response_text

    transactions = orch.handle_message(b, "Cuenta Ahorro ···0002")
    assert transactions.disposition == "AUTO_RESOLVE"
    assert "saldo" not in transactions.response_text and "movimientos" in transactions.response_text


def test_naming_a_product_with_nothing_asked_before_is_not_guessed():
    orch, login = make()
    assert orch.handle_message(login(), "Cuenta Ahorro ···0002").disposition != "AUTO_RESOLVE"
