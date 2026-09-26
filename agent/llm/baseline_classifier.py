"""Deterministic keyword-rule baseline for intent classification.

This is the baseline the learned component (agent/llm/intent_classifier.py)
must beat to justify its own existence, per "evaluate at least one learned
component against an appropriate baseline."
"""
from __future__ import annotations

import re

RULES: list[tuple[str, list[str]]] = [
    ("requires_escalation", [
        r"\bfraud", r"no reconozco", r"não reconheço", r"robaron", r"roubaram",
        r"clonaron", r"clonou", r"denuncia", r"denúncia", r"no hice", r"não fiz",
    ]),
    ("payment_status", [
        r"al d[ií]a", r"em dia", r"atrasad", r"atraso", r"mora\b", r"cr[ée]dito disponible",
        r"cr[ée]dito ainda", r"vence", r"pr[óo]ximo pago", r"pr[óo]ximo pagamento",
    ]),
    ("exchange_rate_inquiry", [
        r"tipo de cambio", r"cotiza[cç][aã]o", r"cotización", r"c[âa]mbio", r"d[óo]lar",
    ]),
    ("transaction_lookup", [
        r"movimientos", r"movimenta[cç][õo]es", r"transacciones", r"transa[cç][õo]es",
        r"historial", r"hist[óo]rico", r"compras", r"gastos", r"gastos",
    ]),
    ("balance_inquiry", [
        r"saldo", r"cu[áa]nto tengo", r"quanto (eu )?tenho", r"dinero disponible", r"dispon[ií]vel",
    ]),
    ("out_of_scope", [
        r"bloquear", r"bloquear meu", r"pr[ée]stamo nuevo", r"empr[ée]stimo novo",
        r"requisitos", r"requisitos para", r"disputa", r"cobro\b", r"cobran[çc]a",
        r"aumentar el l[ií]mite", r"aumentar o limite", r"n[úu]mero de tel[ée]fono", r"telefone cadastrado",
    ]),
]


def classify(utterance: str) -> str:
    lowered = utterance.lower()
    for label, patterns in RULES:
        if any(re.search(p, lowered) for p in patterns):
            return label
    return "out_of_scope"  # safest default: abstain rather than guess an in-scope action
