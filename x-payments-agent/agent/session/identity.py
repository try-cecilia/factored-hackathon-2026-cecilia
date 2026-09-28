"""Demo identity provider — the "trusted test session service" the brief asks for.

The brief: "a national ID or customer number alone does not prove
identity." So a session requires customer_id + a second factor. In a real
bank that factor comes from the bank's IdP (app login, IVR PIN, OTP). Here
it's a *test credential*: a 6-digit PIN derived as HMAC-SHA256(secret,
customer_id), where the secret (DEMO_IDP_SECRET) lives only on the server.
Demo operators obtain a customer's test PIN from the admin-key-protected
endpoint or `python -m agent.session.identity CLI-...`; customers of this
prototype never need it, and it proves nothing outside this sandbox.

Also enforced here, not in the conversation layer:
- constant-time PIN comparison;
- lockout after repeated failures per customer (brute-force defense);
- unknown customers and Closed accounts can't open sessions.
Fails closed: without DEMO_IDP_SECRET, no session can be issued at all.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import threading
import time
from dataclasses import dataclass

from agent.session.auth import Session, SessionStore, default_store
from agent.tools.db import get_connection

MAX_FAILURES = 5
LOCKOUT_WINDOW_S = 15 * 60


class AuthError(Exception):
    """Generic on purpose: callers must not learn which check failed."""


class IdentityUnavailable(AuthError):
    pass


class LockedOut(AuthError):
    pass


def _secret() -> bytes:
    secret = os.environ.get("DEMO_IDP_SECRET")
    if not secret:
        raise IdentityUnavailable("DEMO_IDP_SECRET is not configured; session issuing is disabled")
    return secret.encode()


def derive_test_pin(customer_id: str) -> str:
    digest = hmac.new(_secret(), customer_id.encode(), hashlib.sha256).hexdigest()
    return f"{int(digest, 16) % 1_000_000:06d}"


@dataclass(frozen=True)
class CustomerRecord:
    customer_id: str
    segment: str
    country: str
    customer_status: str


class IdentityService:
    def __init__(self, store: SessionStore | None = None):
        self.store = default_store if store is None else store  # an empty store is falsy (__len__)
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent_failures(self, customer_id: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(customer_id, []) if now - t < LOCKOUT_WINDOW_S]
        self._failures[customer_id] = recent
        return recent

    def _lookup(self, customer_id: str) -> CustomerRecord | None:
        row = get_connection().execute(
            "SELECT customer_id, segment, country, customer_status FROM customers WHERE customer_id = ?", [customer_id]
        ).fetchone()
        return CustomerRecord(*row) if row else None

    def login(self, customer_id: str, pin: str) -> Session:
        now = time.time()
        with self._lock:
            if len(self._recent_failures(customer_id, now)) >= MAX_FAILURES:
                raise LockedOut("too many failed attempts; try again later")
        expected = derive_test_pin(customer_id)
        record = self._lookup(customer_id)
        ok = hmac.compare_digest(expected, str(pin)) and record is not None and record.customer_status != "Closed"
        if not ok:
            with self._lock:
                self._failures.setdefault(customer_id, []).append(now)
            raise AuthError("invalid credentials")
        with self._lock:
            self._failures.pop(customer_id, None)
        return self.store.issue(customer_id, {"segment": record.segment, "country": record.country,
                                              "customer_status": record.customer_status})


default_identity = IdentityService()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    for cid in sys.argv[1:]:
        print(cid, derive_test_pin(cid))
