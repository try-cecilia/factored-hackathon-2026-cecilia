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
    "trace_propose": {"es": "Encontré este movimiento pendiente: {mov}. ¿Quieres que abra un pedido de rastreo? Responde sí o no.",
                      "pt": "Encontrei esta movimentação pendente: {mov}. Quer que eu abra um pedido de rastreamento? Responda sim ou não."},
    "trace_choose": {"es": "Tienes varios movimientos pendientes: {opts}. ¿Cuál quieres rastrear? Responde con su número, o dime el monto o la fecha.",
                     "pt": "Você tem várias movimentações pendentes: {opts}. Qual quer rastrear? Responda com o número, ou me diga o valor ou a data."},
    "trace_opened": {"es": "Listo: abrí el pedido de rastreo {tid} para la {mov}. Operaciones responde en hasta {sla} días hábiles; si te lo piden, el número es {tid}.",
                     "pt": "Pronto: abri o pedido de rastreamento {tid} para a {mov}. A equipe de operações responde em até {sla} dias úteis; se pedirem, o número é {tid}."},
    "trace_already_open": {"es": "Ya tienes abierto el pedido de rastreo {tid} para la {mov}. Operaciones responde en hasta {sla} días hábiles desde que se abrió.",
                           "pt": "Você já tem aberto o pedido de rastreamento {tid} para a {mov}. A equipe de operações responde em até {sla} dias úteis desde a abertura."},
    "trace_cancelled": {"es": "Entendido, no abrí ningún pedido. Si más adelante lo necesitas, pídemelo.",
                        "pt": "Entendido, não abri nenhum pedido. Se precisar depois, é só pedir."},
    # What the customer is told when a person acts on their case (agent/policy/desk.py). Never the operator's name or a
    # rejection's note, which are internal; a resolution's message is the one text a person writes for the customer.
    "case_claimed": {"es": "Novedad de tu caso: un agente ya lo tomó y lo está revisando.",
                     "pt": "Novidade do seu caso: um atendente já assumiu e está analisando."},
    "case_approved": {"es": "Novedad de tu caso: un agente aprobó el rastreo y abrió el pedido {tid}. Operaciones responde en hasta {sla} días hábiles.",
                      "pt": "Novidade do seu caso: um atendente aprovou o rastreamento e abriu o pedido {tid}. A equipe de operações responde em até {sla} dias úteis."},
    "case_rejected": {"es": "Novedad de tu caso: un agente lo revisó y no pudo abrir el rastreo. Si necesitas más ayuda, puedes comunicarte con la línea de atención del banco.",
                      "pt": "Novidade do seu caso: um atendente analisou e não conseguiu abrir o rastreamento. Se precisar de mais ajuda, entre em contato com a central de atendimento do banco."},
    # A rejected ticket that carried no trace: nothing was asked to be opened, so nothing is said about one.
    "case_rejected_plain": {"es": "Novedad de tu caso: un agente lo revisó y no puede resolverlo por este canal. Si necesitas más ayuda, puedes comunicarte con la línea de atención del banco.",
                            "pt": "Novidade do seu caso: um atendente analisou e não pode resolvê-lo por este canal. Se precisar de mais ajuda, entre em contato com a central de atendimento do banco."},
    "case_resolved": {"es": "Novedad de tu caso: un agente lo resolvió. Mensaje del agente: «{message}»",
                      "pt": "Novidade do seu caso: um atendente resolveu. Mensagem do atendente: «{message}»"},
    # Resolved with a predefined result (RESOLVE_RESULT): the bank's fixed words, and the person's own, if any, in the same quote.
    "case_resolved_result": {"es": "Novedad de tu caso: un agente lo resolvió. {result}",
                             "pt": "Novidade do seu caso: um atendente resolveu. {result}"},
    "case_resolved_result_message": {"es": "Novedad de tu caso: un agente lo resolvió. {result} Mensaje del agente: «{message}»",
                                     "pt": "Novidade do seu caso: um atendente resolveu. {result} Mensagem do atendente: «{message}»"},
    "case_handed_back": {"es": "Novedad de tu caso: un agente lo devolvió al asistente. Cuéntame en qué más puedo ayudarte.",
                         "pt": "Novidade do seu caso: um atendente devolveu ao assistente. Conte como posso ajudar."},
    "case_stale": {"es": "Novedad de tu caso: al revisarlo, el movimiento ya no figura como pendiente, así que no hizo falta abrir un rastreo.",
                   "pt": "Novidade do seu caso: ao revisar, a movimentação já não consta como pendente, então não foi preciso abrir um rastreamento."},
}
# The predefined results of a resolution (agent/policy/desk.py RESULTS), as the customer reads them: what a person found and
# what comes next, never an action done (resolving does none; tests/test_desk.py holds every text to that).
RESOLVE_RESULT = {
    "charge_confirmed": {"es": "Revisamos el movimiento y corresponde a una operación válida de tu cuenta.",
                         "pt": "Analisamos a movimentação e ela corresponde a uma operação válida da sua conta."},
    "movement_settled": {"es": "Revisamos el movimiento y ya figura como completado.",
                         "pt": "Analisamos a movimentação e ela já consta como concluída."},
    "trace_not_possible": {"es": "Revisamos el movimiento y no se puede rastrear por este canal. Te contactaremos al número registrado.",
                           "pt": "Analisamos a movimentação e não é possível rastreá-la por este canal. Entraremos em contato pelo número cadastrado."},
    "needs_specialist": {"es": "Revisamos tu caso y necesita un área especializada del banco. Te contactaremos al número registrado.",
                         "pt": "Analisamos o seu caso e ele precisa de uma área especializada do banco. Entraremos em contato pelo número cadastrado."},
    "info_checked": {"es": "Revisamos tu consulta en el sistema del banco y los datos de tu cuenta están en orden.",
                     "pt": "Analisamos a sua consulta no sistema do banco e os dados da sua conta estão em ordem."},
    "no_action_needed": {"es": "Revisamos tu caso y no hace falta ninguna acción de tu parte.",
                         "pt": "Analisamos o seu caso e não é necessária nenhuma ação da sua parte."},
    "will_contact": {"es": "Revisamos tu caso. Te contactaremos al número registrado.",
                     "pt": "Analisamos o seu caso. Entraremos em contato pelo número cadastrado."},
    "call_the_bank": {"es": "Revisamos tu caso. Para continuar, puedes comunicarte con la línea de atención del banco.",
                      "pt": "Analisamos o seu caso. Para continuar, entre em contato com a central de atendimento do banco."},
}
TXN_TYPE = {"es": {"Transfer": "transferencia", "Payment": "operación de pago", "Deposit": "operación de depósito"},
            "pt": {"Transfer": "transferência", "Payment": "operação de pagamento", "Deposit": "operação de depósito"}}

