"""The keyword stand-in for the model (eval/keyword_llm.py) that ops/serve_fixture.py runs. It is shared by every
session of the process, so what it decides can only come from the messages it is handed, never from what an earlier
caller asked."""
from __future__ import annotations

import pytest

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


def test_a_movement_that_never_arrived_asks_for_the_trace():
    from eval.keyword_llm import _lookup

    for text in ("hice una transferencia y nunca llegó", "nunca le llegó el depósito", "nunca llego mi pago",
                 "el pago no llegó", "no le llego la plata", "la transferencia que hice no aparece",
                 "fiz uma transferência e nunca chegou", "o depósito não chegou", "minha transferência não caiu"):
        assert _lookup(text.lower())[0] == "request_trace", text
    for text in ("cuál es mi saldo", "movimientos de mi cuenta de ahorros", "qual é o meu saldo"):
        assert _lookup(text)[0] != "request_trace", text


def test_a_transfer_that_never_arrived_reaches_the_trace_and_says_why_it_goes_to_a_person():
    from agent.core import render

    orch, login = make()
    r = orch.handle_message(login(), "hice una transferencia y nunca llegó")  # CLI-FIX0001 has nothing pending
    assert (r.policy_rule, r.response_text) == ("action:trace_unmatched", render.MSG["trace_unmatched"]["es"])


def test_a_kind_of_movement_named_alone_lists_that_kind_and_a_negation_still_asks_for_the_trace():
    from eval.keyword_llm import _lookup

    for text, kind in (("transferencias", "Transfer"), ("mis transferencias", "Transfer"), ("Transferências", "Transfer"),
                       ("minhas transferências", "Transfer"), ("pagos", "Payment"), ("mis pagos", "Payment"), ("pagamentos", "Payment"),
                       ("depósitos", "Deposit"), ("meus depósitos", "Deposit"), ("depositos", "Deposit")):
        assert _lookup(text.lower()) == ("list_transactions", {"transaction_type": kind}), text
    for text in ("hice una transferencia y no llegó", "hice una transferencia y nunca llegó", "mis transferencias no aparecen",
                 "fiz uma transferência e não chegou", "minhas transferências não caíram", "el depósito no aparece", "o pagamento não caiu"):
        assert _lookup(text.lower())[0] == "request_trace", text
    assert _lookup("mis pagos están al día")[0] == "get_payment_status"  # late payments are the status, not the list


@pytest.mark.parametrize("text,lang", [("transferencias", "es"), ("mis transferencias", "es"), ("minhas transferências", "pt")])
def test_transfers_alone_answers_with_the_transfers_list(text, lang):
    orch, login = make()
    r = orch.handle_message(login(), text)
    assert (r.disposition, r.language) == ("AUTO_RESOLVE", lang), r.response_text
    [fact] = r.verified_facts
    assert fact["tool"] == "list_transactions" and fact["args"]["transaction_type"] == "Transfer"


STATUS = ["mis pagos no están al día", "mis pagos no están atrasados", "estado de pago", "estado de pagos",
          "meus pagamentos não estão em dia", "meus pagamentos não estão atrasados", "estado do pagamento", "situação dos pagamentos"]


@pytest.mark.parametrize("text", STATUS)
def test_a_payment_status_said_with_a_negation_or_as_a_status_is_the_status_not_a_trace(text):
    from eval.keyword_llm import _lookup

    assert _lookup(text)[0] == "get_payment_status", text
    orch, login = make()
    r = orch.handle_message(login(), text)
    assert r.policy_rule != "action:trace_unmatched" and r.ticket_id is None, (r.policy_rule, r.response_text)
    assert [f["tool"] for f in r.verified_facts] == ["get_payment_status"], (r.policy_rule, r.response_text)


def test_a_payment_or_deposit_that_did_not_arrive_still_asks_for_the_trace():
    from eval.keyword_llm import _lookup

    for text in ("el pago no se acreditó", "mi depósito no aparece", "el pago no me llegó", "el depósito no entró",
                 "o pagamento não caiu", "meu depósito não apareceu", "o pagamento não chegou"):
        assert _lookup(text)[0] == "request_trace", text


@pytest.mark.parametrize("text", ["no aparece mi pago del mes", "no se acreditó mi pago", "não apareceu meu pagamento"])
def test_a_missing_payment_said_verb_first_asks_for_the_trace(text):
    from eval.keyword_llm import _lookup

    assert _lookup(text)[0] == "request_trace", text
    orch, login = make()
    r = orch.handle_message(login(), text)
    assert [c["tool"] for c in r.tool_calls] == ["request_trace"], (r.policy_rule, r.response_text)


def test_a_payment_that_did_arrive_is_not_a_trace():
    from eval.keyword_llm import _lookup

    for text in ("el pago entró", "mis pagos entraron tarde", "o pagamento caiu", "llegó mi pago", "apareció el depósito"):
        assert _lookup(text)[0] != "request_trace", text
