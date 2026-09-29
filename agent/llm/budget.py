"""A daily spend cap on the language model, for a public demo that anyone can use.

Past LLM_DAILY_BUDGET_USD (UTC day; unset or 0 = no cap) the orchestrator
stops calling the model and runs as if it were down: the degraded mode
answers plain balance questions deterministically and hands the rest to a
person. A call whose price is unknown counts as UNPRICED_CALL_USD, so an
unpriced model cannot slip past the cap.

ponytail: in memory, per process. A restart forgets today's spend, so the
spend limit set on the provider key stays the hard ceiling; this one stops a
burst of traffic from reaching it in hours.
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable

UNPRICED_CALL_USD = 0.01


class DailyBudget:
    def __init__(self, limit_usd: float | None = None, clock: Callable[[], float] = time.time):
        self.limit_usd = limit_usd
        self._clock = clock
        self._day, self._spent = "", 0.0
        self._lock = threading.Lock()

    def _today(self) -> str:
        day = datetime.fromtimestamp(self._clock(), timezone.utc).date().isoformat()
        if day != self._day:
            self._day, self._spent = day, 0.0
        return day

    def spent_today(self) -> float:
        with self._lock:
            self._today()
            return self._spent

    def add(self, usd: float | None) -> None:
        with self._lock:
            self._today()
            self._spent += UNPRICED_CALL_USD if usd is None else usd

    def exhausted(self) -> bool:
        return bool(self.limit_usd) and self.spent_today() >= self.limit_usd


default_budget = DailyBudget(float(os.environ.get("LLM_DAILY_BUDGET_USD") or 0) or None)


class SessionBudget:
    """A spend cap per session (LLM_SESSION_BUDGET_USD, default USD 0.25; 0 = no cap), in memory, bounded to the
    most recent sessions. A live session can send 20 messages a minute for its 15 minutes; at the measured USD 0.0014
    per turn that is about USD 0.4, so a session that gets to the default is looping or being abused, not chatting.
    Past it the assistant answers that session in degraded mode, exactly as when the daily cap is reached."""

    MAX_SESSIONS = 10_000

    def __init__(self, limit_usd: float | None = None):
        self.limit_usd = limit_usd
        self._spent: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "SessionBudget":
        return cls(float(os.environ.get("LLM_SESSION_BUDGET_USD", "0.25") or 0) or None)

    def add(self, session_ref: str, usd: float | None) -> None:
        with self._lock:
            self._spent[session_ref] = self._spent.pop(session_ref, 0.0) + (UNPRICED_CALL_USD if usd is None else usd)
            while len(self._spent) > self.MAX_SESSIONS:
                self._spent.popitem(last=False)

    def spent(self, session_ref: str) -> float:
        with self._lock:
            return self._spent.get(session_ref, 0.0)

    def exhausted(self, session_ref: str) -> bool:
        return bool(self.limit_usd) and self.spent(session_ref) >= self.limit_usd
