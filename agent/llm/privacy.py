"""What the customer types, masked before it leaves for an external model.

The challenge rule: no private customer records, credentials or restricted
data in external model requests. The orchestrator already keeps records out
of the model's context; this covers the customer's own words. Any run of 8+
digits (card, account, CLABE, CBU, national ID, phone) becomes `[···1234]`,
keeping the last 4 digits so "my card ending 1234" still resolves to a
product. Emails become `[email]`. Dates are left alone because the model
needs them for date-range questions; amounts are never a tool argument, and
only those with 8+ digits get masked.
"""
from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_DATE = re.compile(r"\b(?:\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2}[-./]\d{2,4})\b")
_LONG_NUMBER = re.compile(r"(?<![\w@])\d(?:[ .-]?\d){7,}(?![\w@])")
_NON_DIGIT = re.compile(r"\D")
_HOLD = ""  # private-use char: breaks digit runs while dates are set aside


def _mask(match: re.Match) -> str:
    return f"[···{_NON_DIGIT.sub('', match.group())[-4:]}]"


def redact(text: str) -> str:
    text = _EMAIL.sub("[email]", text)
    dates = _DATE.findall(text)
    text = _LONG_NUMBER.sub(_mask, _DATE.sub(_HOLD, text))
    restored = iter(dates)
    return re.sub(_HOLD, lambda _: next(restored), text)
