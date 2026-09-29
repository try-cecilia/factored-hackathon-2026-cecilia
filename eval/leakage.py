"""Fuga entre el entrenamiento y el held-out: frases iguales o casi iguales del lado equivocado de la evaluación.

La comprobación anterior comparaba `strip().lower()`, así que una diferencia de puntuación, de tildes o de espacios la
esquivaba: `quantos pesos vale um dólar` (held-out) y `Quantos pesos vale um dólar?` (entrenamiento) pasaron. Esta usa
la similitud de n-gramas de 3 caracteres (Jaccard) sobre el texto normalizado (minúsculas, sin tildes ni puntuación):

- **EXCLUDE_AT = 0.90**: la frase es la misma salvo mayúsculas, tildes o puntuación. Se **excluye de la puntuación**, se
  lista en el reporte y no se puede pasar por alto.
- **REVIEW_AT = 0.60**: casi siempre una plantilla de la que la frase del held-out es una versión más corta. No es una
  fuga estricta: se conserva, se lista, y el reporte da el resultado **con y sin** esas frases para que se vea si el
  número depende de ellas.

Los cortes salen de mirar la distribución real (hay un salto claro: una frase en 1.0 y las demás por debajo de 0.7), no
de ajustarlos para que un resultado salga mejor. Una exclusión no cambia el reparto en dev y test: el reparto se calcula
antes, sobre todo el held-out, y solo después se sacan las frases excluidas.

Límite: una similitud de caracteres no ve una paráfrasis con otras palabras, y las frases las escribió el mismo equipo
que las plantillas: eso solo lo resuelve un conjunto escrito por personas ajenas (docs/human_set.md).
"""
from __future__ import annotations

import re
import statistics
import unicodedata

EXCLUDE_AT = 0.90
REVIEW_AT = 0.60
COUNT_THRESHOLDS = (0.5, 0.6, 0.7, 0.9)


def normalize(text: str) -> str:
    s = unicodedata.normalize("NFKD", text.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def grams(text: str, n: int = 3) -> set[str]:
    s = f" {normalize(text)} "
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def similarity(a: str, b: str) -> float:
    ga, gb = grams(a), grams(b)
    return len(ga & gb) / len(ga | gb) if ga | gb else 0.0


def nearest(train_texts: list[str], held_texts: list[str]) -> list[tuple[float, str]]:
    """For each held-out phrase, its highest similarity to any training phrase and which one."""
    train = [(t, grams(t)) for t in train_texts]
    out = []
    for h in held_texts:
        g = grams(h)
        out.append(max(((len(g & x) / len(g | x) if g | x else 0.0, t) for t, x in train), key=lambda p: p[0]))
    return out


def report(train_texts: list[str], held_texts: list[str]) -> dict:
    near = nearest(train_texts, held_texts)
    sims = sorted(s for s, _ in near)
    pairs = sorted(({"heldout": h, "train": t, "similarity": round(s, 3)} for h, (s, t) in zip(held_texts, near) if s >= REVIEW_AT),
                   key=lambda p: -p["similarity"])
    return {"exclude_at": EXCLUDE_AT, "review_at": REVIEW_AT, "n": len(sims), "max": round(sims[-1], 3),
            "p95": round(sims[min(len(sims) - 1, int(0.95 * len(sims)))], 3), "median": round(statistics.median(sims), 3),
            "counts_at_least": {str(t): sum(s >= t for s in sims) for t in COUNT_THRESHOLDS},
            "excluded": [p for p in pairs if p["similarity"] >= EXCLUDE_AT],
            "review": [p for p in pairs if REVIEW_AT <= p["similarity"] < EXCLUDE_AT]}


def excluded_utterances(rep: dict) -> set[str]:
    return {p["heldout"] for p in rep["excluded"]}


def review_utterances(rep: dict) -> set[str]:
    return {p["heldout"] for p in rep["review"]} | excluded_utterances(rep)
