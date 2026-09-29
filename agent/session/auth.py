"""Session store: short-lived bearer tokens bound to one authenticated customer.

Tokens are minted only by agent/session/identity.py after a credential
check (never from a bare customer_id). Downstream code — tickets, logs,
admin views — never sees the token itself, only `session_ref`, a one-way
hash, so leaking a ticket can't be turned into a hijacked session.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field

from agent.tools import state


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
    """Sessions in SQLite (agent/tools/state.py): they survive a restart, and only a hash of the token is stored, so a
    copy of the disk cannot be replayed as a login. Without STATE_DB_PATH the database is private and in memory."""

    def __init__(self, ttl_seconds: int | None = None, max_sessions: int = 50_000, db_path: str | None = None):
        self._ttl = ttl_seconds if ttl_seconds is not None else int(os.environ.get("SESSION_TTL_SECONDS", "900"))
        self._max = max_sessions
        self._db = state.connect(db_path)
        self._lock = threading.Lock()

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def issue(self, customer_id: str, attributes: dict | None = None) -> Session:
        now = time.time()
        session = Session(secrets.token_urlsafe(24), customer_id, now, now + self._ttl, dict(attributes or {}))
        with self._lock, self._db:
            if self._count() >= self._max:
                self._db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            if self._count() >= self._max:  # still full: drop the oldest
                self._db.execute("DELETE FROM sessions WHERE token_hash = "
                                 "(SELECT token_hash FROM sessions ORDER BY issued_at LIMIT 1)")
            self._db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                             (self._key(session.token), customer_id, now, session.expires_at, json.dumps(session.attributes)))
        return session

    def validate(self, token: str) -> Session:
        with self._lock, self._db:
            row = self._db.execute("SELECT customer_id, issued_at, expires_at, attributes FROM sessions WHERE token_hash = ?",
                                   (self._key(token),)).fetchone()
            if row is None:
                raise InvalidSession("No session found for this token.")
            if time.time() > row[2]:
                self._db.execute("DELETE FROM sessions WHERE token_hash = ?", (self._key(token),))
                raise ExpiredSession("Session token has expired; re-authenticate.")
            return Session(token, row[0], row[1], row[2], json.loads(row[3]))

    def revoke(self, token: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM sessions WHERE token_hash = ?", (self._key(token),))

    def expire(self, token: str) -> None:
        """Ends a session as if its time had run out (the demo's "expire session" button)."""
        with self._lock, self._db:
            self._db.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?", (time.time() - 1, self._key(token)))

    def _count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    def __len__(self) -> int:
        with self._lock:
            return self._count()


default_store = SessionStore()
