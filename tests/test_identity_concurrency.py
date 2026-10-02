"""Failed-login attempts are reserved before the PIN is checked, so concurrent logins cannot check more PINs than the limit allows.

Every wait here is an event or a queue with a timeout, never a sleep: the tests say what must happen once the first attempt is
held inside the lookup, not how long anything takes.
"""
from __future__ import annotations

import queue
import threading
import time
from collections import Counter

import pytest

from agent.session.auth import SessionStore
from agent.session.identity import MAX_FAILURES, AuthError, IdentityService, LockedOut, derive_test_pin

CUSTOMER = "CLI-FIX0001"
WAIT = 5  # seconds an event may take before the test gives up


def wrong_pin(customer_id: str) -> str:
    return f"{(int(derive_test_pin(customer_id)) + 1) % 1_000_000:06d}"


def service() -> IdentityService:
    return IdentityService(store=SessionStore(ttl_seconds=900))


def race(svc: IdentityService, monkeypatch, attempts: int, pin: str, held: set[str] | None = None):
    """Starts `attempts` logins at once with the first one to reach the warehouse lookup held inside it. Returns what each
    login ended with (the exception type, or 'session'), and how many reached the lookup."""
    entered, release, reached = threading.Event(), threading.Event(), []
    real = svc._lookup

    def gated(customer_id):
        reached.append(customer_id)
        entered.set()
        assert release.wait(WAIT), "the held lookup was never released"
        return real(customer_id)

    monkeypatch.setattr(svc, "_lookup", gated)
    outcomes: queue.Queue = queue.Queue()

    def attempt():
        try:
            svc.login(CUSTOMER, pin)
            outcomes.put("session")
        except Exception as exc:  # noqa: BLE001
            outcomes.put(type(exc))

    threads = [threading.Thread(target=attempt, daemon=True) for _ in range(attempts)]
    results: list = []
    try:
        for t in threads:
            t.start()
        assert entered.wait(WAIT), "no attempt reached the lookup"
        # Every attempt that was refused answers while the first is still inside the lookup; one that is not refused is
        # inside the lookup too and cannot answer, so waiting for these is how the test tells the two apart.
        for _ in range(attempts - 1):
            try:
                results.append(outcomes.get(timeout=2))
            except queue.Empty:
                break
    finally:
        release.set()
    for t in threads:
        t.join(WAIT)
    while not outcomes.empty():
        results.append(outcomes.get_nowait())
    return results, len(reached)


def test_with_four_failures_recorded_only_one_more_check_reaches_the_verifier(monkeypatch):
    svc = service()
    svc._failures[CUSTOMER] = [time.time()] * (MAX_FAILURES - 1)
    results, reached = race(svc, monkeypatch, attempts=4, pin=wrong_pin(CUSTOMER))
    assert reached == 1  # the one place left, taken before the lookup
    assert Counter(results) == {LockedOut: 3, AuthError: 1}
    with pytest.raises(LockedOut):  # and the account is now locked, as five failures promise
        svc.login(CUSTOMER, derive_test_pin(CUSTOMER))


def test_a_fresh_account_admits_exactly_the_failures_the_limit_allows_under_concurrency(monkeypatch):
    svc = service()
    results, reached = race(svc, monkeypatch, attempts=MAX_FAILURES + 3, pin=wrong_pin(CUSTOMER))
    assert reached == MAX_FAILURES
    assert Counter(results) == {AuthError: MAX_FAILURES, LockedOut: 3}


def test_other_accounts_are_not_blocked_while_one_is_in_the_warehouse_lookup(monkeypatch):
    svc = service()
    entered, release = threading.Event(), threading.Event()
    real = svc._lookup

    def gated(customer_id):
        if customer_id == CUSTOMER:
            entered.set()
            assert release.wait(WAIT)
        return real(customer_id)

    monkeypatch.setattr(svc, "_lookup", gated)
    slow = threading.Thread(target=lambda: pytest.raises(AuthError, svc.login, CUSTOMER, wrong_pin(CUSTOMER)), daemon=True)
    slow.start()
    try:
        assert entered.wait(WAIT)
        other = "CLI-FIX0002"
        done = queue.Queue()
        threading.Thread(target=lambda: done.put(svc.login(other, derive_test_pin(other))), daemon=True).start()
        assert done.get(timeout=WAIT).customer_id == other  # answered while the first is still held
    finally:
        release.set()
        slow.join(WAIT)


def test_a_lookup_that_fails_gives_the_reserved_place_back(monkeypatch):
    svc = service()
    svc._failures[CUSTOMER] = [time.time()] * (MAX_FAILURES - 1)

    def broken(customer_id):
        raise RuntimeError("warehouse down")

    monkeypatch.setattr(svc, "_lookup", broken)
    with pytest.raises(RuntimeError):
        svc.login(CUSTOMER, wrong_pin(CUSTOMER))
    monkeypatch.undo()
    assert svc.login(CUSTOMER, derive_test_pin(CUSTOMER)).customer_id == CUSTOMER  # not locked out by an error that was not a guess


def test_a_success_clears_the_failures_and_leaves_nothing_reserved():
    svc = service()
    svc._failures[CUSTOMER] = [time.time()] * (MAX_FAILURES - 1)
    assert svc.login(CUSTOMER, derive_test_pin(CUSTOMER)).customer_id == CUSTOMER
    assert svc._failures.get(CUSTOMER) is None
    assert svc._inflight.get(CUSTOMER) is None  # nothing left reserved
