"""Numeric grounding check — the deterministic half of "Verify".

Every number the LLM writes in its final answer must match a number that a
verified tool result (or the customer's own message) actually contains.
Anything else — a sum the model computed, a hallucinated balance, a wrong
day count — fails the check, and the orchestrator replaces the answer with
a deterministic rendering of the verified facts instead.

Number formats vary by locale ("2,455.81", "2.455,81", "$ 2 455,81"), so
each token is read under both decimal conventions and accepted if either
reading matches a grounded value within max(0.01, 0.5%).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{1,2}:\d{2}\b")
_LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s+")
_NUM = re.compile(r"(?<![\w])\d[\d.,\s]*\d(?![\w])|(?<![\w.,])\d(?![\w])")


@dataclass
class GroundingResult:
    numbers_checked: int
    ungrounded: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.ungrounded


def _readings(token: str) -> set[float]:
    t = token.replace(" ", "").replace(" ", "")
    out: set[float] = set()
    for dec, thou in ((".", ","), (",", ".")):
        s = t.replace(thou, "")
        if s.count(dec) > 1:
            continue
        s = s.replace(dec, ".")
        try:
            out.add(float(s))
        except ValueError:
            pass
    return out


def _collect(obj: Any, acc: set[float]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float, Decimal)):
        acc.add(float(obj))
    elif isinstance(obj, (date, datetime)):
        acc.update({float(obj.year), float(obj.month), float(obj.day)})
    elif isinstance(obj, str):
        for m in re.findall(r"\d+(?:[.,]\d+)?", obj):
            acc.update(_readings(m))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect(v, acc)
    elif isinstance(obj, (list, tuple)):
        acc.add(float(len(obj)))
        for v in obj:
            _collect(v, acc)


def grounded_values(results: Iterable[Any], extra_texts: Iterable[str] = ()) -> set[float]:
    acc: set[float] = set()
    for r in results:
        _collect(r, acc)
    for t in extra_texts:
        _collect(t, acc)
    return acc


def _matches(x: float, values: set[float]) -> bool:
    return any(abs(x - v) <= max(0.01, 0.005 * abs(v)) for v in values)


def check(answer: str, results: Iterable[Any], extra_texts: Iterable[str] = ()) -> GroundingResult:
    values = grounded_values(list(results), extra_texts)
    text = _LIST_MARKER.sub(" ", _DATE.sub(" ", answer))
    tokens = [t.strip() for t in _NUM.findall(text) if t.strip()]
    ungrounded = [t for t in tokens if not any(_matches(x, values) for x in _readings(t))]
    return GroundingResult(len(tokens), ungrounded)
