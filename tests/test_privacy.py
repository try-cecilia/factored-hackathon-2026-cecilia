"""Privacy by design: what may and may not reach an external model.

The challenge forbids private customer records in external model requests.
Two layers are pinned here:
- `redact` masks what the customer types (card, account, CLABE/CBU and ID
  numbers, emails) before the text leaves for the LLM, keeping the last 4
  digits so "my card ending 1234" still resolves to a product;
- the orchestrator never puts a record in the model's context: no tool
  result, no balance, no internal product id, no rendered answer, no
  customer attribute. The model sees the customer's (masked) words and a
  catalog of aliases, and only ever chooses tools.
"""
from __future__ import annotations

import json
import os

import pytest

from agent.core.orchestrator import Orchestrator
from agent.llm.privacy import redact
from agent.session.auth import SessionStore
from agent.tools.db import get_connection
from eval.fake_llm import FakeLLMClient, tool_call_response

ANA = "CLI-FIX0001"  # fixture customer: Ana Pérez, Premium, México (tests/fixtures/raw)


def _session(orch: Orchestrator, customer: str = ANA) -> str:
    return orch.session_store.issue(customer, {"segment": "Premium", "country": "México", "customer_status": "Active"}).token


def _sent_to_model(fake) -> str:
    return json.dumps([m for call in fake.calls for m in call], ensure_ascii=False, default=str)


def _money_variants(value) -> set[str]:
    v = float(value)
    return {f"{v:,.2f}", f"{v:.2f}", f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")}


def _records_of(customer: str) -> set[str]:
    """Everything the bank holds about the customer that must never reach the
    model, read straight from the warehouse (independent of the code under test)."""
    con = get_connection()
    secret: set[str] = set()
    for pid, number, balance, limit in con.execute(
            "SELECT product_id, product_number, current_balance, credit_limit FROM products WHERE customer_id = ?", [customer]).fetchall():
        secret |= {pid, str(number)}
        for amount in (balance, limit):
            if amount is not None and abs(float(amount)) >= 1:
                secret |= _money_variants(amount)
    for tid, amount, merchant in con.execute(
            "SELECT transaction_id, amount, merchant_name FROM transactions WHERE customer_id = ?", [customer]).fetchall():
        secret |= {tid} | (_money_variants(amount) if abs(float(amount)) >= 1 else set()) | ({merchant} if merchant else set())
    first, last, doc, email, phone, segment = con.execute(
        "SELECT first_name, last_name, document_number, email, mobile_phone, segment FROM customers WHERE customer_id = ?",
        [customer]).fetchone()
    return secret | {first, last, doc, email, phone, segment}


def _leaks(sent: str, secrets: set[str]) -> list[str]:
    import re

    def found(s: str) -> bool:  # words match whole-word ("Ana" must not hit "semana"); ids and figures as substrings
        return bool(re.search(rf"\b{re.escape(s)}\b", sent)) if s.replace(" ", "").isalpha() else s in sent
    return sorted(s for s in secrets if found(s))


def test_the_model_never_receives_a_customer_record_across_a_whole_conversation():
    fake = FakeLLMClient([
        tool_call_response("get_account_summary", {}),
        tool_call_response("list_transactions", {"product_id": "0003"}),
        tool_call_response("get_payment_status", {"product_id": "Préstamo Personal"}),
        tool_call_response("list_transactions", {"product_id": "Cuenta Ahorro"}),
        tool_call_response("list_transactions", {"product_id": "0002"}),
    ])
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: fake)
    tok = _session(orch)
    replies = [orch.handle_message(tok, t) for t in (
        "¿cuánto tengo en mis cuentas?", "mis movimientos de la cuenta corriente 0003", "¿estoy al día con mi préstamo?",
        "movimientos de mi cuenta de ahorros", "la terminada en 0002")]

    assert [r.disposition for r in replies] == ["AUTO_RESOLVE", "AUTO_RESOLVE", "AUTO_RESOLVE", "CLARIFY", "AUTO_RESOLVE"]
    assert "2,455.81" in replies[0].response_text  # the customer still gets the verified figures...
    assert replies[4].verified_facts[0]["args"]["product_id"] == "PRD-FIX0002"
    assert _leaks(_sent_to_model(fake), _records_of(ANA)) == []  # ...the model never does


