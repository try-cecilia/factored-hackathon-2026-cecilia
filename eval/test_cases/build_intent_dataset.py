"""Builds the labeled utterance set for the intent classifier.

Data-provenance note (read this before trusting these labels): the supplied
LATAM Bank dataset's `reason_category` (6 broad buckets) and `call_transcripts
.detected_intents` (unstructured, from an unknown upstream NLP pipeline) do
not carry the fine-grained intent taxonomy this workflow's tool-routing needs
(balance_inquiry / transaction_lookup / payment_status / exchange_rate_inquiry
/ out_of_scope / requires_escalation). So this set is team-authored from
templates, in Spanish and Portuguese, NOT derived from the real dataset —
exactly the kind of limitation the challenge asks to report explicitly rather
than silently pass off as production ground truth.

Leakage prevention: every generated utterance carries the template_id it came
from. Train/test splits must partition by template_id (see
eval/evaluate_intent_classifier.py), never by row — otherwise a
slot-substituted twin of a training sentence would leak into the test set.
"""
from __future__ import annotations

import csv
import itertools
from pathlib import Path

# (intent, language, template_id, template) — {slot} placeholders filled below.
TEMPLATES = [
    # --- balance_inquiry ---
    ("balance_inquiry", "es", "bal_es_1", "¿Cuál es mi saldo en mi {account}?"),
    ("balance_inquiry", "es", "bal_es_2", "¿Cuánto dinero tengo disponible en mi {account}?"),
    ("balance_inquiry", "es", "bal_es_3", "Quiero saber el saldo de mi {account}, por favor"),
    ("balance_inquiry", "es", "bal_es_4", "Dime cuánto tengo en {account}"),
    ("balance_inquiry", "es", "bal_es_5", "Necesito consultar el saldo actual de todas mis cuentas"),
    ("balance_inquiry", "pt", "bal_pt_1", "Qual é o meu saldo na minha {account_pt}?"),
    ("balance_inquiry", "pt", "bal_pt_2", "Quanto dinheiro eu tenho disponível na minha {account_pt}?"),
    ("balance_inquiry", "pt", "bal_pt_3", "Quero saber o saldo da minha {account_pt}, por favor"),
    ("balance_inquiry", "pt", "bal_pt_4", "Me diga quanto eu tenho na {account_pt}"),
    ("balance_inquiry", "pt", "bal_pt_5", "Preciso consultar o saldo atual de todas as minhas contas"),
    # --- transaction_lookup ---
    ("transaction_lookup", "es", "txn_es_1", "¿Puedes mostrarme mis últimos movimientos de {account}?"),
    ("transaction_lookup", "es", "txn_es_2", "Necesito ver las transacciones de {account} de la semana pasada"),
    ("transaction_lookup", "es", "txn_es_3", "¿Qué compras hice ayer con mi {account}?"),
    ("transaction_lookup", "es", "txn_es_4", "Muéstrame el historial de movimientos de mi {account}"),
    ("transaction_lookup", "es", "txn_es_5", "Quiero revisar mis últimos gastos"),
    ("transaction_lookup", "pt", "txn_pt_1", "Pode me mostrar minhas últimas movimentações da {account_pt}?"),
    ("transaction_lookup", "pt", "txn_pt_2", "Preciso ver as transações da {account_pt} da semana passada"),
    ("transaction_lookup", "pt", "txn_pt_3", "Quais compras eu fiz ontem com meu {account_pt}?"),
    ("transaction_lookup", "pt", "txn_pt_4", "Mostra o histórico de movimentações da minha {account_pt}"),
    ("transaction_lookup", "pt", "txn_pt_5", "Quero revisar meus últimos gastos"),
    # --- payment_status ---
    ("payment_status", "es", "pay_es_1", "¿Estoy al día con el pago de mi {credit_product}?"),
    ("payment_status", "es", "pay_es_2", "¿Tengo pagos atrasados en mi {credit_product}?"),
    ("payment_status", "es", "pay_es_3", "¿Cuánto crédito me queda disponible en mi {credit_product}?"),
    ("payment_status", "es", "pay_es_4", "¿Cuántos días de mora tengo en mi {credit_product}?"),
    ("payment_status", "pt", "pay_pt_1", "Estou em dia com o pagamento do meu {credit_product_pt}?"),
    ("payment_status", "pt", "pay_pt_2", "Tenho pagamentos atrasados no meu {credit_product_pt}?"),
    ("payment_status", "pt", "pay_pt_3", "Quanto crédito ainda tenho disponível no meu {credit_product_pt}?"),
    ("payment_status", "pt", "pay_pt_4", "Quantos dias de atraso eu tenho no meu {credit_product_pt}?"),
    # --- exchange_rate_inquiry ---
    ("exchange_rate_inquiry", "es", "fx_es_1", "¿A cuánto está el {currency} hoy?"),
    ("exchange_rate_inquiry", "es", "fx_es_2", "¿Cuál es el tipo de cambio de {currency} a dólares?"),
    ("exchange_rate_inquiry", "es", "fx_es_3", "Necesito saber la cotización del {currency} de ayer"),
    ("exchange_rate_inquiry", "pt", "fx_pt_1", "Qual é a cotação do {currency_pt} hoje?"),
    ("exchange_rate_inquiry", "pt", "fx_pt_2", "Quanto está o câmbio de {currency_pt} para dólar?"),
    ("exchange_rate_inquiry", "pt", "fx_pt_3", "Preciso saber a cotação de ontem do {currency_pt}"),
    # --- out_of_scope ---
    ("out_of_scope", "es", "oos_es_1", "Quiero bloquear mi tarjeta porque la perdí"),
    ("out_of_scope", "es", "oos_es_2", "Necesito solicitar un préstamo nuevo"),
    ("out_of_scope", "es", "oos_es_3", "¿Cuáles son los requisitos para una tarjeta de crédito?"),
    ("out_of_scope", "es", "oos_es_4", "Quiero abrir una disputa por un cobro"),
    ("out_of_scope", "es", "oos_es_5", "¿Puedo aumentar el límite de mi tarjeta?"),
    ("out_of_scope", "es", "oos_es_6", "¿Cómo cambio mi número de teléfono registrado?"),
    ("out_of_scope", "pt", "oos_pt_1", "Quero bloquear meu cartão porque perdi"),
    ("out_of_scope", "pt", "oos_pt_2", "Preciso solicitar um novo empréstimo"),
    ("out_of_scope", "pt", "oos_pt_3", "Quais são os requisitos para um cartão de crédito?"),
    ("out_of_scope", "pt", "oos_pt_4", "Quero abrir uma disputa por uma cobrança"),
    ("out_of_scope", "pt", "oos_pt_5", "Posso aumentar o limite do meu cartão?"),
    ("out_of_scope", "pt", "oos_pt_6", "Como eu troco meu número de telefone cadastrado?"),
    # --- requires_escalation ---
    ("requires_escalation", "es", "esc_es_1", "No reconozco un cargo en mi cuenta, creo que es fraude"),
    ("requires_escalation", "es", "esc_es_2", "Me robaron la tarjeta y ya hicieron compras"),
    ("requires_escalation", "es", "esc_es_3", "Alguien clonó mi tarjeta de crédito"),
    ("requires_escalation", "es", "esc_es_4", "Quiero poner una denuncia por un cobro no autorizado"),
    ("requires_escalation", "es", "esc_es_5", "Hay un movimiento en mi cuenta que yo no hice"),
    ("requires_escalation", "pt", "esc_pt_1", "Não reconheço uma cobrança na minha conta, acho que é fraude"),
    ("requires_escalation", "pt", "esc_pt_2", "Roubaram meu cartão e já fizeram compras"),
    ("requires_escalation", "pt", "esc_pt_3", "Alguém clonou meu cartão de crédito"),
    ("requires_escalation", "pt", "esc_pt_4", "Quero fazer uma denúncia por uma cobrança não autorizada"),
    ("requires_escalation", "pt", "esc_pt_5", "Tem uma movimentação na minha conta que eu não fiz"),
    # --- round 2 (added before the held-out set was written; see EVALUATION.md) ---
    ("balance_inquiry", "es", "bal_es_6", "¿Cuánto dinero me queda en la {account}?"),
    ("balance_inquiry", "es", "bal_es_7", "Consultar saldo de {account}"),
    ("balance_inquiry", "es", "bal_es_8", "Me podrías decir el saldo disponible de mis cuentas"),
    ("balance_inquiry", "pt", "bal_pt_6", "Quanto dinheiro sobrou na {account_pt}?"),
    ("balance_inquiry", "pt", "bal_pt_7", "Consultar saldo da {account_pt}"),
    ("balance_inquiry", "pt", "bal_pt_8", "Pode me informar o saldo disponível das minhas contas"),
    ("transaction_lookup", "es", "txn_es_6", "¿Cuáles fueron mis últimas transacciones con la {account}?"),
    ("transaction_lookup", "es", "txn_es_7", "Quiero ver los retiros y depósitos de este mes"),
    ("transaction_lookup", "es", "txn_es_8", "¿Ya se reflejó la transferencia que hice ayer?"),
    ("transaction_lookup", "pt", "txn_pt_6", "Quais foram minhas últimas transações com o {account_pt}?"),
    ("transaction_lookup", "pt", "txn_pt_7", "Quero ver os saques e depósitos deste mês"),
    ("transaction_lookup", "pt", "txn_pt_8", "A transferência que fiz ontem já aparece?"),
    ("payment_status", "es", "pay_es_5", "¿Cuánto debo de mi {credit_product}?"),
    ("payment_status", "es", "pay_es_6", "¿Tengo alguna cuota vencida del {credit_product}?"),
    ("payment_status", "es", "pay_es_7", "¿Cuándo vence el pago de mi {credit_product}?"),
    ("payment_status", "pt", "pay_pt_5", "Quanto eu devo no {credit_product_pt}?"),
    ("payment_status", "pt", "pay_pt_6", "Tenho alguma parcela vencida do {credit_product_pt}?"),
    ("payment_status", "pt", "pay_pt_7", "Quando vence o pagamento do meu {credit_product_pt}?"),
    ("exchange_rate_inquiry", "es", "fx_es_4", "¿Cuántos pesos me dan por un {currency}?"),
    ("exchange_rate_inquiry", "es", "fx_es_5", "Tipo de cambio de hoy"),
    ("exchange_rate_inquiry", "pt", "fx_pt_4", "Quantos pesos vale um {currency_pt}?"),
    ("exchange_rate_inquiry", "pt", "fx_pt_5", "Câmbio de hoje"),
    ("out_of_scope", "es", "oos_es_7", "Quiero cancelar mi tarjeta de crédito"),
    ("out_of_scope", "es", "oos_es_8", "¿Dónde queda la sucursal más cercana?"),
    ("out_of_scope", "es", "oos_es_9", "Olvidé la clave de la aplicación"),
    ("out_of_scope", "pt", "oos_pt_7", "Quero cancelar meu cartão de crédito"),
    ("out_of_scope", "pt", "oos_pt_8", "Onde fica a agência mais próxima?"),
    ("out_of_scope", "pt", "oos_pt_9", "Esqueci a senha do aplicativo"),
    ("requires_escalation", "es", "esc_es_6", "Me hicieron un cargo que no autoricé"),
    ("requires_escalation", "es", "esc_es_7", "Me sacaron dinero de la cuenta sin permiso"),
    ("requires_escalation", "es", "esc_es_8", "Creo que hackearon mi banca en línea"),
    ("requires_escalation", "pt", "esc_pt_6", "Fizeram uma cobrança que eu não autorizei"),
    ("requires_escalation", "pt", "esc_pt_7", "Tiraram dinheiro da minha conta sem permissão"),
    ("requires_escalation", "pt", "esc_pt_8", "Acho que invadiram meu internet banking"),
]

