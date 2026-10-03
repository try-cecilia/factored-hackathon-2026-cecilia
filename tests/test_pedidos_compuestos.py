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


# --- revisión: lo que no se podía perder ni filtrar ----------------------------------------------------------------------

MARKER = "MARCADOR-SINTETICO-7f3a91"


def _files(*names):
    import os

    return {n: open(os.environ[n], encoding="utf-8").read() if os.path.exists(os.environ[n]) else "" for n in names}


def test_a_failure_inside_the_audited_tool_leaves_no_message_in_the_audit_the_trace_or_the_ticket(monkeypatch):
    """El fallo ocurre DENTRO de list_transactions (la consulta al warehouse), no sustituyendo la herramienta: lo que se
    guarda es el tipo de la excepción, nunca su mensaje."""
    real = tools._rows

    def rows(sql, params):
        if "FROM transactions WHERE" in sql:
            raise RuntimeError(f'Cannot open "{MARKER}" for PRD-FIX0015')
        return real(sql, params)

    monkeypatch.setattr(tools, "_rows", rows)
    orch, tok, _ = session([tool_call_response("list_transactions", {})])
    r = orch.handle_message(tok, "mis movimientos")
    assert r.disposition == "ESCALATE" and r.category == "tool_failure"
    kept = _files("AUDIT_LOG_PATH", "TRACE_LOG_PATH", "HUMAN_QUEUE_PATH")
    assert all(MARKER not in text for text in kept.values()), [n for n, t in kept.items() if MARKER in t]
    assert '"error_type": "RuntimeError"' in kept["AUDIT_LOG_PATH"] and "RuntimeError" in kept["HUMAN_QUEUE_PATH"] and "RuntimeError" in kept["TRACE_LOG_PATH"]


def test_evidence_that_could_not_be_gathered_leaves_no_message_in_the_ticket(monkeypatch):
    from agent.policy import escalation

    def boom(*a, **k):
        raise RuntimeError(f"disk {MARKER}")

    monkeypatch.setattr(escalation.account_tools, "recent_activity_for_review", boom)
    orch, tok, _ = session([])
    assert orch.handle_message(tok, "me robaron la tarjeta, es un fraude").disposition == "ESCALATE"
    assert MARKER not in _files("HUMAN_QUEUE_PATH")["HUMAN_QUEUE_PATH"]


def test_the_prompt_asks_for_every_read_and_leaves_the_cap_to_the_code():
    from agent.llm import prompts

    assert "hasta dos" not in prompts.SYSTEM_PROMPT and "dos primeras" not in prompts.SYSTEM_PROMPT
    assert "todas" in prompts.SYSTEM_PROMPT


def test_a_third_read_the_model_declared_is_run_never_and_is_announced():
    """El modelo declara las tres lecturas que pidió el cliente; el código ejecuta dos y avisa la tercera."""
    orch, tok, fake = session([tool_call_response(*PENDING, TRANSFERS_5, CARD)])
    r = orch.handle_message(tok, ASK + " y el estado de mi tarjeta")
    assert [f["tool"] for f in r.verified_facts] == ["list_transactions", "list_transactions"]
    assert "Quedó sin atender: estado de pago" in r.response_text


def test_the_unattended_notice_and_its_history_survive_a_repeated_answer():
    three = tool_call_response(*PENDING, TRANSFERS_5, CARD)
    orch, tok, fake = session([three, tool_call_response(*PENDING, TRANSFERS_5, CARD), tool_call_response(*CARD)])
    first = orch.handle_message(tok, ASK + " y mi tarjeta")
    second = orch.handle_message(tok, "te pedi tres cosas")
    assert second.policy_rule == "repeat_guard" and "ya te la respondí" in second.response_text
    assert "Quedó sin atender: estado de pago" in second.response_text and "Quedó sin atender" in first.response_text
    orch.handle_message(tok, "y mi tarjeta?")
    history = fake.calls[2][2:-1]
    assert "sin atender" in history[3]["content"] and "get_payment_status" in history[3]["content"]  # la respuesta repetida


def test_two_reads_that_each_need_a_clarification_lose_neither():
    orch, tok, fake = session([tool_call_response("get_exchange_rate", {}, ("list_transactions", {"product_id": "Cuenta Ahorro"})),
                               tool_call_response("get_account_summary", {})], customer="CLI-FIX0001")
    r = orch.handle_message(tok, "el dólar y los movimientos de mi cuenta de ahorros")
    assert r.disposition == "CLARIFY" and "¿Qué monedas quieres convertir?" in r.response_text
    assert "Quedó sin atender: movimientos" in r.response_text
    orch.handle_message(tok, "USD a MXN")
    assert "list_transactions(Cuenta Ahorro)" in fake.calls[1][2:-1][1]["content"]  # lo que el modelo ya había pedido


