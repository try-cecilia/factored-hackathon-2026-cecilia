"""Comparing secrets (admin, operator and metrics keys, PINs) without leaking where they differ.

hmac.compare_digest is constant-time but raises TypeError on a str with non-ASCII characters, so a header or a PIN such as
"١٢٣٤٥٦" (which a Unicode-aware \\d accepts) made the request a 500 instead of a refusal. Compared as UTF-8 bytes, it is a
plain "no".
"""
from __future__ import annotations

import hmac


def constant_time_equals(presented: str | None, expected: str | None) -> bool:
    """Whether two secrets are equal, in time that does not depend on where they differ. False if either is empty."""
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))
