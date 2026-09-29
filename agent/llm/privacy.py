"""What the customer types, masked before it leaves for an external model.

The challenge rule: no private customer records, credentials or restricted
data in external model requests. The orchestrator never adds a record to
the model's context; this masks the identifiers the customer types.

Everything that inspects customer text looks at `normalize(text)` first:
fullwidth, mathematical and small-form characters become ASCII, Cyrillic and
Greek look-alikes of Latin letters become Latin, digits of any script (and
superscripts) become 0-9, every Unicode dash becomes "-", and invisible
format and control characters are dropped.

`redact` (for the model):
- internal ids (PRD-, CLI-, TXN-, SUC-): the customer's own products become
  their alias (P1, P2...), anything else becomes `[id]`. The standard form
  (PRD-XXXX) is caught with any body. With other separators ("PRD - FIX0006"),
  split in two ("PRD-FIX 0006") or glued after a capitalized prefix
  ("PRDFIX0006"), the body must carry a digit, so "clientes", "sucursal123"
  or "el cli 2024" stay as written;
- Mexican CURP and RFC codes, with or without separators: `[id]`;
- any run of 8+ digits, and a Luhn-valid card however it is split:
  `[···1234]`, keeping the last 4 digits so "my card ending 1234" still
  resolves to a product (a CVV typed after the card never shifts them);
- emails: `[email]`.
Dates, months, year periods and time ranges are kept: the model needs them.
They are validated (a phone written in pairs is not a date). Amounts under
8 digits are kept. Names, addresses and IDs under 8 digits typed in free
text are not detected (LIMITATIONS.md). An amount range written as one chain
of digits ("1500-2000") reads as one long number and is masked: the error
is on the side of hiding, never of leaking.

`mask_card_numbers` (for tickets read by the bank's own agents) masks only
cards, so an agent still reads "me cobraron 15.000.000".
"""
from __future__ import annotations

import re
import unicodedata

_LOOKALIKES = zip("АВСЕНІЈКМОРЅТХҮасеіјорѕхуΑΒΕΖΗΙΚΜΝΟΡΤΥΧοİK",
                  "ABCEHIJKMOPSTXYaceijopsxyABEZHIKMNOPTYXoIK", strict=True)
_CHAR_MAP = ({ord(c): "-" for c in "‐‑‒–—―⁃−˗⸺⸻﹘﹣－"}
             | {cp: cp - 0xFEE0 for cp in range(0xFF01, 0xFF5F)}  # fullwidth ASCII
             | {ord(k): v for k, v in _LOOKALIKES})


def normalize(text: str) -> str:
    out = []
    for ch in text.translate(_CHAR_MAP):
        if ch in "\n\t" or ch.isascii() and ch.isprintable():
            out.append(ch)
        elif unicodedata.category(ch) in ("Cf", "Cc"):
            continue  # zero-width spaces, BOM, NUL...
        elif unicodedata.digit(ch, None) is not None:
            out.append(str(unicodedata.digit(ch)))  # Arabic-Indic, superscript, circled...
        elif 0xFE50 <= ord(ch) <= 0xFE6F or 0x1D400 <= ord(ch) <= 0x1D7FF:
            out.append(unicodedata.normalize("NFKC", ch))  # small forms (﹫), mathematical letters (𝐏)
        else:
            out.append(ch)
    return "".join(out)


_EMAIL = re.compile(r"[\w.+'-]{1,64}\s?@\s?[\w-]{1,63}(?:\.[\w-]{1,63})+")
_INTERNAL_ID = re.compile(
    r"(?i:(?P<p1>PRD|CLI|TXN|SUC)-(?P<b1>[A-Z0-9]{4,32}))"                                   # standard: any body
    r"|(?i:(?P<p2>PRD|CLI|TXN|SUC)[\W_]{1,3}(?P<b2>(?-i:[A-Z]{1,4})[\W_]{1,3}(?=\d)[A-Z0-9]{1,32}"  # split in two
    r"|[A-Z]{0,12}\d[A-Z0-9]{0,31}))"                                                           # other separators
    r"|(?P<p3>PRD|CLI|TXN|SUC)(?i:(?=[A-Z0-9]{0,31}\d)(?P<b3>[A-Z0-9]{4,32}))")                 # glued
_ID_AT = re.compile(rf"(?=(?:{_INTERNAL_ID.pattern}))")  # every position, so overlapping mentions are found too
_CURP = re.compile(r"[A-Z]{4}[\s-]?\d{6}[\s-]?[HM][A-Z]{5}[A-Z0-9]\d", re.IGNORECASE)
_RFC_LABELED = re.compile(r"(RFC[\s:.]*)[A-ZÑ&]{3,4}[\s-]?\d{6}[\s-]?[A-Z0-9]{3}(?![A-Z0-9])", re.IGNORECASE)
_RFC = re.compile(r"(?<![A-Z0-9])[A-ZÑ&]{3,4}-?\d{6}-?[A-Z0-9]{3}(?![A-Z0-9])", re.IGNORECASE)