TYPE_PT = {"Cuenta Ahorro": "Conta Poupança", "Cuenta Corriente": "Conta Corrente", "Tarjeta Débito": "Cartão de Débito",
           "Tarjeta Crédito": "Cartão de Crédito", "Préstamo Personal": "Empréstimo Pessoal",
           "Préstamo Hipotecario": "Financiamento Imobiliário", "Inversión": "Investimento", "Seguro": "Seguro"}
STATUS = {"es": {"Active": "activa", "Blocked": "bloqueada", "Closed": "cerrada", "Suspended": "suspendida",
                 "Approved": "aprobada", "Declined": "rechazada", "Pending": "pendiente", "Reversed": "revertida"},
          "pt": {"Active": "ativa", "Blocked": "bloqueada", "Closed": "encerrada", "Suspended": "suspensa",
                 "Approved": "aprovada", "Declined": "recusada", "Pending": "pendente", "Reversed": "estornada"}}


def case_update(status: str, lang: str, trace: dict | None = None, message: str | None = None,
                had_action: bool = True, result: str | None = None) -> str | None:
    """The customer-facing line for what a person did with their ticket, or None for a status with nothing to say.
    `message` is a resolution's words to the customer; `had_action` says whether the ticket carried a trace to decide;
    `result` is the predefined result a resolution named, said before the message, which never replaces it."""
    key = "case_rejected_plain" if status == "rejected" and not had_action else f"case_{status}"
    if status == "resolved" and result in RESOLVE_RESULT:
        key = "case_resolved_result_message" if message else "case_resolved_result"
    entry = MSG.get(key)
    if entry is None:
        return None
    return entry[lang].format(tid=(trace or {}).get("trace_id", ""), sla=(trace or {}).get("sla_business_days", ""),
                              message=message or "", result=RESOLVE_RESULT[result][lang] if key.startswith("case_resolved_result") else "")


