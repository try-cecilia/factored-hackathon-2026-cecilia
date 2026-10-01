"""La conversación real de un cliente de la demo: pidió dos cosas en un mensaje (lo pendiente y sus últimas 5 transferencias),
la asistente contestó una sola (y la equivocada), repitió esa respuesta tres veces y al final listó cualquier movimiento.

El modelo es el guionado de los tests: lo que se prueba es lo que hace el código con lo que el modelo decide (las
herramientas, las plantillas, el cierre de un turno que repite al anterior) y que el modo degradado no empeora nada.
Nada aquí detecta una intención con palabras clave: la intención sale de lo que el modelo guionado devuelve.
"""
from __future__ import annotations

import shutil

import pytest

from agent.core.orchestrator import Orchestrator
from agent.session.auth import SessionStore
from agent.tools import account_tools as tools
from agent.tools import db
from eval.fake_llm import FakeLLMClient, tool_call_response, unavailable
from tests.conftest import FIXTURES, build_fixture_warehouse

# Un cliente más, con lo que esa conversación necesita: una tarjeta con 90 días de atraso, siete transferencias aprobadas,
# una transferencia y un pago pendientes, una compra y un depósito. Todo del 2024-01-16 (el día del warehouse de prueba).
CUSTOMER = ("CLI-FIX0007,DNI90000007,DNI,Lucía,Rojas,1990-02-02,F,lucia@fixture.test,+525544444444,,Calle Fixture 7,Monterrey,"
            "Nuevo León,México,64000,mexican,Basic,690,20000.00,Diseñadora,Soltera,Universitario,2019-06-01 10:00:00,SUC-FIX01,Active,"
            "2026-06-01 00:00:00,false")
PRODUCTS = ("PRD-FIX0015,CLI-FIX0007,Cuenta Corriente,4000000015,USD,5000.00,,,2019-06-01,,SUC-FIX01,Active,App,true,,"
            "2024-01-16 12:00:00,2026-06-01 00:00:00",
            "PRD-FIX0016,CLI-FIX0007,Tarjeta Crédito,5000000016,USD,1395.70,19300.61,30.00,2019-06-01,2028-06-30,SUC-FIX01,Active,App,"
            "true,90,2024-01-16 12:00:00,2026-06-01 00:00:00")


def _txn(n: int, hour: int, kind: str, amount: str, status: str, product: str, merchant: str = "") -> str:
    return (f"TXN-FIX{n:04d},2024-01-16 {hour:02d}:00:00,2024-01-16,{product},CLI-FIX0007,{kind},,{amount},USD,{amount},App,,"
            f"{merchant},,México,Monterrey,{status},00,false,3.00,,")


MOVEMENTS = (
    *(_txn(100 + i, 1 + i, "Transfer", f"{100 + i}.00", "Approved", "PRD-FIX0015") for i in range(7)),  # 01:00 a 07:00
    _txn(110, 9, "Deposit", "900.00", "Approved", "PRD-FIX0015"),
    _txn(111, 11, "Purchase", "378.89", "Approved", "PRD-FIX0016", "Conciertos Live"),
    _txn(112, 13, "Payment", "250.00", "Pending", "PRD-FIX0016"),
    _txn(113, 15, "Transfer", "640.00", "Pending", "PRD-FIX0015"),
)


def _append(path, *lines):
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture(scope="module", autouse=True)
def warehouse(tmp_path_factory):
    raw = tmp_path_factory.mktemp("compuestos") / "raw"
    shutil.copytree(FIXTURES / "raw", raw)
    _append(raw / "customers.csv", CUSTOMER)
    _append(raw / "products.csv", *PRODUCTS)
    _append(next((raw / "transactions").glob("year=2024/month=01/day=16/*.csv")), *MOVEMENTS)
    mp = pytest.MonkeyPatch()
    mp.setenv("DUCKDB_PATH", str(raw.parent / "warehouse.duckdb"))
    build_fixture_warehouse(raw_dir=raw)
    db.close_all()
    yield
    db.close_all()
    mp.undo()


