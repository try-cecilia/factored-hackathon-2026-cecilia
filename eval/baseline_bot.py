"""Baseline system: a deterministic keyword bot, no LLM.

What a bank would ship without generative AI — keyword routing, regex slot
extraction, templated answers, no conversational memory. It deliberately
shares everything *except* understanding with the proposed system: the same
session validation, compliance hold, safety lexicon, tool layer (with the
same ownership checks), escalation tickets and renderer. So the comparison
in eval/run_system_eval.py isolates what the LLM (+ learned classifier)
adds on the same held-out workload, and nothing else.
"""
from __future__ import annotations

import re
import time
import uuid

from agent.core import render
from agent.core.orchestrator import TurnResult, resolve_product_ref
from agent.llm import baseline_classifier
from agent.policy import escalation
from agent.policy.router import Decision, Disposition, after_tool
from agent.policy.signals import detect_language, escalation_categories, normalize
from agent.session.auth import ExpiredSession, InvalidSession, SessionStore
from agent.tools import account_tools
from agent.tools.errors import MissingSlot, NotApplicable, ToolError

TYPE_WORDS = {
    "Cuenta Ahorro": [r"\bahorro", r"\bpoupanca\b"],
    "Cuenta Corriente": [r"\bcorriente\b", r"\bconta corrente\b"],
    "Tarjeta Crédito": [r"\bcredito\b"],
    "Tarjeta Débito": [r"\bdebito\b"],
    "Préstamo Personal": [r"\bprestamo\b", r"\bemprestimo\b"],
    "Préstamo Hipotecario": [r"\bhipotec", r"\bimobiliario\b"],
}
CURRENCY_WORDS = {"USD": [r"\bdolar", r"\busd\b"], "MXN": [r"\bpeso mexicano", r"\bmxn\b"],
                  "COP": [r"\bpeso colombiano", r"\bcop\b"], "ARS": [r"\bpeso argentino", r"\bars\b"]}
LOCAL = {"México": "MXN", "Colombia": "COP", "Argentina": "ARS"}


def _product_from_text(text: str, catalog: list[dict]) -> str | None:
    digits = re.findall(r"\b\d{4}\b", text)
    if digits:
        return resolve_product_ref(digits[-1], catalog)
    norm = normalize(text)
    types = [t for t, pats in TYPE_WORDS.items() if any(re.search(p, norm) for p in pats)]
    if len(types) == 1:
        return resolve_product_ref(types[0], catalog)
    return None