def money(v: Any, cur: str) -> str:
    return f"{float(v):,.2f} {cur}"


def fmt_date(d: Any) -> str:
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d/%m/%Y") if isinstance(d, date) else str(d)


def product_label(p: dict, lang: str) -> str:
    t = p.get("product_type", "")
    return f"{TYPE_PT.get(t, t) if lang == 'pt' else t} ···{p.get('last4') or '????'}"


def movement(m: dict, lang: str) -> str:
    """A pending movement as the customer knows it: kind, amount, date and product (type and last 4)."""
    kind = TXN_TYPE[lang].get(m["transaction_type"], m["transaction_type"])
    on = "del" if lang == "es" else "de"
    return f"{kind} de {money(m['amount'], m['currency'])} {on} {fmt_date(m['transaction_date'])} ({product_label(m, lang)})"


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


RANGE = {"es": ("del {a} al {b}", "desde el {a}", "hasta el {b}", "Movimientos"),
         "pt": ("de {a} a {b}", "desde {a}", "até {b}", "Movimentações")}


def _date_scope(result: dict, lang: str) -> str:
    f = result.get("filters") or {}
    a, b = f.get("start_date"), f.get("end_date")
    both, since, until, _ = RANGE[lang]
    if a and b:
        return both.format(a=fmt_date(a), b=fmt_date(b))
    return since.format(a=fmt_date(a)) if a else until.format(b=fmt_date(b)) if b else ""


# --- what a turn says around its reads (nothing here comes from the model) -----------------------------------------------

READ_MSG = {
    "repeat": {"es": "Esa consulta ya te la respondí arriba y los datos no cambiaron. {as_of} Si pediste otra cosa, dime cuál: puedo mostrarte "
                     "movimientos (también solo transferencias, pagos o depósitos, o solo los pendientes), saldos, estado de pago o tipo de cambio.",
               "pt": "Essa consulta eu já respondi acima e os dados não mudaram. {as_of} Se você pediu outra coisa, me diga qual: posso mostrar "
                     "movimentações (também só transferências, pagamentos ou depósitos, ou só as pendentes), saldos, situação de pagamento ou câmbio."},
    "unattended": {"es": "Tu mensaje tenía más consultas de las que atiendo a la vez. Quedó sin atender: {parts}. Pídemelo en otro mensaje.",
                   "pt": "Sua mensagem tinha mais consultas do que atendo de uma vez. Ficou sem atender: {parts}. Peça em outra mensagem."},
}
# A type in the plural and a count read as "Transferencias (5 más recientes)": no ordinal in front, so no gender to agree.
KIND_PLURAL = {"es": {"Deposit": "depósitos", "Withdrawal": "retiros", "Transfer": "transferencias", "Payment": "pagos", "Purchase": "compras",
                      "Adjustment": "ajustes"},
               "pt": {"Deposit": "depósitos", "Withdrawal": "saques", "Transfer": "transferências", "Payment": "pagamentos", "Purchase": "compras",
                      "Adjustment": "ajustes"}}
