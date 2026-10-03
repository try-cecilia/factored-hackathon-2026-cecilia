"""Per-key rate limits in memory: a sliding window per key, and the 429 that says when to come back."""
from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from agent import metrics


class RateLimiter:
    """A sliding window per key, in memory: it resets on restart and is not shared between replicas (a second replica
    needs Redis). Bounded: keys that have gone quiet are dropped, and past MAX_KEYS the oldest go first."""

    MAX_KEYS = 100_000
    SWEEP_EVERY = 1_000

    def __init__(self, limit: int, window_s: float, name: str = ""):
        self.limit, self.window_s, self.name = limit, window_s, name
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def _prune(self, key: str, now: float) -> deque:
        q = self._hits[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        return q

    def _sweep(self, now: float) -> None:
        for key in [k for k, q in self._hits.items() if not q or now - q[-1] > self.window_s]:
            del self._hits[key]
        while len(self._hits) > self.MAX_KEYS:
            del self._hits[next(iter(self._hits))]

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._calls += 1
            if self._calls % self.SWEEP_EVERY == 0:
                self._sweep(now)
            q = self._prune(key, now)
            if len(q) >= self.limit:
                if self.name:
                    metrics.default.rate_limited.labels(self.name).inc()
                return False
            q.append(now)
            return True

    def over(self, key: str) -> bool:
        """Whether this key has used up its hits in the window. Looking does not count as a hit."""
        with self._lock:
            return len(self._prune(key, time.time())) >= self.limit

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.time())

    def reserve(self, key: str) -> float | None:
        """Takes one of this key's hits, checking and taking in one step, or returns None if none is left. What it returns is
        the claim ticket for `release`. The check-then-record pair (`over`, `record`) lets concurrent callers all pass the check."""
        now = time.time()
        with self._lock:
            q = self._prune(key, now)
            if len(q) >= self.limit:
                return None
            q.append(now)
            return now

    def release(self, key: str, ticket: float) -> None:
        """Gives back a hit taken by `reserve` (its attempt turned out not to be a failure)."""
        with self._lock:
            try:
                self._hits[key].remove(ticket)
            except ValueError:  # already aged out of the window, or never held
                pass

    def retry_after(self, key: str) -> int:
        """Whole seconds until this key has a hit to spend again (at least 1)."""
        now = time.time()
        with self._lock:
            q = self._prune(key, now)
            return max(1, math.ceil(self.window_s - (now - q[0]))) if q else 1

    def __len__(self) -> int:
        return len(self._hits)


def too_many(limiter: "RateLimiter", key: str, detail: str) -> HTTPException:
    return HTTPException(429, detail, headers={"Retry-After": str(limiter.retry_after(key))})