def session(script, customer="CLI-FIX0007"):
    fake = FakeLLMClient(script)
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: fake)
    return orch, orch.session_store.issue(customer, {"segment": "Basic", "country": "México", "customer_status": "Active"}).token, fake


PENDING = ("list_transactions", {"status": "Pending"})
TRANSFERS_5 = ("list_transactions", {"transaction_type": "Transfer", "limit": 5})
CARD = ("get_payment_status", {"product_id": "Tarjeta Crédito"})
ASK = "dame mis pagos pendientes y mis ultimas 5 transferencias"


def section(text: str, head: str) -> str:
    """El tramo de la respuesta que cuelga de un encabezado, hasta el siguiente encabezado o el final."""
    start = text.index(head)
    rest = text[start + len(head):]
    ends = [rest.index(h) for h in ("\nMovimientos", "\nTransferencias", "\nInformación al") if h in rest]
    return rest[:min(ends)] if ends else rest


# --- 1. el pedido compuesto: las dos lecturas en un turno --------------------------------------------------------------

def test_a_request_for_two_reads_is_answered_with_both_each_under_its_own_heading():
    orch, tok, fake = session([tool_call_response(*PENDING, TRANSFERS_5)])
    r = orch.handle_message(tok, ASK)
    assert r.disposition == "AUTO_RESOLVE" and r.llm_calls == 1 and fake.call_count == 1
    assert [f["tool"] for f in r.verified_facts] == ["list_transactions", "list_transactions"]
    pending, transfers = section(r.response_text, "Movimientos pendientes"), section(r.response_text, "Transferencias (5 más recientes)")
    assert "250.00 USD" in pending and "640.00 USD" in pending and "Tarjeta Crédito" not in r.response_text
    assert "Conciertos Live" not in transfers and "378.89" not in transfers and "Deposit" not in transfers


def test_the_two_reads_are_answered_in_portuguese_too():
    orch, tok, _ = session([tool_call_response(*PENDING, TRANSFERS_5)])
    r = orch.handle_message(tok, "me mostre minhas movimentações pendentes e as últimas 5 transferências")
    assert r.language == "pt" and "Movimentações pendentes" in r.response_text
    assert "Transferências (5 mais recentes)" in r.response_text and "Informação de 16/01/2024" in r.response_text


# --- 3. el filtro y la cantidad ----------------------------------------------------------------------------------------

def test_the_tool_filters_by_type_and_keeps_the_quantity_the_customer_asked_for():
    got = tools.list_transactions("CLI-FIX0007", transaction_type="Transfer", limit=5)["items"]
    assert len(got) == 5 and {t["transaction_type"] for t in got} == {"Transfer"}
    assert [t["transaction_date"] for t in got] == sorted((t["transaction_date"] for t in got), reverse=True)
    assert len(tools.list_transactions("CLI-FIX0007", transaction_type="Transfer", status="Approved")["items"]) == 7
    assert tools.list_transactions("CLI-FIX0007", transaction_type="Transfer", limit=10_000)["limit"] == tools.MAX_TRANSACTIONS


def test_last_5_transfers_are_only_transfers_and_exactly_5():
    orch, tok, _ = session([tool_call_response("list_transactions", {"transaction_type": "Transfer", "limit": 5})])
    r = orch.handle_message(tok, "transferencias, ultimas 5")
    body = r.response_text
    assert body.startswith("Transferencias (5 más recientes):") and body.count("\n- ") == 5
    assert "Conciertos Live" not in body and "900.00" not in body and "250.00" not in body  # ni la compra, ni el depósito, ni el pago


def test_fewer_transfers_than_asked_says_how_many_there_are():
    orch, tok, _ = session([tool_call_response("list_transactions", {"transaction_type": "Transfer", "limit": 30})])
    assert orch.handle_message(tok, "mis transferencias").response_text.startswith("Transferencias (8 más recientes):")
    orch, tok, _ = session([tool_call_response("list_transactions", {"transaction_type": "Transfer"})], customer="CLI-FIX0001")
    assert "No encontré movimientos" in orch.handle_message(tok, "mis transferencias").response_text


