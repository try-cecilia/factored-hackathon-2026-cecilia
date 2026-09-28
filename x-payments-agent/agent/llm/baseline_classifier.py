"""Keyword-rule intent classifier — the baseline the learned classifier must beat.

Escalation uses the shared lexicon (agent/policy/signals.py) so baseline and
proposed system apply identical safety rules; the rest are hand-written
routing keywords. These rules were written from the *training* templates
only and frozen before the held-out set existed (see EVALUATION.md).
"""
from __future__ import annotations

import re

from agent.policy.signals import contains_escalation_signal, normalize

RULES: list[tuple[str, list[str]]] = [
    ("out_of_scope", [r"\bbloque", r"\bprestamo nuevo", r"\bemprestimo novo", r"\bnovo emprestimo", r"\bsolicitar (un|um) ",
                      r"\brequisitos\b", r"\bdisputa", r"\baumentar (el|o) limite", r"\b(numero de )?telefono\b",
                      r"\btelefone\b", r"\bperdi\b"]),
    ("payment_status", [r"\bal dia\b", r"\bem dia\b", r"\batrasad", r"\batraso\b", r"\bmora\b", r"\bcredito (disponible|ainda|disponivel)",
                        r"\bvence\b", r"\bproximo (pago|pagamento)\b", r"\bdias de (mora|atraso)\b"]),
    ("exchange_rate_inquiry", [r"\btipo de cambio\b", r"\bcotiza", r"\bcotacao\b", r"\bcambio\b", r"\bdolar\b"]),
    ("transaction_lookup", [r"\bmovimient", r"\bmovimenta", r"\btransac", r"\bhistorial\b", r"\bhistorico\b", r"\bcompras\b", r"\bgastos\b"]),
    ("balance_inquiry", [r"\bsaldo\b", r"\bcuanto tengo\b", r"\bquanto (eu )?tenho\b", r"\bdisponible\b", r"\bdisponivel\b"]),
]
_COMPILED = [(label, [re.compile(p) for p in pats]) for label, pats in RULES]


def classify(utterance: str) -> str:
    if contains_escalation_signal(utterance):
        return "requires_escalation"
    norm = normalize(utterance)
    for label, patterns in _COMPILED:
        if any(p.search(norm) for p in patterns):
            return label
    return "out_of_scope"  # safest default: abstain rather than guess an in-scope action
