"""What the customer types, masked before it leaves for an external model.

The challenge rule: no private customer records, credentials or restricted
data in external model requests. The orchestrator never adds a record to
the model's context; this masks the identifiers the customer types.

Everything that inspects customer text looks at `normalize(text)` first:
fullwidth characters become ASCII, every Unicode dash becomes "-", and
invisible format and control characters are dropped. So "PRD–FIX0006",
"ＰＲＤ-FIX0006" and "5000–000–0004" are the same as their plain forms.

`redact` (for the model):
- internal ids (PRD-, CLI-, TXN-, SUC-), even glued to other words or with
  "_" or a space as separator: the customer's own products become their
  alias (P1, P2...), anything else becomes `[id]`;
- Mexican CURP and RFC codes: `[id]`;
- any run of 8+ digits outside a date, separators allowed (card, account,
  CLABE, CBU, national ID, CUIL, phone): `[···1234]`, keeping the last 4
  digits so "my card ending 1234" still resolves to a product;
- emails: `[email]`.
Dates are kept because the model needs them for date-range questions.
Amounts are never a tool argument; only those with 8+ digits get masked.
Names, addresses, 7-digit IDs and amounts typed in free text are not
detected (LIMITATIONS.md).

`mask_card_numbers` (for tickets read by the bank's own agents) masks only
card-length numbers, so an agent still reads "me cobraron 15.000.000".
"""
from __future__ import annotations

import re
import unicodedata

_DASHES = {ord(c): "-" for c in "‐‑‒–—―−﹘﹣－"}
_FULLWIDTH = {cp: cp - 0xFEE0 for cp in range(0xFF01, 0xFF5F)}


def normalize(text: str) -> str:
    """Fullwidth to ASCII, dashes to "-", invisible format/control characters dropped (newlines and tabs kept)."""
    text = text.translate(_FULLWIDTH).translate(_DASHES)
    return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in ("Cf", "Cc"))


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# With a separator any body counts; glued to the prefix it needs a digit, so "clientes" or "sucursal" are not ids.
_INTERNAL_ID = re.compile(r"(PRD|CLI|TXN|SUC)(?:[\s_-]{1,2}([A-Z0-9]{4,})|(?=[A-Z0-9]{4,})([A-Z0-9]*\d[A-Z0-9]*))", re.IGNORECASE)
_CURP = re.compile(r"[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d", re.IGNORECASE)
_RFC = re.compile(r"(?<![A-Z0-9])[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}(?![A-Z0-9])", re.IGNORECASE)
_DATE = re.compile(r"(?<!\d)(?:\d{4}\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}|\d{1,2}\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{2,4})(?!\d)")
_SEP = r"(?:,(?!\s)|[\s._*·/-]){0,5}"  # a comma followed by a space separates list items, not digit groups
_LONG_NUMBER = re.compile(rf"(?<!\d)\d(?:{_SEP}\d){{7,}}(?!\d)")
_CARD_NUMBER = re.compile(rf"(?<!\d)\d(?:{_SEP}\d){{12,18}}(?!\d)")
_NON_DIGIT = re.compile(r"\D")


def internal_ids(text: str) -> list[list[str]]:
    """Each internal-id mention in normalized text, as canonical candidates (PRD-FIX0006...), longest first:
    a body glued to trailing letters ("PRD-FIX0006por") also yields its shorter prefixes."""
    out = []
    for m in _INTERNAL_ID.finditer(text):
        prefix, body = m.group(1).upper(), (m.group(2) or m.group(3)).upper()
        out.append([f"{prefix}-{body[:n]}" for n in range(len(body), 3, -1)])
    return out


def _mask_last4(match: re.Match) -> str:
    return f"[···{_NON_DIGIT.sub('', match.group())[-4:]}]"


def _outside_dates(text: str, number: re.Pattern) -> str:
    out, pos = [], 0
    for d in _DATE.finditer(text):
        out += [number.sub(_mask_last4, text[pos:d.start()]), d.group()]
        pos = d.end()
    return "".join(out + [number.sub(_mask_last4, text[pos:])])


def redact(text: str, own_ids: dict[str, str] | None = None) -> str:
    """own_ids: the session customer's product ids -> alias."""
    aliases = {k.upper(): v for k, v in (own_ids or {}).items()}
    text = _EMAIL.sub("[email]", normalize(text))
    # Ids become placeholders first (a control char cannot survive normalize), so an alias like P1 never
    # merges with digits that follow it; they are filled in after the numbers are masked.
    replacements: list[str] = []

    def hold(m: re.Match) -> str:
        candidates = internal_ids(m.group())[0]
        replacements.append(next((aliases[c] for c in candidates if c in aliases), "[id]"))
        return f"\x00{len(replacements) - 1:x}\x00".translate(str.maketrans("0123456789abcdef", "ghijklmnopqrstuv"))

    text = _INTERNAL_ID.sub(hold, text)
    text = _RFC.sub("[id]", _CURP.sub("[id]", text))
    text = _outside_dates(text, _LONG_NUMBER)
    return re.sub("\x00([g-v]+)\x00", lambda m: replacements[int(m.group(1).translate(str.maketrans("ghijklmnopqrstuv", "0123456789abcdef")), 16)], text)


def mask_card_numbers(text: str) -> str:
    return _outside_dates(normalize(text), _CARD_NUMBER)
