"""Bounded retries and the turn's time budget, shared by every outbound call (model, tracing service, ticket queue, tools).

The rules, in one place so each caller states only what it knows about its own call:
- A retry needs a retryable error (timeouts, connection failures, 429/5xx, `Transient`). Anything else is raised at once.
- The number of attempts is capped, the wait between them is exponential with jitter and capped, and no wait starts
  that would not leave time for another attempt inside the turn's deadline. No sleep follows the last attempt.
- A write that is not idempotent is attempted once. It is retried only when the caller names an idempotency key, which
  is the caller's promise that a second attempt cannot duplicate the effect (the tracing service derives the trace id
  from customer and movement; the ticket queue checks the ticket id before it appends again).
- The deadline is per turn (`TURN_BUDGET_SECONDS`) and travels in a context variable, so the model client and the
  retries after it draw on the same budget without every function passing it along.
"""
from __future__ import annotations

import contextlib
import contextvars
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator, TypeVar

T = TypeVar("T")

DEFAULT_TURN_BUDGET_S = 30.0  # the model's own budget is 25 s (LLM_TOTAL_BUDGET_SECONDS); the rest is for tools and rendering


class Transient(Exception):
    """A failure that a later attempt may not repeat: the dependency was busy, unreachable or timed out."""


class DeadlineExceeded(Exception):
    """The turn's time budget ran out before the work could start or finish."""


class Deadline:
    """A point on the monotonic clock. `at` is absolute, so it can be shared across functions and threads."""

    def __init__(self, seconds: float, clock: Callable[[], float] = time.perf_counter):
        self._clock = clock
        self.at = clock() + seconds

    def remaining(self) -> float:
        return self.at - self._clock()

    @property
    def expired(self) -> bool:
        return self.remaining() <= 0


current_deadline: contextvars.ContextVar[Deadline | None] = contextvars.ContextVar("current_deadline", default=None)


def turn_budget_seconds() -> float:
    return float(os.environ.get("TURN_BUDGET_SECONDS") or DEFAULT_TURN_BUDGET_S)


@contextlib.contextmanager
def turn_deadline(seconds: float | None = None, clock: Callable[[], float] = time.perf_counter) -> Iterator[Deadline]:
    """Start the turn's clock for everything called inside the block. An enclosing deadline is never extended."""
    d = Deadline(turn_budget_seconds() if seconds is None else seconds, clock)
    outer = current_deadline.get()
    if outer is not None and outer.remaining() < d.remaining():
        d = outer
    token = current_deadline.set(d)
    try:
        yield d
    finally:
        current_deadline.reset(token)


def remaining_turn_seconds() -> float | None:
    """Seconds left in the turn, or None when no turn clock is running (a script, a test)."""
    d = current_deadline.get()
    return None if d is None else d.remaining()


def backoff_delay(attempt: int, base_s: float, cap_s: float = 8.0, rand: Callable[[], float] = random.random) -> float:
    """Wait before retry number `attempt` + 1 (attempt counts from 0): exponential, capped, then half of it fixed and
    half random, so callers that failed together do not come back together, and never less than half the schedule."""
    step = min(cap_s, base_s * (2 ** attempt))
    return step / 2 + rand() * step / 2


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_s: float = 0.2
    cap_s: float = 2.0


def is_transient(exc: BaseException) -> bool:
    """Whether a later attempt could succeed. Deliberately narrow: an unknown exception is our bug, not a busy service."""
    if isinstance(exc, (Transient, TimeoutError, ConnectionError, InterruptedError)):
        return True
    if isinstance(exc, OSError):  # a busy or flaky disk or mount; the attempts stay bounded if it is really gone
        return True
    with contextlib.suppress(ImportError):
        import duckdb

        return isinstance(exc, (duckdb.IOException, duckdb.ConnectionException, duckdb.TransactionException))
    return False


def retry_call(fn: Callable[[], T], *, policy: RetryPolicy = RetryPolicy(), idempotent: bool = False,
               idempotency_key: str | None = None, retryable: Callable[[BaseException], bool] = is_transient,
               deadline: Deadline | None = None, sleep: Callable[[float], None] = time.sleep,
               rand: Callable[[], float] = random.random, attempts_log: list[dict] | None = None) -> T:
    """Call `fn` up to `policy.max_attempts` times and return its result, or raise the last error.

    `idempotent=True` (a read, or a write that repeats harmlessly) or an `idempotency_key` allows retries; a write
    with neither is attempted once. The first attempt always runs, even past the deadline: a caller that must try
    (filing a handoff) is never denied its one attempt by a clock. `attempts_log` collects one entry per attempt."""
    deadline = deadline or current_deadline.get()
    attempts = policy.max_attempts if (idempotent or idempotency_key) else 1
    for attempt in range(attempts):
        t0 = time.perf_counter()
        try:
            result = fn()
            if attempts_log is not None:
                attempts_log.append({"attempt": attempt + 1, "outcome": "ok", "ms": round((time.perf_counter() - t0) * 1000, 1)})
            return result
        except Exception as exc:  # noqa: BLE001 - what is retryable is decided by `retryable`, not by the type here
            kind = "transient" if retryable(exc) else "permanent"
            if attempts_log is not None:
                attempts_log.append({"attempt": attempt + 1, "outcome": "error", "kind": kind, "error": type(exc).__name__,
                                     "ms": round((time.perf_counter() - t0) * 1000, 1)})
            if kind == "permanent" or attempt == attempts - 1:
                raise
            delay = backoff_delay(attempt, policy.base_s, policy.cap_s, rand)
            if deadline is not None and deadline.remaining() <= delay:
                raise  # the wait would eat what is left of the turn: fail now, and let the caller fall back
            sleep(delay)
    raise AssertionError("unreachable")  # the loop returns or raises


# --- the handoff's own budget ------------------------------------------------------------------------------------------

DEFAULT_HANDOFF_BUDGET_S = 3.0

current_handoff: contextvars.ContextVar[Deadline | None] = contextvars.ContextVar("current_handoff", default=None)


def handoff_budget_seconds() -> float:
    return float(os.environ.get("HANDOFF_BUDGET_SECONDS") or DEFAULT_HANDOFF_BUDGET_S)


def request_budget_seconds() -> float:
    """The most a chat turn works for once it is running: the turn's budget, then the handoff's. The wait for a slot and
    the read of the request body come before it and have their own limits (CHAT_QUEUE_WAIT_SECONDS, REQUEST_BODY_TIMEOUT_SECONDS)."""
    return turn_budget_seconds() + handoff_budget_seconds()


@contextlib.contextmanager
def handoff_deadline() -> Iterator[Deadline]:
    """The clock of one handoff (evidence, lock, write, read-back), independent of the turn's: a turn out of time can
    still hand over, and a handoff cannot take more than its own budget. Nested handoffs share the outer clock."""
    outer = current_handoff.get()
    if outer is not None:
        yield outer
        return
    d = Deadline(handoff_budget_seconds())
    token = current_handoff.set(d)
    try:
        yield d
    finally:
        current_handoff.reset(token)
