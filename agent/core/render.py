"""Deterministic ES/PT renderings of verified tool results and canned messages.

Everything the customer reads comes from here: answers, clarifications,
abstentions, escalation notices and the degraded mode. The model never
writes to the customer (ADR-001). Also the output layer of the no-LLM
baseline bot (eval/baseline_bot.py).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

MSG = {
    "reauth": {"es": "Tu sesión expiró o no es válida. Por favor vuelve a iniciar sesión para continuar.",
               "pt": "Sua sessão expirou ou não é válida. Por favor, faça login novamente para continuar."},
    "escalate": {"es": "Entiendo. Voy a transferir tu caso a un agente especializado con todo el detalle, para que no tengas que repetirlo.",
                 "pt": "Entendo. Vou transferir seu caso para um atendente especializado com todos os detalhes, para você não precisar repetir."},
    "escalate_security": {"es": "Por seguridad no puedo mostrar esa información. Un agente revisará tu solicitud y te contactará.",
                          "pt": "Por segurança não posso mostrar essa informação. Um atendente vai revisar sua solicitação e entrar em contato."},
    "escalate_unverified": {"es": "No pude registrar tu caso en este momento, así que no quedó derivado. Por favor comunícate con la línea de atención del banco y menciona el código {code}.",
                            "pt": "Não consegui registrar seu caso agora, então ele não foi encaminhado. Por favor, entre em contato com a central de atendimento do banco e informe o código {code}."},
    "abstain": {"es": "Eso está fuera de lo que puedo resolver en consultas de cuenta y pagos (saldos, movimientos, estado de pago y tipo de cambio). Te oriento al área correspondiente.",
                "pt": "Isso está fora do que posso resolver em consultas de conta e pagamentos (saldos, movimentações, situação de pagamento e câmbio). Vou te orientar para a área correta."},
    "clarify_generic": {"es": "¿Me cuentas un poco más qué necesitas? Puedo ayudarte con saldos, movimientos, estado de pago o tipo de cambio.",
                        "pt": "Pode me contar um pouco mais do que precisa? Posso ajudar com saldos, movimentações, situação de pagamento ou câmbio."},
    "clarify_dates": {"es": "¿Para qué fechas? Indícalas como AAAA-MM-DD.", "pt": "Para quais datas? Informe como AAAA-MM-DD."},
    "clarify_currency": {"es": "¿Qué monedas quieres convertir? (MXN, COP, ARS o USD)", "pt": "Quais moedas você quer converter? (MXN, COP, ARS ou USD)"},
    "clarify_product": {"es": "¿Sobre cuál de tus productos?", "pt": "Sobre qual dos seus produtos?"},
    "as_of": {"es": "Información al {d}.", "pt": "Informação de {d}."},
}

TYPE_PT = {"Cuenta Ahorro": "Conta Poupança", "Cuenta Corriente": "Conta Corrente", "Tarjeta Débito": "Cartão de Débito",
           "Tarjeta Crédito": "Cartão de Crédito", "Préstamo Personal": "Empréstimo Pessoal",
           "Préstamo Hipotecario": "Financiamento Imobiliário", "Inversión": "Investimento", "Seguro": "Seguro"}
STATUS = {"es": {"Active": "activa", "Blocked": "bloqueada", "Closed": "cerrada", "Suspended": "suspendida",
                 "Approved": "aprobada", "Declined": "rechazada", "Pending": "pendiente", "Reversed": "revertida"},
          "pt": {"Active": "ativa", "Blocked": "bloqueada", "Closed": "encerrada", "Suspended": "suspensa",
                 "Approved": "aprovada", "Declined": "recusada", "Pending": "pendente", "Reversed": "estornada"}}


def money(v: Any, cur: str) -> str:
    return f"{float(v):,.2f} {cur}"


def fmt_date(d: Any) -> str:
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d/%m/%Y") if isinstance(d, date) else str(d)


def product_label(p: dict, lang: str) -> str:
    t = p.get("product_type", "")
    return f"{TYPE_PT.get(t, t) if lang == 'pt' else t} ···{p.get('last4') or '????'}"


def as_of_line(as_of: Any, lang: str) -> str:
    return MSG["as_of"][lang].format(d=fmt_date(as_of)) if as_of else ""


def clarify(missing: list[str], catalog: list[dict], lang: str) -> str:
    if "product_id" in missing and catalog:
        opts = "; ".join(f"{i + 1}) {product_label(p, lang)} ({p['currency']})" for i, p in enumerate(catalog))
        return f"{MSG['clarify_product'][lang]} {opts}"
    if any(s in missing for s in ("start_date", "end_date", "on_date")):
        return MSG["clarify_dates"][lang]
    if any(s in missing for s in ("source_currency", "target_currency")):
        return MSG["clarify_currency"][lang]
    return MSG["clarify_generic"][lang]


def render_result(tool: str, result: dict, lang: str) -> str:
    es = lang == "es"
    if result.get("not_applicable"):
        t = result.get("product_type", "")
        return (f"El estado de pago aplica solo a tarjetas de crédito y préstamos; tu {t} no tiene pagos pendientes de ese tipo."
                if es else f"A situação de pagamento se aplica só a cartões de crédito e empréstimos; sua {TYPE_PT.get(t, t)} não tem esse tipo de pagamento.")
    if tool == "get_account_summary":
        lines = []
        for it in result["items"]:
            st = STATUS[lang].get(it["product_status"], it["product_status"])
            lines.append(f"- {product_label(it, lang)}: {'saldo' if es else 'saldo'} {money(it['current_balance'], it['currency'])} ({st})")
        return "\n".join(lines)
    if tool == "list_transactions":
        if not result["items"]:
            return "No encontré movimientos con esos filtros." if es else "Não encontrei movimentações com esses filtros."
        lines = [f"- {fmt_date(t['transaction_date'])}: {t['transaction_type']} {money(t['amount'], t['currency'])}"
                 f"{' · ' + t['merchant_name'] if t.get('merchant_name') else ''} ({STATUS[lang].get(t['transaction_status'], t['transaction_status'])})"
                 for t in result["items"]]
        return "\n".join(lines)
    if tool == "get_payment_status":
        dpd, cur = result["days_past_due"], result.get("currency") or ""
        head = (f"Tu {result['product_type']} tiene {dpd} días de atraso." if dpd else f"Tu {result['product_type']} está al día.") if es else \
               (f"Seu {TYPE_PT.get(result['product_type'])} tem {dpd} dias de atraso." if dpd else f"Seu {TYPE_PT.get(result['product_type'])} está em dia.")
        extra = []
        if result.get("current_balance") is not None:
            extra.append(("Saldo utilizado: " if es else "Saldo utilizado: ") + money(result["current_balance"], cur) + ".")
        if result.get("available_credit") is not None:
            extra.append(("Crédito disponible: " if es else "Crédito disponível: ") + money(result["available_credit"], cur) + ".")
        return " ".join([head] + extra)
    if tool == "get_exchange_rate":
        s = (f"1 {result['source_currency']} = {float(result['exchange_rate']):.6f} {result['target_currency']} "
             f"({'fecha' if es else 'data'} {fmt_date(result['used_date'])})")
        if result.get("was_fallback"):
            s += " — sin dato para la fecha pedida; uso el más reciente anterior." if es else " — sem dado para a data pedida; uso o mais recente anterior."
        if result.get("derived_from_inverse"):
            s += " Calculado a partir del par inverso." if es else " Calculado a partir do par inverso."
        return s
    return str(result)


def render_answer(results: list[dict], lang: str, catalog: list[dict] | None = None) -> str:
    """Verified facts as text. A transaction list is headed by its product, so two lists never blur together."""
    labels = {p["product_id"]: product_label(p, lang) for p in catalog or []}
    parts = []
    for r in results:
        body = render_result(r["tool"], r["result"], lang)
        pid = (r["result"].get("filters") or {}).get("product_id") if r["tool"] == "list_transactions" else None
        parts.append(f"{labels[pid]}:\n{body}" if pid in labels else body)
    as_of = next((r["result"].get("as_of") for r in results if isinstance(r.get("result"), dict) and r["result"].get("as_of")), None)
    return "\n".join(p for p in parts + [as_of_line(as_of, lang)] if p)