PENDING_WORD = {"es": "pendientes", "pt": "pendentes"}  # the same for both genders
STATUS_WORD = {"es": "estado", "pt": "situação"}
MOST_RECENT = {"es": ("más reciente", "{n} más recientes"), "pt": ("mais recente", "{n} mais recentes")}
READ_PART = {"es": {"get_account_summary": "saldos", "get_payment_status": "estado de pago", "get_exchange_rate": "tipo de cambio",
                    "request_trace": "rastreo de un movimiento", "other": "otra consulta"},
             "pt": {"get_account_summary": "saldos", "get_payment_status": "situação de pagamento", "get_exchange_rate": "câmbio",
                    "request_trace": "rastreamento de uma movimentação", "other": "outra consulta"}}


def _narrowing(filters: dict, shown: int, lang: str) -> tuple[str, list[str]]:
    """What a movements list is about when the customer narrowed it by type or status: its noun ("Transferencias",
    "Movimientos pendientes") and the notes that go in parentheses ("5 más recientes", the status). ("", []) when it
    was not narrowed. The type and the status are checked values (enums), so every word here is a fixed one."""
    kind, status = filters.get("transaction_type"), filters.get("status")
    if not kind and not status:
        return "", []
    noun = KIND_PLURAL[lang].get(kind, kind).capitalize() if kind else RANGE[lang][3]
    notes = []
    if status == "Pending":
        noun += " " + PENDING_WORD[lang]
    elif status:
        notes.append(f"{STATUS_WORD[lang]}: {STATUS[lang].get(status, status)}")
    if kind and shown:
        notes.append(MOST_RECENT[lang][shown > 1].format(n=shown))
    return noun, notes


def _list_label(res: dict, product: str, lang: str) -> str:
    """The heading of a movements list: its product, the type and status it was narrowed to, and the dates it covers."""
    scope = _date_scope(res, lang)
    noun, notes = _narrowing(res.get("filters") or {}, len(res.get("items") or []), lang)
    if not noun:
        return f"{product or RANGE[lang][3]} ({scope})" if scope else product
    notes += [scope] if scope else []
    head = f"{noun} ({', '.join(notes)})" if notes else noun
    return f"{head} · {product}" if product else head


def read_part(tool: str, args: dict, lang: str) -> str:
    """A read named for the customer, in a fixed word: what a turn left unattended ("transferencias", "estado de pago")."""
    if tool == "list_transactions":
        kind, status = args.get("transaction_type"), args.get("status")
        noun = KIND_PLURAL[lang].get(kind, "") or RANGE[lang][3].lower()
        return f"{noun} {PENDING_WORD[lang]}" if status == "Pending" else noun
    return READ_PART[lang].get(tool, READ_PART[lang]["other"])


def repeat_notice(as_of: Any, lang: str) -> str:
    """What the customer reads when the answer would be the one they just got: it says so, and what else can be asked."""
    return " ".join(READ_MSG["repeat"][lang].format(as_of=as_of_line(as_of, lang)).split())


def unattended_notice(parts: list[str], lang: str) -> str:
    return READ_MSG["unattended"][lang].format(parts=", ".join(dict.fromkeys(parts)))


def render_answer(results: list[dict], lang: str, catalog: list[dict] | None = None) -> str:
    """Verified facts as text. Every product-specific answer is headed by its product (two cards never blur
    together), and a filtered transaction list says which dates it covers."""
    labels = {p["product_id"]: product_label(p, lang) for p in catalog or []}
    parts = []
    for r in results:
        res = r["result"]
        body = render_result(r["tool"], res, lang)
        label = labels.get(res.get("product_id") or (res.get("filters") or {}).get("product_id"), "")
        if r["tool"] == "list_transactions":
            label = _list_label(res, label, lang)
        parts.append(f"{label}:\n{body}" if label else body)
    as_of = next((r["result"].get("as_of") for r in results if isinstance(r.get("result"), dict) and r["result"].get("as_of")), None)
    return "\n".join(p for p in parts + [as_of_line(as_of, lang)] if p)
