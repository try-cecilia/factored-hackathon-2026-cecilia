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


def _held_login(svc, monkeypatch, name: str, pin: str):
    """Starts a login of `name` that is held inside the lookup until released; any other login passes through it."""
    entered, release, outcome = threading.Event(), threading.Event(), queue.Queue()
    real = svc._lookup

    def lookup(customer_id):
        if threading.current_thread().name == name:
            entered.set()
            assert release.wait(WAIT), "the held lookup was never released"
        return real(customer_id)

    monkeypatch.setattr(svc, "_lookup", lookup)

    def run():
        try:
            outcome.put(svc.login(CUSTOMER, pin))
        except Exception as exc:  # noqa: BLE001
            outcome.put(exc)

    worker = threading.Thread(target=run, name=name, daemon=True)
    worker.start()
    assert entered.wait(WAIT), "the login never reached the lookup"
    return worker, release, outcome


def test_a_success_does_not_erase_the_failures_of_attempts_that_ran_beside_it(monkeypatch):
    """The correct PIN is held in the lookup; four wrong ones finish meanwhile; the success then resolves. Those four failures
    were not before it, so they stay, and the account is one place from locked."""
    svc = service()
    worker, release, outcome = _held_login(svc, monkeypatch, "successful-login", derive_test_pin(CUSTOMER))
    try:
        for _ in range(MAX_FAILURES - 1):
            with pytest.raises(AuthError):
                svc.login(CUSTOMER, wrong_pin(CUSTOMER))
    finally:
        release.set()
        worker.join(WAIT)
    assert not isinstance(outcome.get(timeout=WAIT), Exception)
    assert len(svc._failures[CUSTOMER]) == MAX_FAILURES - 1
    assert not svc._inflight


def test_a_success_that_resolves_before_a_failure_that_began_earlier_keeps_that_failure(monkeypatch):
    """The other order: the wrong PIN is held; the correct one starts after it and finishes first; the wrong one resolves last."""
    svc = service()
    svc._failures[CUSTOMER] = [time.time()] * 2  # before both: the success clears these
    worker, release, outcome = _held_login(svc, monkeypatch, "slow-failure", wrong_pin(CUSTOMER))
    try:
        assert svc.login(CUSTOMER, derive_test_pin(CUSTOMER)).customer_id == CUSTOMER
        assert CUSTOMER not in svc._failures or svc._failures[CUSTOMER] == []  # the two earlier failures are gone
    finally:
        release.set()
        worker.join(WAIT)
    assert isinstance(outcome.get(timeout=WAIT), AuthError)
    assert len(svc._failures[CUSTOMER]) == 1  # and the slow failure, resolved after the success, counts
    assert not svc._inflight


def test_a_success_clears_what_was_recorded_before_it_began_and_five_failures_still_lock(monkeypatch):
    svc = service()
    for _ in range(MAX_FAILURES - 1):
        with pytest.raises(AuthError):
            svc.login(CUSTOMER, wrong_pin(CUSTOMER))
    assert svc.login(CUSTOMER, derive_test_pin(CUSTOMER)).customer_id == CUSTOMER
    assert svc._failures.get(CUSTOMER) in (None, [])
    for _ in range(MAX_FAILURES):
        with pytest.raises(AuthError) as err:
            svc.login(CUSTOMER, wrong_pin(CUSTOMER))
        assert not isinstance(err.value, LockedOut)
    with pytest.raises(LockedOut):
        svc.login(CUSTOMER, derive_test_pin(CUSTOMER))


@pytest.mark.parametrize("order", [("a", "b"), ("b", "a")])
@pytest.mark.parametrize("same_clock", [False, True])
def test_two_successes_each_clear_only_the_failures_they_began_after(monkeypatch, order, same_clock):
    """A and B are held in the lookup while one earlier failure stands. The first to resolve clears it; a new failure then comes in; the
    second to resolve must not take that one too, even when the clock gave both failures the same timestamp."""
    import types

    from agent.session import identity

    svc = service()
    if same_clock:  # only identity's clock stands still, so waits and the framework's keep advancing
        monkeypatch.setattr(identity, "time", types.SimpleNamespace(time=lambda: 12345.0))
    with pytest.raises(AuthError):
        svc.login(CUSTOMER, wrong_pin(CUSTOMER))
    assert len(svc._failures[CUSTOMER]) == 1
    entered = {name: threading.Event() for name in "ab"}
    release = {name: threading.Event() for name in "ab"}
    results = {name: queue.Queue() for name in "ab"}
    real = svc._lookup

    def lookup(customer_id):
        name = threading.current_thread().name
        if name in entered:
            entered[name].set()
            assert release[name].wait(WAIT), "the held lookup was never released"
        return real(customer_id)

    monkeypatch.setattr(svc, "_lookup", lookup)

    def login(name):
        try:
            results[name].put(svc.login(CUSTOMER, derive_test_pin(CUSTOMER)))
        except BaseException as exc:  # noqa: BLE001
            results[name].put(exc)

    workers = {name: threading.Thread(target=login, args=(name,), name=name, daemon=True) for name in "ab"}
    first, last = order
    try:
        for name in "ab":
            workers[name].start()
            assert entered[name].wait(WAIT)
        release[first].set()
        workers[first].join(WAIT)
        assert not isinstance(results[first].get(timeout=WAIT), BaseException)
        assert not svc._failures.get(CUSTOMER)  # the earlier failure is gone
        with pytest.raises(AuthError):
            svc.login(CUSTOMER, wrong_pin(CUSTOMER))  # a new one, between the two resolutions
        assert len(svc._failures[CUSTOMER]) == 1
        release[last].set()
        workers[last].join(WAIT)
        assert not isinstance(results[last].get(timeout=WAIT), BaseException)
    finally:
        for name in "ab":
            release[name].set()
        for worker in workers.values():
            if worker.ident is not None:
                worker.join(WAIT)
    assert not svc._inflight
    assert len(svc._failures.get(CUSTOMER, [])) == 1  # the new failure survived both successes
