"""A stand-in for the language model that picks the lookup by keyword: what `ops/serve_fixture.py` runs so the web
front can be developed and shown with no model key.

OFFLINE SIMULATION, like eval/fake_llm.py: the choice of tool is a keyword match, not a model's judgment.
"""
from __future__ import annotations

import re

from agent.llm.client import LLMResponse
from eval.fake_llm import text_response, tool_call_response

RULES: list[tuple[str, str, dict]] = [
    (r"rastre|rastrea|no (me )?lleg|no (me )?chegou|pendiente|pendente", "request_trace", {}),
    (r"movimiento|transacc|movimenta", "list_transactions", {}),
    (r"d[oó]lar|cambio|c[aâ]mbio", "get_exchange_rate", {"source_currency": "USD", "target_currency": "MXN"}),
    (r"atras|al d[ií]a|em dia", "get_payment_status", {"product_id": "Tarjeta Crédito"}),
    (r"saldo|balance", "get_account_summary", {}),
]


PRODUCTS = [(r"ahorro|poupan", "Cuenta Ahorro"), (r"tarjeta|cart[aã]o", "Tarjeta Crédito"),
            (r"pr[eé]stamo|empr[eé]stimo", "Préstamo Personal")]
TAKES_PRODUCT = {"list_transactions", "get_account_summary", "get_payment_status"}


def _lookup(text: str) -> tuple[str | None, dict]:
    return next(((tool, args) for pattern, tool, args in RULES if re.search(pattern, text)), (None, {}))


class KeywordModel:
    """No state of its own: like a live model, it reads everything from the messages it is given, so one instance
    can serve every session. Naming a product ("Cuenta Ahorro ···0002") after a clarification repeats the lookup
    that same conversation asked for."""

    def chat(self, messages, tools=None, temperature=0.0) -> LLMResponse:
        asked = [m["content"].lower() for m in messages if m.get("role") == "user"]
        text = asked[-1] if asked else ""
        last4 = re.search(r"···(\d{4})", text)  # a product picked from the clarification list
        tool, args = _lookup(text)
        if tool is None and last4:
            tool, args = next(((t, a) for t, a in map(_lookup, reversed(asked[:-1])) if t in TAKES_PRODUCT), (None, {}))
        if tool is None:
            return text_response("Entiendo.")
        product = last4.group(1) if last4 else next((name for p, name in PRODUCTS if re.search(p, text)), None)
        return tool_call_response(tool, {**args, "product_id": product} if product and tool in TAKES_PRODUCT else args)