def test_a_type_that_is_not_one_is_a_question_not_a_guess():
    orch, tok, _ = session([tool_call_response("list_transactions", {"transaction_type": "Cheque"})])
    assert orch.handle_message(tok, "mis cheques").disposition == "CLARIFY"


def test_the_model_is_told_it_can_filter_by_type_and_status():
    from agent.llm import prompts

    schema = next(t["function"]["parameters"]["properties"] for t in prompts.TOOL_SCHEMAS if t["function"]["name"] == "list_transactions")
    assert schema["transaction_type"]["enum"] == ["Deposit", "Withdrawal", "Transfer", "Payment", "Purchase", "Adjustment"]
    assert "transaction_type" in prompts.SYSTEM_PROMPT and "status" in prompts.SYSTEM_PROMPT


# --- 2. el seguimiento: usar el contexto, o decir qué faltó --------------------------------------------------------------

def test_the_history_the_model_gets_says_which_reads_were_answered_and_with_what_filters():
    orch, tok, fake = session([tool_call_response(*CARD), tool_call_response(*PENDING, TRANSFERS_5)])
    first = orch.handle_message(tok, ASK)
    assert "Tarjeta Crédito" in first.response_text and "90 días de atraso" in first.response_text  # lo que contestó el modelo del caso
    orch.handle_message(tok, "te pedi dos cosas")
    history = fake.calls[1][2:-1]
    assert history[0]["content"] == ASK and history[1]["role"] == "assistant"
    assert "get_payment_status(P2)" in history[1]["content"] and "1,395" not in history[1]["content"]


def test_the_conversation_of_the_report_completes_what_was_missing_with_the_context():
    """Cliente: 'dame mis pagos pendientes y mis ultimas 5 transferencias'. El modelo contesta solo la tarjeta. Al reclamar,
    el modelo (que ve en el historial qué se contestó) pide las dos lecturas que faltaron; nada se repite."""
    orch, tok, _ = session([tool_call_response(*CARD), tool_call_response(*PENDING, TRANSFERS_5),
                            tool_call_response("list_transactions", {"transaction_type": "Transfer", "limit": 5})])
    first = orch.handle_message(tok, ASK)
    second = orch.handle_message(tok, "te pedi dos cosas")
    assert second.disposition == "AUTO_RESOLVE" and second.response_text != first.response_text
    assert "Movimientos pendientes" in second.response_text and "Transferencias (5 más recientes)" in second.response_text
    third = orch.handle_message(tok, "transferencias, ultimas 5")
    assert third.response_text.startswith("Transferencias (5 más recientes):") and third.response_text != second.response_text


@pytest.mark.parametrize("complaint", ["te pedi dos cosas", "y las ultimas 5 ?"])
def test_a_model_that_repeats_the_same_read_gets_no_identical_reply(complaint):
    orch, tok, _ = session([tool_call_response(*CARD), tool_call_response(*CARD), tool_call_response(*CARD)])
    first = orch.handle_message(tok, ASK)
    second = orch.handle_message(tok, complaint)
    assert second.response_text != first.response_text
    assert "90 días" not in second.response_text and "1,395.70" not in second.response_text  # no vuelve a pegar la cifra
    assert "ya te la respondí" in second.response_text and "transferencias" in second.response_text  # dice qué más puede pedir
    assert second.disposition == "CLARIFY" and second.policy_rule == "repeat_guard" and second.category == "repeated_request"
    assert [f["tool"] for f in second.verified_facts] == ["get_payment_status"]  # lo leído sigue verificado
    third = orch.handle_message(tok, complaint)  # insiste: ahora sí se muestra otra vez, nunca dos respuestas iguales seguidas
    assert third.response_text == first.response_text != second.response_text


def test_the_repeat_template_is_in_the_customers_language():
    orch, tok, _ = session([tool_call_response(*CARD), tool_call_response(*CARD)])
    orch.handle_message(tok, "meu cartão está em dia?")
    r = orch.handle_message(tok, "eu pedi duas coisas")
    assert r.language == "pt" and "já respondi" in r.response_text and "transferências" in r.response_text