_D, _M, _Y4 = r"(?:0?[1-9]|[12]\d|3[01])", r"(?:0?[1-9]|1[0-2])", r"(?:19|20)\d{2}"
_S, _H = r"\s*[-./]\s*", r"(?:[01]?\d|2[0-3])[.:][0-5]\d"
_WHEN = (rf"(?:{_Y4}{_S}{_M}{_S}{_D}|{_D}{_S}{_M}{_S}(?:{_Y4}|\d{{2}})|{_D}\s{_M}\s{_Y4}"  # dates
         rf"|{_M}\s*[-/]\s*{_Y4}|{_M}/\d{{2}}|{_H})")                                        # months, times
_PROTECTED = re.compile(  # a date, or a range of them; one inside a longer chain of digits is not a date
    rf"(?<!\d)(?<!\d[-./])(?:{_Y4}\s*[-/]\s*{_Y4}|{_WHEN}(?:\s*-\s*{_WHEN})?)(?!\d)(?![-./]\d)")
_SEP = r"(?:,(?!\s)|[\s._*·/-]){0,5}"  # a comma followed by a space separates list items, not digit groups
_LONG_NUMBER = re.compile(rf"(?<!\d)\d(?:{_SEP}\d){{7,}}(?!\d)")
_CARD_LENGTH = re.compile(rf"(?<!\d)\d(?:{_SEP}\d){{12,18}}(?!\d)")
_SPLIT_CARD = re.compile(r"(?<!\d)\d(?:[\W_]{0,8}\d){12,18}(?!\d)")  # any separators: masked only if Luhn-valid
_DIGITS = re.compile(r"\d+")
_TO_LETTERS, _FROM_LETTERS = str.maketrans("0123456789", "ghijklmnop"), str.maketrans("ghijklmnop", "0123456789")


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def _card(number: str) -> str | None:
    """The card's digits if `number` is a Luhn-valid card, alone or followed by a 3-4 digit CVV."""
    groups = _DIGITS.findall(number)
    if len(groups) > 1 and len(groups[-1]) in (3, 4) and len(card := "".join(groups[:-1])) in (15, 16) and _luhn(card):
        return card
    digits = "".join(groups)
    return digits if 13 <= len(digits) <= 19 and _luhn(digits) else None


def _masked(number: str) -> str:
    return f"[···{(_card(number) or ''.join(_DIGITS.findall(number)))[-4:]}]"


def _mask_numbers(text: str, general: re.Pattern) -> str:
    def gap(segment: str) -> str:
        segment = _SPLIT_CARD.sub(lambda m: _masked(m[0]) if _card(m[0]) else m[0], segment)
        return general.sub(lambda m: _masked(m[0]), segment)

    out, pos = [], 0
    for p in _PROTECTED.finditer(text):
        out += [gap(text[pos:p.start()]), p[0]]
        pos = p.end()
    return "".join(out + [gap(text[pos:])])


def _candidates(m: re.Match) -> list[str] | None:
    """Canonical ids for one mention, longest first: letters glued after the id ("PRD-FIX0006por") are trimmed
    one at a time, digits never are. None if a mention written loosely is too short to be an id ("Suc 1234")."""
    prefix = (m["p1"] or m["p2"] or m["p3"]).upper()
    body = re.sub(r"[\W_]", "", m["b1"] or m["b2"] or m["b3"]).upper()
    if m["p2"] and len(body) < 6:
        return None
    out = [body]
    while len(body) > 4 and body[-1].isalpha():
        body = body[:-1]
        out.append(body)
    return [f"{prefix}-{b}" for b in out]


def internal_ids(text: str) -> list[list[str]]:
    """Every internal-id mention in normalized text, overlapping ones included ("CLI-PRDFIX0006" also yields
    PRD-FIX0006), each as its canonical candidates."""
    return [c for c in map(_candidates, _ID_AT.finditer(text)) if c]


def redact(text: str, own_ids: dict[str, str] | None = None) -> str:
    """own_ids: the session customer's product ids -> alias."""
    aliases = {k.upper(): v for k, v in (own_ids or {}).items()}
    held: list[str] = []

    def hold(m: re.Match) -> str:
        found = _candidates(m)
        if found is None:
            return m[0]
        held.append(next((aliases[c] for c in found if c in aliases), "[id]"))
        return "\x00" + str(len(held) - 1).translate(_TO_LETTERS) + "\x00"

    # Ids become placeholders first (a control char cannot survive normalize), so an alias like P1 never
    # merges with digits that follow it; they are filled in after the numbers are masked.
    text = _INTERNAL_ID.sub(hold, _EMAIL.sub("[email]", normalize(text)))
    text = _RFC.sub("[id]", _RFC_LABELED.sub(r"\1[id]", _CURP.sub("[id]", text)))
    text = _mask_numbers(text, _LONG_NUMBER)
    return re.sub("\x00([g-p]+)\x00", lambda m: held[int(m[1].translate(_FROM_LETTERS))], text)


def mask_card_numbers(text: str) -> str:
    return _mask_numbers(normalize(text), _CARD_LENGTH)
