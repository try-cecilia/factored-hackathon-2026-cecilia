"""Bounded retries (agent/resilience.py) with injected faults: the limits are the point, so each test breaks one."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.llm.client import LLMClient, LLMUnavailable, Provider
from agent.resilience import (Deadline, RetryPolicy, Transient, backoff_delay, current_deadline, is_transient, retry_call,
                              turn_deadline)


class Flaky:
    """Fails `failures` times with `error`, then answers "ok". Counts calls."""

    def __init__(self, failures: int, error: Exception | None = None):
        self.failures, self.error, self.calls = failures, error or Transient("busy"), 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "ok"


POLICY = RetryPolicy(max_attempts=3, base_s=0.1, cap_s=0.4)


def test_a_transient_failure_is_retried_and_the_attempts_are_capped():
    sleeps = []
    assert retry_call(Flaky(2), policy=POLICY, idempotent=True, sleep=sleeps.append) == "ok"
    always = Flaky(99)
    with pytest.raises(Transient):
        retry_call(always, policy=POLICY, idempotent=True, sleep=sleeps.append)
    assert always.calls == POLICY.max_attempts  # never a fourth try
    assert len(sleeps) == 2 + 2  # two waits before the success, two before giving up: none after the last attempt


def test_backoff_grows_is_capped_and_is_never_less_than_half_the_schedule():
    for attempt, step in ((0, 0.1), (1, 0.2), (2, 0.4), (3, 0.4), (9, 0.4)):
        low, high = backoff_delay(attempt, 0.1, 0.4, lambda: 0.0), backoff_delay(attempt, 0.1, 0.4, lambda: 1.0)
        assert (low, high) == (pytest.approx(step / 2), pytest.approx(step))  # jitter spans [step/2, step]; step is capped at 0.4


def test_only_retryable_errors_are_retried():
    for error in (ValueError("bad argument"), KeyError("x"), RuntimeError("bug")):
        f = Flaky(99, error)
        with pytest.raises(type(error)):
            retry_call(f, policy=POLICY, idempotent=True, sleep=lambda s: None)
        assert f.calls == 1
    for error in (TimeoutError(), ConnectionError(), OSError("disk busy"), Transient()):
        assert is_transient(error)
    assert not is_transient(ValueError()) and not is_transient(RuntimeError())


def test_a_write_that_is_not_idempotent_is_attempted_once_unless_it_carries_an_idempotency_key():
    write = Flaky(1)
    with pytest.raises(Transient):
        retry_call(write, policy=POLICY, sleep=lambda s: None)  # neither a read nor keyed
    assert write.calls == 1
    keyed = Flaky(1)
    assert retry_call(keyed, policy=POLICY, idempotency_key="TR-0001", sleep=lambda s: None) == "ok" and keyed.calls == 2


def test_no_wait_is_started_that_would_outlast_the_turns_deadline():
    now = [0.0]
    d = Deadline(1.0, clock=lambda: now[0])
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    f = Flaky(99)
    with pytest.raises(Transient):
        retry_call(f, policy=RetryPolicy(max_attempts=10, base_s=0.3, cap_s=2.0), idempotent=True, deadline=d, sleep=sleep, rand=lambda: 1.0)
    assert sum(slept) < 1.0 and f.calls < 10  # 0.3 + 0.6 fit inside 1 s; the next wait (1.2 s) does not, so it fails at once


def test_the_first_attempt_runs_even_when_the_deadline_has_passed():
    f = Flaky(0)
    assert retry_call(f, policy=POLICY, idempotent=True, deadline=Deadline(-5)) == "ok" and f.calls == 1
    g = Flaky(1)
    with pytest.raises(Transient):
        retry_call(g, policy=POLICY, idempotent=True, deadline=Deadline(-5), sleep=lambda s: pytest.fail("slept past the deadline"))
    assert g.calls == 1  # an expired budget allows the one attempt, never a retry


def test_the_attempt_log_says_what_happened_each_time():
    log: list[dict] = []
    retry_call(Flaky(1, TimeoutError()), policy=POLICY, idempotent=True, sleep=lambda s: None, attempts_log=log)
    assert [(a["attempt"], a["outcome"]) for a in log] == [(1, "error"), (2, "ok")] and log[0]["kind"] == "transient"


def test_the_turn_deadline_can_be_shortened_by_an_inner_scope_but_never_extended():
    with turn_deadline(100) as outer:
        with turn_deadline(1000) as inner:
            assert inner is outer  # asking for more time inside a turn gets the turn's own budget
        with turn_deadline(1) as short:
            assert short.remaining() <= 1 and current_deadline.get() is short
        assert current_deadline.get() is outer
    assert current_deadline.get() is None


# --- the model client draws on the same budget ---------------------------------------------------------------------

class HttpError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def provider(name, calls, error=HttpError(503), delay=0.0):
    import time

    def create(**kwargs):
        calls.append(name)
        time.sleep(delay)
        raise error

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return Provider(name, f"{name}-model", f"{name.upper()}_KEY", lambda key, timeout: sdk)


def test_the_model_is_tried_at_most_max_attempts_per_provider_and_then_the_next_provider(monkeypatch):
    monkeypatch.setenv("P1_KEY", "k")
    monkeypatch.setenv("P2_KEY", "k")
    calls, sleeps = [], []
    client = LLMClient([provider("p1", calls), provider("p2", calls)], max_attempts_per_provider=2, sleep=sleeps.append)
    with pytest.raises(LLMUnavailable) as e:
        client.chat([{"role": "user", "content": "hi"}])
    assert calls == ["p1", "p1", "p2", "p2"] and len(sleeps) == 2  # one wait per provider, none after its last attempt
    assert sum(a["outcome"] == "error" for a in e.value.attempts) == 4


def test_a_retry_wait_that_outlasts_the_budget_is_not_slept_and_the_turn_falls_back(monkeypatch):
    monkeypatch.setenv("P1_KEY", "k")
    calls, sleeps = [], []
    client = LLMClient([provider("p1", calls)], total_budget_s=0.2, backoff_base_s=5.0, sleep=sleeps.append)
    with pytest.raises(LLMUnavailable) as e:
        client.chat([{"role": "user", "content": "hi"}])
    assert calls == ["p1"] and sleeps == []  # a 2.5-5 s wait cannot fit in 0.2 s: no wait, no second call
    assert e.value.attempts[-1] == {"provider": "p1", "outcome": "skipped", "reason": "turn_budget_exhausted"}


def test_the_model_never_gets_more_time_than_the_turn_has_left(monkeypatch):
    monkeypatch.setenv("P1_KEY", "k")
    calls = []
    client = LLMClient([provider("p1", calls)], total_budget_s=25, sleep=lambda s: None)
    with turn_deadline(-1):  # the turn's clock has already run out
        with pytest.raises(LLMUnavailable) as e:
            client.chat([{"role": "user", "content": "hi"}])
    assert calls == [] and e.value.attempts[0]["reason"] == "turn_budget_exhausted"


def test_a_slow_provider_costs_one_timeout_not_one_per_request(monkeypatch):
    monkeypatch.setenv("P1_KEY", "k")
    calls = []
    client = LLMClient([provider("p1", calls, error=TimeoutError("slow"))], breaker_threshold=2, sleep=lambda s: None)
    for _ in range(3):
        with pytest.raises(LLMUnavailable):
            client.chat([{"role": "user", "content": "hi"}])
    assert calls == ["p1", "p1"]  # two attempts in the first turn trip the breaker; the next two turns never reach the provider


def test_a_retry_after_from_the_provider_is_never_undercut_and_never_waited_past_the_budget(monkeypatch):
    monkeypatch.setenv("P1_KEY", "k")

    class Limited(Exception):
        status_code = 429

        def __init__(self, retry_after):
            super().__init__("HTTP 429")
            self.response = SimpleNamespace(headers={"retry-after": str(retry_after)}, status_code=429)

    for retry_after, budget, expect_sleep in ((3, 25, 3.0), (60, 25, None)):
        calls, sleeps = [], []
        client = LLMClient([provider("p1", calls, error=Limited(retry_after))], total_budget_s=budget, backoff_base_s=0.1,
                           sleep=sleeps.append)
        with pytest.raises(LLMUnavailable) as e:
            client.chat([{"role": "user", "content": "hi"}])
        if expect_sleep is None:  # asked to wait longer than the turn has: no wait, no second call
            assert calls == ["p1"] and sleeps == [] and e.value.attempts[-1]["reason"] == "turn_budget_exhausted"
        else:
            assert calls == ["p1", "p1"] and sleeps == [pytest.approx(expect_sleep)]  # waited what it asked, not the 0.1 s backoff
        assert e.value.attempts[0]["retry_after_s"] == retry_after