class BaselineBot:
    def __init__(self, session_store: SessionStore):
        self.session_store = session_store

    def handle_message(self, token: str, text: str) -> TurnResult:
        start, trace_id = time.perf_counter(), uuid.uuid4().hex  # a monotonic clock fine enough for milliseconds
        lang = detect_language(text).language
        try:
            session = self.session_store.validate(token)
        except (InvalidSession, ExpiredSession):
            return TurnResult(trace_id, "REAUTH_REQUIRED", render.MSG["reauth"][lang], lang, "session", latency_ms=(time.perf_counter() - start) * 1000)

        def esc(decision: Decision, actions=()):
            t = escalation.escalate(decision, session.customer_id, session.ref, text, lang, list(actions), [], [], session.attributes, trace_id)
            msg = render.MSG["escalate_security" if decision.category == "security" else "escalate"][lang]
            return TurnResult(trace_id, "ESCALATE", msg, lang, decision.category, decision.rule, t.ticket_id,
                              latency_ms=(time.perf_counter() - start) * 1000)

        if session.attributes.get("customer_status") == "Suspended":
            return esc(Decision(Disposition.ESCALATE, "compliance hold", "compliance_hold", rule="customer_status == Suspended"))
        intent = baseline_classifier.classify(text)
        if intent == "requires_escalation":
            cats = escalation_categories(text) or ["fraud"]
            return esc(Decision(Disposition.ESCALATE, "keyword escalation", cats[0], rule=f"lexicon:{cats[0]}"))
        if intent == "out_of_scope":
            return TurnResult(trace_id, "ABSTAIN", render.MSG["abstain"][lang], lang, "out_of_scope", "keyword:out_of_scope",
                              latency_ms=(time.perf_counter() - start) * 1000)

        catalog = account_tools.get_customer_profile(session.customer_id)["products"]
        tool, args = None, {}
        try:
            product = _product_from_text(text, catalog)
            if intent == "balance_inquiry":
                tool, args = "get_account_summary", ({"product_id": product} if product else {})
            elif intent == "transaction_lookup":
                tool, args = "list_transactions", ({"product_id": product} if product else {})
            elif intent == "payment_status":
                norm = normalize(text)
                is_condition = any(re.search(p, norm) for p in
                                   (r"\bcomision", r"\bcomissao", r"\btarifa", r"\bcuanto cuesta\b", r"\bquanto custa\b",
                                    r"\bplazo\b", r"\bprazo\b", r"\bumbral\b", r"\blimite de transferencia\b"))
                if is_condition:
                    if product is None:
                        active = [p for p in catalog if p["product_status"] != "Closed"]
                        if len(active) != 1:
                            raise MissingSlot("which product", missing_slots=["product_id"])
                        product = active[0]["product_id"]
                    operation = next((name for name, pats in {
                        "Transfer": (r"transfer",), "Payment": (r"pago", r"pagamento"),
                        "Deposit": (r"deposit",), "Withdrawal": (r"retiro", r"saque"),
                        "Purchase": (r"compra", r"purchase")}.items() if any(re.search(p, norm) for p in pats)), None)
                    kind = ("commission" if any(re.search(p, norm) for p in (r"comision", r"comissao", r"tarifa", r"cuesta", r"custa"))
                            else "deadline" if any(re.search(p, norm) for p in (r"plazo", r"prazo", r"dias", r"dias uteis"))
                            else "threshold")
                    if operation is None:
                        raise MissingSlot("which payment operation", missing_slots=["operation"])
                    tool, args = "get_payment_conditions", {"product_id": product, "operation": operation, "kind": kind}
                else:
                    if product is None:
                        credit = [p for p in catalog if p["product_type"] in account_tools.CREDIT_PRODUCT_TYPES and p["product_status"] != "Closed"]
                        if len(credit) != 1:
                            raise MissingSlot("which credit product", missing_slots=["product_id"])
                        product = credit[0]["product_id"]
                    tool, args = "get_payment_status", {"product_id": product}
            else:
                norm = normalize(text)
                found = [c for c, pats in CURRENCY_WORDS.items() if any(re.search(p, norm) for p in pats)]
                local = LOCAL.get(session.attributes.get("country"), "USD")
                pair = found[:2] if len(found) >= 2 else ([found[0], local] if found and found[0] != local else ["USD", local])
                tool, args = "get_exchange_rate", {"source_currency": pair[0], "target_currency": pair[1]}
            fn = {"get_account_summary": account_tools.get_account_summary, "list_transactions": account_tools.list_transactions,
                  "get_payment_status": account_tools.get_payment_status, "get_payment_conditions": account_tools.get_payment_conditions,
                  "get_exchange_rate": account_tools.get_exchange_rate}[tool]
            result, error = fn(session.customer_id, **args), None
        except NotApplicable as exc:
            result, error = {"not_applicable": True, **exc.payload}, None
        except ToolError as exc:
            result, error = None, exc
        except Exception as exc:  # noqa: BLE001 - same bounded fallback as the proposed system
            result, error = None, ToolError(f"unexpected failure in {tool}: {type(exc).__name__}")
        action = {"tool": tool, "args": args, "success": error is None, "error_type": type(error).__name__ if error else None}
        decision = after_tool(error)
        if decision is not None:
            if decision.disposition == Disposition.CLARIFY:
                return TurnResult(trace_id, "CLARIFY", render.clarify(decision.missing_slots, catalog, lang), lang, decision.category,
                                  decision.rule, tool_calls=[action], latency_ms=(time.perf_counter() - start) * 1000)
            return esc(decision, [action])
        facts = [{"tool": tool, "args": args, "result": result}]
        return TurnResult(trace_id, "AUTO_RESOLVE", render.render_answer(facts, lang, country=session.attributes.get("country")), lang, "resolved", "keyword_routing",
                          None, facts, [action], latency_ms=(time.perf_counter() - start) * 1000)
