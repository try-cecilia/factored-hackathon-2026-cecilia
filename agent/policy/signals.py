"""Single source of truth for deterministic text signals.

Used by the pre-LLM safety guard (agent/core/orchestrator.py), the ticket
priority (agent/policy/escalation.py) and the keyword baseline
(agent/llm/baseline_classifier.py) — previously three divergent keyword
lists, one of which missed "un movimiento que yo no hice", a sentence from
our own escalation training set.

Matching is accent- and case-insensitive (NFKD-stripped), so "autoricé",
"autorice" and "AUTORICE" all hit the same rule. The guard is deliberately
high-recall: "no es fraude" still escalates. A false escalation costs a
human a minute; a missed one costs the customer money.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip()


# category -> patterns over normalize(text)
ESCALATION_PATTERNS: dict[str, list[str]] = {
    "fraud": [
        r"\bfraud\w*", r"\bestaf\w*", r"\bgolpe\b", r"\bphishing\b", r"\bsuplant\w*",
        r"\bno (lo |la |los |las )?reconozco\b", r"\bdesconozco\b", r"\bno reconocid[oa]s?\b",
        r"\bnao (o |a |os |as )?reconheco\b", r"\bdesconheco\b", r"\bnao reconhecid[oa]s?\b",
        # "no hice el pago" means "I haven't paid yet" (a payment-status question),
        # not "I didn't make that transaction" — excluded for hice/realice/fiz/realizei.
        r"\b(yo )?no (lo |la )?(hice|realice)\b(?! (el|mi|un|ningun) pago)",
        r"\b(yo )?no (lo |la )?(autorice|solicite|pedi)\b",
        r"\b(eu )?nao (o |a )?(fiz|realizei)\b(?! (o|meu|um|nenhum) pagamento)",
        r"\b(eu )?nao (o |a )?(autorizei|solicitei|pedi)\b",
        r"\bno autorizad[oa]s?\b", r"\bnao autorizad[oa]s?\b",
        r"\bsin (mi )?(permiso|autorizacion|consentimiento)\b", r"\bsem (minha )?(permissao|autorizacao|consentimento)\b",
        r"\balguien (uso|usaron|entro|saco|hizo)\b", r"\balguem (usou|entrou|sacou|fez)\b",
    ],
    "theft": [
        r"\brob(o|aron|ada|ado|aran)\b", r"\bhurt\w*", r"\brouba\w*", r"\broubo\b", r"\bfurt(o|aram|ado|ada)\b",
        r"\bclon\w*", r"\bextravi\w*.*\b(robad|clonad)",
    ],
    "account_takeover": [
        r"\bhacke\w*", r"\bjackea\w*", r"\binvadi\w*", r"\bme (sacaron|vaciaron)\b", r"\besvaziaram\b",
        r"\bcambiaron (mi|la) (clave|contrasena)\b", r"\bmudaram (minha|a) senha\b",
    ],
    "legal_or_regulator": [
        r"\bdenunci\w*", r"\bdemandar\w*", r"\bdemanda judicial\b", r"\babogad\w*", r"\badvogad\w*",
        r"\bprocon\b", r"\bcondusef\b", r"\bsuperintendencia\b", r"\bbcra\b", r"\bdefensor del consumidor\b",
    ],
    "safety": [r"\bamenaz\w*", r"\bameac\w*", r"\bsuicid\w*", r"\bme voy a matar\b", r"\bvou me matar\b"],
}
_COMPILED = {cat: [re.compile(p) for p in pats] for cat, pats in ESCALATION_PATTERNS.items()}
PRIORITY_BY_CATEGORY = {"fraud": "Critical", "theft": "Critical", "account_takeover": "Critical",
                        "safety": "Critical", "legal_or_regulator": "High"}


def escalation_categories(text: str) -> list[str]:
    norm = normalize(text)
    return [cat for cat, pats in _COMPILED.items() if any(p.search(norm) for p in pats)]


def contains_escalation_signal(text: str) -> bool:
    return bool(escalation_categories(text))


# --- language detection (es / pt) ---------------------------------------
# Scored on *un-normalized* text for diacritics that only Portuguese uses
# (ã õ ç ê ô), then on function words that differ between the languages.
_PT_CHARS = re.compile(r"[ãõçêô]")
_ES_CHARS = re.compile(r"[¿¡ñ]")
_PT_WORDS = {
    "nao", "voce", "voces", "meu", "minha", "meus", "minhas", "obrigado", "obrigada", "qual", "quero",
    "preciso", "tenho", "estou", "fiz", "fazer", "ola", "oi", "bom", "boa", "hoje", "ontem", "dinheiro",
    "pagamento", "emprestimo", "cartao", "extrato", "fatura", "cobranca", "movimentacoes", "tambem", "entao",
    "isso", "agora", "sim", "com", "em", "no", "na", "do", "da", "o", "a", "e", "um", "uma", "pra", "para",
    "conta", "saldo", "atrasado", "cotacao", "cambio", "roubaram", "alguem", "quanto", "posso", "gostaria",
}
_ES_WORDS = {
    "el", "la", "los", "las", "mi", "mis", "cual", "que", "cuanto", "cuanta", "quiero", "necesito", "tengo",
    "hice", "prestamo", "tarjeta", "pago", "cuenta", "hoy", "ayer", "dinero", "gracias", "usted", "estoy",
    "buenos", "buenas", "hola", "movimientos", "si", "con", "en", "del", "al", "un", "una", "por", "para",
    "saldo", "atrasado", "cotizacion", "cambio", "robaron", "alguien", "puedo", "quisiera", "y", "es", "de",
}
# Words present in both sets carry no signal.
_PT_ONLY = _PT_WORDS - _ES_WORDS
_ES_ONLY = _ES_WORDS - _PT_WORDS


@dataclass(frozen=True)
class LanguageGuess:
    language: str  # es | pt
    pt_score: int
    es_score: int

    @property
    def mixed(self) -> bool:
        return self.pt_score > 0 and self.es_score > 0


def detect_language(text: str, default: str = "es") -> LanguageGuess:
    lowered = text.lower()
    tokens = re.findall(r"[a-z]+", normalize(text))
    pt = 2 * len(_PT_CHARS.findall(lowered)) + sum(t in _PT_ONLY for t in tokens) + (2 if re.search(r"(^|\s)é(\s|$|\?)", lowered) else 0)
    es = 2 * len(_ES_CHARS.findall(lowered)) + sum(t in _ES_ONLY for t in tokens)
    if pt == es:
        return LanguageGuess(default, pt, es)
    return LanguageGuess("pt" if pt > es else "es", pt, es)
