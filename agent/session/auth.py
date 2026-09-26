"""Session store: short-lived bearer tokens bound to one authenticated customer.

Tokens are minted only by agent/session/identity.py after a credential
check (never from a bare customer_id). Downstream code — tickets, logs,
admin views — never sees the token itself, only `session_ref`, a one-way
hash, so leaking a ticket can't be turned into a hijacked session.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from dataclasses import dataclass, field


class SessionError(Exception):
    """Base class for session/auth failures."""


class InvalidSession(SessionError):
    pass


class ExpiredSession(SessionError):
    pass


def session_ref(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


@dataclass
class Session:
    token: str
    customer_id: str
    issued_at: float
    expires_at: float
    attributes: dict = field(default_factory=dict)  # segment, country, customer_status

    @property
    def ref(self) -> str:
        return session_ref(self.token)


class SessionStore:
    """In-memory store. Production: Redis (TTL-native, shared across replicas)."""

    def __init__(self, ttl_seconds: int | None = None, max_sessions: int = 50_000):
        self._ttl = ttl_seconds if ttl_seconds is not None else int(os.environ.get("SESSION_TTL_SECONDS", "900"))
        self._max = max_sessions
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def issue(self, customer_id: str, attributes: dict | None = None) -> Session:
        now = time.time()
        session = Session(secrets.token_urlsafe(24), customer_id, now, now + self._ttl, dict(attributes or {}))
        with self._lock:
            if len(self._sessions) >= self._max:
                self._evict_expired(now)
            if len(self._sessions) >= self._max:  # still full: drop the oldest
                oldest = min(self._sessions.values(), key=lambda s: s.issued_at)
                self._sessions.pop(oldest.token, None)
            self._sessions[session.token] = session
        return session

    def validate(self, token: str) -> Session:
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                raise InvalidSession("No session found for this token.")
            if time.time() > session.expires_at:
                del self._sessions[token]
                raise ExpiredSession("Session token has expired; re-authenticate.")
            return session

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)

    def _evict_expired(self, now: float) -> None:
        for tok in [t for t, s in self._sessions.items() if s.expires_at < now]:
            del self._sessions[tok]

    def __len__(self) -> int:
        return len(self._sessions)


default_store = SessionStore()