SLOTS = {
    "account": ["cuenta de ahorros", "cuenta corriente", "tarjeta de débito"],
    "account_pt": ["conta poupança", "conta corrente", "cartão de débito"],
    "credit_product": ["tarjeta de crédito", "préstamo personal", "préstamo hipotecario"],
    "credit_product_pt": ["cartão de crédito", "empréstimo pessoal", "empréstimo imobiliário"],
    "currency": ["dólar", "peso mexicano", "peso colombiano", "peso argentino"],
    "currency_pt": ["dólar", "peso mexicano", "peso colombiano"],
}


def _fill(template: str) -> list[str]:
    placeholders = [p.strip("{}") for p in __import__("re").findall(r"\{[^}]+\}", template)]
    if not placeholders:
        return [template]
    options = [SLOTS[p] for p in placeholders]
    out = []
    for combo in itertools.product(*options):
        text = template
        for p, val in zip(placeholders, combo):
            text = text.replace("{" + p + "}", val)
        out.append(text)
    return out


def build(out_path: str = "eval/test_cases/intent_dataset.csv") -> int:
    rows = []
    for intent, language, template_id, template in TEMPLATES:
        for utterance in _fill(template):
            rows.append({"utterance": utterance, "intent": intent, "language": language, "template_id": template_id})

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["utterance", "intent", "language", "template_id"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    n = build()
    print(f"Wrote {n} labeled utterances to eval/test_cases/intent_dataset.csv")
