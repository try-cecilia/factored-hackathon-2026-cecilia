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
- lockout after repeated failures per customer (brute-force defense), where the attempt is reserved under the lock before the
  PIN is checked, so concurrent logins cannot check more PINs than the limit allows;
- unknown customers and Closed accounts can't open sessions.
Fails closed: without DEMO_IDP_SECRET, no session can be issued at all.
"""
from __future__ import annotations

import hashlib
import hmac
import itertools
import os
import sys
import threading
import time
from dataclasses import dataclass

from agent.session.auth import Session, SessionStore, default_store
from agent.session.secure_compare import constant_time_equals
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


class _Failure(float):
    """A failed attempt: its timestamp (what the lockout window reads) and a number no other failure has (what a success reads
    to clear exactly the failures it began after, however equal two timestamps are)."""

    seq: int

    def __new__(cls, when: float, seq: int) -> "_Failure":
        failure = super().__new__(cls, when)
        failure.seq = seq
        return failure


@dataclass(frozen=True)
class CustomerRecord:
    customer_id: str
    segment: str
    country: str
    customer_status: str


class IdentityService:
    def __init__(self, store: SessionStore | None = None):
        self.store = default_store if store is None else store  # an empty store is falsy (__len__)
        self._failures: dict[str, list[float]] = {}  # per customer: the failed attempts (_Failure: timestamp and number)
        self._failure_seq = itertools.count()  # numbers the failures; used only under the lock
        self._inflight: dict[str, int] = {}  # per customer: attempts that hold a place and have not been resolved yet
        self._lock = threading.Lock()

    def _recent_failures(self, customer_id: str, now: float) -> list[float]:
        recent = [t if isinstance(t, _Failure) else _Failure(t, next(self._failure_seq))  # one set from outside gets its number here
                  for t in self._failures.get(customer_id, []) if now - t < LOCKOUT_WINDOW_S]
        self._failures[customer_id] = recent
        return recent

    def _lookup(self, customer_id: str) -> CustomerRecord | None:
        row = get_connection().execute(
            "SELECT customer_id, segment, country, customer_status FROM customers WHERE customer_id = ?", [customer_id]
        ).fetchone()
        return CustomerRecord(*row) if row else None

    def _reserve(self, customer_id: str) -> tuple[float, frozenset[int]]:
        """Takes one of the account's MAX_FAILURES places, or raises LockedOut. Checking and taking are one step under the
        lock, so the places held by attempts still in the lookup count as failures: concurrent logins cannot pass the check
        together. Only this account's counters are touched, and the lock is not held while the warehouse answers.
        Returns when the attempt began and the numbers of the failures recorded by then: a success clears those and no others."""
        now = time.time()
        with self._lock:
            before = self._recent_failures(customer_id, now)
            if len(before) + self._inflight.get(customer_id, 0) >= MAX_FAILURES:
                raise LockedOut("too many failed attempts; try again later")
            self._inflight[customer_id] = self._inflight.get(customer_id, 0) + 1
            return now, frozenset(failure.seq for failure in before)

    def _resolve(self, customer_id: str, failed_at: float | None, clears: frozenset[int] | None = None) -> None:
        """Gives the reserved place back: as a recorded failure (`failed_at`), as a success that clears the failures numbered in
        `clears` (the ones recorded when it began, never those of attempts that ran beside it, and a failure another success
        already cleared is simply not there), or, with neither, as nothing (the attempt ended in an error that was not a guess)."""
        with self._lock:
            held = self._inflight.get(customer_id, 1) - 1
            if held > 0:
                self._inflight[customer_id] = held
            else:
                self._inflight.pop(customer_id, None)
            if failed_at is not None:
                self._failures.setdefault(customer_id, []).append(_Failure(failed_at, next(self._failure_seq)))
            elif clears is not None:
                left = [f for f in self._failures.get(customer_id, []) if getattr(f, "seq", None) not in clears]
                if left:
                    self._failures[customer_id] = left
                else:
                    self._failures.pop(customer_id, None)

    def login(self, customer_id: str, pin: str) -> Session:
        reserved_at, before = self._reserve(customer_id)
        outcome: tuple[float | None, frozenset[int] | None] = (None, None)  # what to settle: an unexpected error settles as nothing
        try:
            expected = derive_test_pin(customer_id)
            record = self._lookup(customer_id)
            ok = constant_time_equals(expected, str(pin)) and record is not None and record.customer_status != "Closed"
            outcome = (None, before) if ok else (reserved_at, None)
        finally:
            self._resolve(customer_id, *outcome)
        if not ok:
            raise AuthError("invalid credentials")
        return self.store.issue(customer_id, {"segment": record.segment, "country": record.country,
                                              "customer_status": record.customer_status})


default_identity = IdentityService()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    for cid in sys.argv[1:]:
        print(cid, derive_test_pin(cid))