def test_a_request_trace_in_any_position_takes_the_turn_alone_and_the_yes_opens_it():
    orch, tok, _ = session([tool_call_response(*PENDING, TRANSFERS_5, ("request_trace", {"amount": 640}))])
    r = orch.handle_message(tok, "pendientes, mis últimas 5 transferencias y mi transferencia de 640 que no llegó")
    assert r.policy_rule == "action:trace_proposed" and "Encontré este movimiento pendiente" in r.response_text
    assert "Quedó sin atender: movimientos pendientes, transferencias" in r.response_text
    opened = orch.handle_message(tok, "sí")
    assert opened.policy_rule == "action:trace_opened" and opened.verified_facts[0]["tool"] == "request_trace"


def test_the_kind_of_a_choice_comes_from_the_backend_not_from_the_words_of_the_reply():
    orch, tok, _ = session([tool_call_response(*PENDING, ("list_transactions", {"product_id": "Cuenta Ahorro"}))], customer="CLI-FIX0001")
    r = orch.handle_message(tok, "mis pendientes y los movimientos de mi cuenta de ahorros")
    assert r.disposition == "CLARIFY" and "Movimientos pendientes" in r.response_text and r.choice == "product"
    orch, tok, _ = session([tool_call_response("request_trace", {})])
    chosen = orch.handle_message(tok, "mis pagos no llegaron")
    assert chosen.policy_rule == "action:trace_choose" and chosen.choice == "movement"
    orch, tok, _ = session([tool_call_response("get_account_summary", {})])
    assert orch.handle_message(tok, "mis saldos").choice is None


def test_the_balance_again_after_the_model_is_restored_is_the_repeat_notice_by_decision():
    """Se decidió: con el mismo saldo la segunda respuesta sería idéntica a la anterior, también al volver el modelo tras
    una caída; sale el aviso, y al insistir se muestra el dato (LIMITATIONS.md)."""
    orch, tok, _ = session([unavailable(), tool_call_response("get_account_summary", {}), tool_call_response("get_account_summary", {})])
    down = orch.handle_message(tok, "¿Cuál es mi saldo?")
    assert down.policy_rule == "degraded:deterministic_balance"
    restored = orch.handle_message(tok, "¿Cuál es mi saldo?")
    assert restored.policy_rule == "repeat_guard" and restored.disposition == "CLARIFY" and restored.llm_calls == 1
    again = orch.handle_message(tok, "¿Cuál es mi saldo?")
    assert again.policy_rule == "verified_tool_results" and again.response_text == down.response_text


def test_a_read_left_unattended_keeps_every_valid_argument_in_the_models_history():
    fx = ("get_exchange_rate", {"source_currency": "USD", "target_currency": "MXN", "on_date": "2024-01-16"})
    orch, tok, fake = session([tool_call_response(*PENDING, TRANSFERS_5, fx), tool_call_response(*CARD)])
    r = orch.handle_message(tok, "pendientes, transferencias y el dólar de hoy")
    assert "Quedó sin atender: tipo de cambio" in r.response_text
    orch.handle_message(tok, "¿y el cambio?")
    kept = fake.calls[1][2:-1][1]["content"]
    assert "get_exchange_rate(on_date=2024-01-16, source_currency=USD, target_currency=MXN)" in kept


def test_a_read_that_is_incomplete_keeps_the_valid_part_and_a_value_that_does_not_pass_is_left_out():
    partial = ("get_exchange_rate", {"source_currency": "usd", "on_date": "2024-01-16"})  # no target: it would need a clarification
    bad = ("list_transactions", {"transaction_type": "Cheque", "limit": 3})  # one value outside its enum, one valid
    orch, tok, fake = session([tool_call_response(*PENDING, TRANSFERS_5, partial, bad), tool_call_response(*CARD)])
    r = orch.handle_message(tok, "pendientes, transferencias, el dólar y cheques")
    assert "Quedó sin atender: tipo de cambio, movimientos" in r.response_text
    orch.handle_message(tok, "¿y lo otro?")
    kept = fake.calls[1][2:-1][1]["content"]
    assert "get_exchange_rate(on_date=2024-01-16, source_currency=USD)" in kept and "list_transactions(limit=3)" in kept


@pytest.mark.parametrize("bad", ["2024-99-99", {"bad": "value"}, ["2024-01-16"], 7.5, "mañana"])
def test_a_date_the_tools_would_reject_is_left_out_of_the_history_and_the_rest_is_kept(bad):
    fx = ("get_exchange_rate", {"source_currency": "USD", "target_currency": "MXN", "on_date": bad})
    listing = ("list_transactions", {"start_date": bad, "end_date": "2024-01-16T10:30:00", "limit": 4})
    orch, tok, fake = session([tool_call_response(*PENDING, TRANSFERS_5, fx, listing), tool_call_response(*CARD)])
    orch.handle_message(tok, "pendientes, transferencias, el dólar y movimientos")
    orch.handle_message(tok, "¿y lo otro?")
    kept = fake.calls[1][2:-1][1]["content"]
    assert "get_exchange_rate(source_currency=USD, target_currency=MXN)" in kept
    assert "list_transactions(limit=4, end_date=2024-01-16)" in kept  # the valid ones stay, the timestamp as the tool reads it: a date
    assert "2024-99" not in kept and "bad" not in kept and "mañana" not in kept