def test_the_same_question_again_after_something_else_is_answered_again():
    orch, tok, _ = session([tool_call_response("get_account_summary", {}), tool_call_response("get_exchange_rate",
                            {"source_currency": "USD", "target_currency": "MXN"}), tool_call_response("get_account_summary", {})])
    first = orch.handle_message(tok, "mis saldos")
    orch.handle_message(tok, "el dólar")
    again = orch.handle_message(tok, "mis saldos")
    assert again.response_text == first.response_text and again.policy_rule == "verified_tool_results"


def test_what_the_repeat_check_keeps_is_a_digest_not_the_customers_figures():
    import re

    orch, tok, _ = session([tool_call_response(*CARD)])
    orch.handle_message(tok, ASK)
    conv = orch.conversations.get(orch.session_store.validate(tok).ref)
    assert re.fullmatch(r"[0-9a-f]{16}", conv.last_answer)  # what the check keeps of the reply: a digest, never its text


def test_more_reads_than_a_turn_takes_are_not_dropped_in_silence():
    orch, tok, _ = session([tool_call_response(*PENDING, TRANSFERS_5, CARD,
                                               ("get_exchange_rate", {"source_currency": "USD", "target_currency": "MXN"}))])
    r = orch.handle_message(tok, "pendientes, transferencias, estado de mi tarjeta y el dólar")
    assert r.disposition == "AUTO_RESOLVE" and len(r.verified_facts) == 2
    assert "Quedó sin atender: estado de pago, tipo de cambio" in r.response_text and "otro mensaje" in r.response_text


def test_the_model_sees_what_was_left_unattended_so_it_can_finish_next_turn():
    orch, tok, fake = session([tool_call_response(*PENDING, TRANSFERS_5, CARD), tool_call_response(*CARD)])
    orch.handle_message(tok, ASK + " y mi tarjeta")
    r = orch.handle_message(tok, "y mi tarjeta?")
    assert "get_payment_status" in fake.calls[1][2:-1][1]["content"] and "sin atender" in fake.calls[1][2:-1][1]["content"]
    assert "90 días de atraso" in r.response_text


def test_a_clarification_for_one_read_does_not_throw_away_the_other_that_was_answered():
    orch, tok, _ = session([tool_call_response("get_account_summary", {}, ("list_transactions", {"product_id": "Cuenta Ahorro"}))],
                           customer="CLI-FIX0001")
    r = orch.handle_message(tok, "mis saldos y los movimientos de mi cuenta de ahorros")
    assert r.disposition == "CLARIFY" and "2,455.81" in r.response_text and "¿Sobre cuál de tus productos?" in r.response_text


def test_a_request_trace_takes_the_turn_and_says_what_it_left_aside():
    orch, tok, _ = session([tool_call_response("request_trace", {"amount": 640}, TRANSFERS_5)])
    r = orch.handle_message(tok, "mi transferencia de 640 no llegó y mis últimas 5 transferencias")
    assert "pedido de rastreo" in r.response_text and "Quedó sin atender: transferencias" in r.response_text


# --- el modo degradado: sin modelo, el clasificador no se inventa una lectura ----------------------------------------------

def test_without_the_model_the_conversation_of_the_report_is_handed_over_never_answered_with_the_card():
    orch, tok, _ = session([unavailable(), unavailable(), unavailable(), unavailable()])
    for text in (ASK, "te pedi dos cosas", "y las ultimas 5 ?", "transferencias, ultimas 5"):
        r = orch.handle_message(tok, text)
        assert r.disposition == "ESCALATE" and r.category == "llm_unavailable" and "90 días" not in r.response_text


def test_without_the_model_the_same_balance_question_twice_is_not_answered_twice_identically():
    orch, tok, _ = session([unavailable(), unavailable()])
    first, second = orch.handle_message(tok, "¿Cuál es mi saldo?"), orch.handle_message(tok, "¿Cuál es mi saldo?")
    assert first.policy_rule == "degraded:deterministic_balance" and first.degraded
    assert second.response_text != first.response_text and second.policy_rule == "degraded:repeat_guard" and second.degraded