def test_a_card_number_typed_by_the_customer_reaches_the_model_masked_and_still_resolves():
    fake = FakeLLMClient([tool_call_response("get_payment_status", {"product_id": "0004"})])
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: fake)
    r = orch.handle_message(_session(orch), "¿estoy al día con la tarjeta 5000000004?")
    sent = _sent_to_model(fake)
    assert "5000000004" not in sent and "[···0004]" in sent
    assert r.disposition == "AUTO_RESOLVE" and r.verified_facts[0]["args"]["product_id"] == "PRD-FIX0004"


def test_a_card_number_in_a_fraud_report_is_masked_in_the_ticket():
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: FakeLLMClient([]))
    r = orch.handle_message(_session(orch), "me clonaron la tarjeta 4111 1111 1111 1234")
    ticket = json.loads(open(os.environ["HUMAN_QUEUE_PATH"]).read().splitlines()[-1])
    assert r.disposition == "ESCALATE" and ticket["ticket_id"] == r.ticket_id
    assert "4111" not in ticket["request"] and "[···1234]" in ticket["request"]


def test_one_model_call_per_turn_and_the_models_own_prose_never_reaches_the_customer():
    resp = tool_call_response("get_account_summary", {"product_id": "0001"})
    resp.content = "Tu saldo es 9,999.99 USD y ya bloqueé tu tarjeta."  # a model that also writes an answer
    fake = FakeLLMClient([resp])
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: fake)
    r = orch.handle_message(_session(orch), "saldo de la cuenta 0001")
    assert fake.call_count == 1 and r.llm_calls == 1
    assert "2,455.81" in r.response_text and "9,999.99" not in r.response_text and "bloque" not in r.response_text


class _ReadsTheCatalog:
    """A stand-in model that picks a product the way a real one must: by alias,
    from the catalog it was shown."""

    def __init__(self, product_type: str):
        self.product_type, self.calls, self.call_count = product_type, [], 0

    def chat(self, messages, tools=None, temperature=0.0):
        self.calls.append(list(messages))
        self.call_count += 1
        block = next(m["content"] for m in messages if m["role"] == "system" and '"alias"' in m["content"])
        catalog = json.loads(block[block.index("{"):])
        alias = next(p["alias"] for p in catalog["products"] if p["type"] == self.product_type)
        return tool_call_response("get_payment_status", {"product_id": alias})


def test_the_model_names_products_by_alias_and_the_alias_resolves_to_the_customers_product():
    model = _ReadsTheCatalog("Préstamo Personal")
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: model)
    r = orch.handle_message(_session(orch), "¿estoy al día con mi préstamo?")
    assert r.disposition == "AUTO_RESOLVE" and r.verified_facts[0]["args"]["product_id"] == "PRD-FIX0005"
    assert "5 días de atraso" in r.response_text and "PRD-" not in _sent_to_model(model)


@pytest.mark.parametrize("raw,expected", [
    ("mi tarjeta 4111 1111 1111 1234 no pasa", "mi tarjeta [···1234] no pasa"),
    ("cartão 4111-1111-1111-1234", "cartão [···1234]"),
    ("pan 4111111111111234.", "pan [···1234]."),
    ("CLABE 032180000118359719", "CLABE [···9719]"),
    ("mi CBU es 2850590940090418135201", "mi CBU es [···5201]"),
    ("DNI 30.123.456 por favor", "DNI [···3456] por favor"),
    ("cuenta 4000000001", "cuenta [···0001]"),
    ("escribime a ana.perez@mail.com", "escribime a [email]"),
])
def test_identifiers_the_customer_types_are_masked_keeping_the_last_four(raw, expected):
    assert redact(raw) == expected


@pytest.mark.parametrize("text", [
    "movimientos desde 2026-06-01 hasta 2026-06-17",
    "del 17-06-2026 al 17/06/2026",
    "la terminada en 0002",
    "me cobraron 1.500.000 pesos y 45,90 USD",
    "tengo 2,455.81 en la cuenta a las 10:30",
])
def test_dates_amounts_and_last_four_references_pass_through_unchanged(text):
    assert redact(text) == text