def test_the_history_and_the_tool_use_one_rule_for_a_date():
    import json

    from agent.core.orchestrator import Orchestrator

    for value in ("2024-01-16", "2024-01-16T10:30:00", "2024-99-99", "mañana", " ", 7.5, {"a": 1}):
        try:
            tools.parse_date(value, "on_date")
            accepted = isinstance(value, str)  # the history also wants text, which is what the schema declares
        except Exception:
            accepted = False
        call = {"name": "get_exchange_rate", "arguments": json.dumps({"source_currency": "USD", "target_currency": "MXN", "on_date": value})}
        _, views = Orchestrator._unattended([call], [], "es")
        assert ("on_date=" in views[0]) == accepted, value


def test_requiring_the_mandatory_arguments_is_unchanged_and_a_bad_date_is_still_the_tools_to_reject():
    from agent.core.orchestrator import sanitize_args
    from agent.tools.errors import MissingSlot

    raw = {"source_currency": "usd", "target_currency": "MXN", "on_date": "2024-99-99"}
    args, _ = sanitize_args("get_exchange_rate", raw, [])  # same as before: dates are the tool's to judge
    assert args == {"source_currency": "USD", "target_currency": "MXN", "on_date": "2024-99-99"}
    with pytest.raises(MissingSlot):
        sanitize_args("get_exchange_rate", {"source_currency": "USD"}, [])
    assert sanitize_args("get_exchange_rate", {"source_currency": "USD"}, [], require=False)[0] == {"source_currency": "USD"}
    orch, tok, _ = session([tool_call_response("get_exchange_rate", raw)])
    r = orch.handle_message(tok, "el dólar al 99 del 99")
    assert r.disposition == "CLARIFY" and r.verified_facts == []  # the tool rejects it: a question, as before


# --- prompt 3.3.0: compound requests and source-backed payment conditions --------------------------------------------------

def test_the_prompt_teaches_two_requests_and_registers_conditions_without_changing_existing_tools():
    from agent.llm import prompts

    assert prompts.PROMPT_VERSION == "3.3.0"
    assert [t["function"]["name"] for t in prompts.TOOL_SCHEMAS] == ["get_account_summary", "list_transactions", "get_payment_status",
                                                                     "get_payment_conditions", "get_exchange_rate", "request_trace"]
    for fragment in ("cuánto tengo y mis últimas 4 transferencias", "muéstrame los pagos pendientes y mis 3 últimas transferencias",
                     "quiero ver lo pendiente y las 6 últimas transferencias", "mis saldos, mis 4 últimas transferencias y si mi tarjeta está en mora",
                     "quanto eu tenho e minhas 4 últimas transferências", "mostre os pagamentos pendentes e as 3 últimas transferências",
                     "eu pedi duas coisas", "e as últimas 5?", "transaction_type=Payment, status=Pending"):
        assert fragment in prompts.SYSTEM_PROMPT, fragment
    assert "get_payment_status es solo para atrasos" in prompts.SYSTEM_PROMPT  # pending payments are not a card's delinquency
    assert "hasta dos" not in prompts.SYSTEM_PROMPT and "dos primeras" not in prompts.SYSTEM_PROMPT  # the cap is the code's


def test_the_balance_and_the_last_transfers_the_prompt_example_asks_for_are_two_reads_with_their_own_filters():
    orch, tok, _ = session([tool_call_response("get_account_summary", {}, ("list_transactions", {"transaction_type": "Transfer", "limit": 4}))])
    r = orch.handle_message(tok, "cuánto tengo y mis últimas 4 transferencias")
    assert [f["tool"] for f in r.verified_facts] == ["get_account_summary", "list_transactions"]
    assert "saldo 5,000.00 USD" in r.response_text and "Transferencias (4 más recientes):" in r.response_text
    assert sum(line.startswith("- ") for line in r.response_text.splitlines()) == 2 + 4  # the customer's two products and exactly four transfers


def test_pending_payments_are_the_pending_movements_of_type_payment_and_not_the_cards_delinquency():
    orch, tok, _ = session([tool_call_response("list_transactions", {"transaction_type": "Payment", "status": "Pending"},
                                               ("list_transactions", {"transaction_type": "Transfer", "limit": 3}))])
    r = orch.handle_message(tok, "muéstrame los pagos pendientes y mis 3 últimas transferencias")
    pending = section(r.response_text, "Pagos pendientes")
    assert "250.00 USD" in pending and "640.00" not in pending.split("Transferencias")[0]  # the pending transfer is not a payment
    assert "días de atraso" not in r.response_text and "Transferencias (3 más recientes)" in r.response_text


def test_the_recovery_a_follow_up_gets_keeps_what_the_customer_asked_for_in_the_models_history():
    """After a half answer the history says what was read and with which filters, which is what the prompt asks the model to use."""
    orch, tok, fake = session([tool_call_response("get_account_summary", {}), tool_call_response("list_transactions", {"transaction_type": "Transfer", "limit": 5})])
    orch.handle_message(tok, "quiero mi saldo y mis ultimas 5 transferencias")
    r = orch.handle_message(tok, "¿y las últimas 5?")
    assert r.response_text.startswith("Transferencias (5 más recientes):")
    assert "get_account_summary()" in fake.calls[1][2:-1][1]["content"]
