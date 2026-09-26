"""Mock session/authentication service.

The problem statement is explicit: "a national ID or customer number alone
does not prove identity" — a real deployment would sit behind the bank's own
identity provider. For this prototype we simulate a trusted test-session
service: something upstream (a login flow, an IVR PIN check, an app token)
already authenticated the caller and handed them a short-lived session token
bound to exactly one customer_id. Every tool call is gated on a *valid,
unexpired* token — never on a bare customer_id/document_number passed in the
conversation, which is exactly the kind of thing a prompt-injection attempt
would try to spoof.
"""
from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass


class SessionError(Exception):
    """Base class for session/auth failures."""


class InvalidSession(SessionError):
    pass


class ExpiredSession(SessionError):
    pass


@dataclass
class Session:
    token: str
    customer_id: str
    issued_at: float
    expires_at: float


class SessionStore:
    """In-memory session store. Swap for Redis/DB-backed store in production."""

    def __init__(self, ttl_seconds: int | None = None):
        self._ttl = ttl_seconds or int(os.environ.get("SESSION_TTL_SECONDS", "900"))
        self._sessions: dict[str, Session] = {}

    def issue(self, customer_id: str) -> Session:
        token = secrets.token_urlsafe(24)
        now = time.time()
        session = Session(token=token, customer_id=customer_id, issued_at=now, expires_at=now + self._ttl)
        self._sessions[token] = session
        return session

    def validate(self, token: str) -> Session:
        session = self._sessions.get(token)
        if session is None:
            raise InvalidSession("No session found for this token.")
        if time.time() > session.expires_at:
            del self._sessions[token]
            raise ExpiredSession("Session token has expired; re-authenticate.")
        return session

    def revoke(self, token: str) -> None:
        self._sessions.pop(token, None)


# Process-wide singleton store used by the API layer. A real deployment would
# back this with Redis so it survives restarts / works across replicas.
default_store = SessionStore()
