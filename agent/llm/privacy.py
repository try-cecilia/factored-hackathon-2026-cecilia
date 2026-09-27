"""What the customer types, masked before it leaves for an external model.

The challenge rule: no private customer records, credentials or restricted
data in external model requests. The orchestrator never adds a record to
the model's context; this masks the identifiers the customer types:
- internal ids (PRD-, CLI-, TXN-, SUC-): the customer's own products become
  their alias (P1, P2...), anything else becomes `[id]`;
- Mexican CURP and RFC codes: `[id]`;
- any run of 8+ digits, separators allowed (card, account, CLABE, CBU,
  national ID, CUIL, phone): `[···1234]`, keeping the last 4 digits so "my
  card ending 1234" still resolves to a product;
- emails: `[email]`.
Dates are left alone because the model needs them for date-range
questions. Amounts are never a tool argument; only those with 8+ digits get
masked. Names and addresses typed in free text are not detected
(LIMITATIONS.md).

Tickets for the bank's own agents keep more: `mask_card_numbers` masks
only card-length numbers, so an agent still reads "me cobraron 15.000.000".
"""
from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_INTERNAL_ID = re.compile(r"\b(?:PRD|CLI|TXN|SUC)-[A-Za-z0-9]+\b", re.IGNORECASE)
_CURP_RFC = re.compile(r"\b(?:[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d|[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})\b", re.IGNORECASE)
_SEP = r"[\s./-]{0,3}"  # \s covers non-breaking and other Unicode spaces
_DATE = rf"\d{{4}}\s*[-./]\s*\d{{1,2}}\s*[-./]\s*\d{{1,2}}|\d{{1,2}}\s*[-./]\s*\d{{1,2}}\s*[-./]\s*\d{{2,4}}"
_DATE_OR_NUMBER = re.compile(rf"(?<!\d)(?:(?P<date>{_DATE})|(?P<number>\d(?:{_SEP}\d){{7,}}))(?!\d)")
_CARD_NUMBER = re.compile(rf"(?<!\d)\d(?:{_SEP}\d){{12,18}}(?!\d)")
_NON_DIGIT = re.compile(r"\D")


def _last4(match: re.Match) -> str:
    return f"[···{_NON_DIGIT.sub('', match.group())[-4:]}]"


def redact(text: str, own_ids: dict[str, str] | None = None) -> str:
    """own_ids: the session customer's product ids (upper case) -> alias."""
    aliases = {k.upper(): v for k, v in (own_ids or {}).items()}
    text = _EMAIL.sub("[email]", text)
    text = _INTERNAL_ID.sub(lambda m: aliases.get(m.group().upper(), "[id]"), text)
    text = _CURP_RFC.sub("[id]", text)
    return _DATE_OR_NUMBER.sub(lambda m: m.group() if m.group("date") else _last4(m), text)


def mask_card_numbers(text: str) -> str:
    return _CARD_NUMBER.sub(_last4, text)
