"""Idempotency-Key for POST /chat.

A client that loses the answer to a turn (the connection drops after the server got the message) cannot know whether
the turn ran. It retries with the same key and gets the stored reply instead of a second turn, so a retry cannot file a
second ticket or confirm an action twice. Replies are kept per (session, key) for as long as the session lives, in the
same SQLite file as sessions and conversations (STATE_DB_PATH, or memory): once the session is over nothing stored for
it can be shown, and its key could not be reused. The same key with another message is refused: it is a client bug,
and answering it with the first message's reply would hide it.

When too many replies are kept the oldest are dropped but their keys stay, marked as processed: a retry of one of them
is told so (409) instead of running the turn again. A live session's key is never forgotten: when the table itself is
full (`max_marks`), a new turn is refused before it runs (CapacityFull -> 503 + Retry-After), and every turn takes its
place in the same transaction that checks the limit.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator

from agent.tools import state

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_ENTRIES = 50_000  # replies kept; past it the oldest lose their reply and stay as marks
MAX_MARKS = 500_000  # keys held in all, until their session ends; when full, new turns are refused


class KeyReused(Exception):
    """The key was used before with a different message."""


class CapacityFull(Exception):
    """No place for another key until some session ends; nothing was run."""

    def __init__(self, retry_after: int):
        super().__init__(retry_after)
        self.retry_after = retry_after


@dataclass
class Slot:
    replay: str | None  # the stored reply (JSON) when this key already ran and its reply is still kept
    processed: bool = False  # this key already ran, and its reply is no longer kept
    _save: Callable[[str], None] = field(default=lambda body: None, repr=False)
    saved: bool = False
    started: bool = False

    def begin(self) -> None:
        """The point of no return: the turn is about to run and may have effects. From here the key's place is only
        given back by `abandon`; an error, before or after the reply is saved, leaves the key marked as processed."""
        self.started = True

    def abandon(self) -> None:
        """The turn is proven to have had no effect (the session had already ended): give the place back."""
        self.started = False

    def save(self, body: str) -> None:
        self._save(body)
        self.saved = True


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class IdempotencyStore:
    def __init__(self, max_entries: int = MAX_ENTRIES, max_marks: int = MAX_MARKS, db_path: str | None = None):
        self._max_entries, self._max_marks = max_entries, max_marks
        self._db = state.connect(db_path)
        # First version of the table, only ever on an unmerged branch (keys unhashed, no session expiry): dropped, not migrated.
        self._db.execute("DROP TABLE IF EXISTS idempotency")
        self._db.execute("CREATE TABLE IF NOT EXISTS idempotency_keys (session_ref TEXT NOT NULL, key_hash TEXT NOT NULL, "
                         "message_hash TEXT NOT NULL, response TEXT, created_at REAL NOT NULL, expires_at REAL NOT NULL, "
                         "PRIMARY KEY (session_ref, key_hash))")
        self._lock = threading.Lock()
        self._running: dict[tuple[str, str], list] = {}  # key -> [its lock, how many are holding or waiting for it]

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM idempotency_keys").fetchone()[0]

    @contextmanager
    def guard(self, session_ref: str, key: str, message: str, expires_at: float) -> Iterator[Slot]:
        """One turn per key at a time: a retry that arrives while the first is still running waits for its reply
        rather than running a second turn. What is saved lives until `expires_at` (the session's own end). Raises
        KeyReused for the same key with another message."""
        ident = (session_ref, _digest(key))
        with self._lock:
            entry = self._running.setdefault(ident, [threading.Lock(), 0])
            entry[1] += 1
        with entry[0]:
            slot = None
            try:
                message_hash = _digest(message)
                with self._lock, self._db:  # one transaction: look up the key and, if new, take its place
                    now = time.time()
                    self._db.execute("DELETE FROM idempotency_keys WHERE expires_at < ?", (now,))
                    row = self._db.execute("SELECT message_hash, response FROM idempotency_keys WHERE session_ref = ? "
                                           "AND key_hash = ?", ident).fetchone()
                    if row and row[0] != message_hash:
                        raise KeyReused(key)
                    if row is None:
                        total, soonest = self._db.execute("SELECT COUNT(*), MIN(expires_at) FROM idempotency_keys").fetchone()
                        if total >= self._max_marks:
                            raise CapacityFull(max(1, min(900, int((soonest or now) - now) + 1)))
                        # Held from here. Given back only if the turn is refused before it begins (Slot.begin); once it
                        # began, or if the process dies mid-turn, the mark stays: the turn may have had effects.
                        self._db.execute("INSERT INTO idempotency_keys VALUES (?, ?, ?, NULL, ?, ?)",
                                         (*ident, message_hash, now, expires_at))

                def save(body: str) -> None:
                    with self._lock, self._db:
                        self._db.execute("UPDATE idempotency_keys SET response = ?, created_at = ?, expires_at = ? "
                                         "WHERE session_ref = ? AND key_hash = ?", (body, time.time(), expires_at, *ident))
                        self._make_room()

                slot = Slot(replay=row[1] if row else None, processed=row is not None and row[1] is None, _save=save)
                yield slot
            finally:
                if slot is not None and row is None and not slot.saved and not slot.started:  # it never began to run
                    with self._lock, self._db:
                        self._db.execute("DELETE FROM idempotency_keys WHERE session_ref = ? AND key_hash = ? "
                                         "AND response IS NULL", ident)
                with self._lock:
                    entry[1] -= 1
                    if entry[1] == 0:
                        del self._running[ident]

    def _make_room(self) -> None:
        """Called with the lock held. Past `max_entries` the oldest replies lose the reply and keep the mark."""
        kept = self._db.execute("SELECT COUNT(*) FROM idempotency_keys WHERE response IS NOT NULL").fetchone()[0]
        if kept > self._max_entries:
            drop = max(1, self._max_entries // 50) + kept - self._max_entries - 1
            self._db.execute("UPDATE idempotency_keys SET response = NULL WHERE rowid IN (SELECT rowid FROM idempotency_keys "
                             "WHERE response IS NOT NULL ORDER BY created_at, rowid LIMIT ?)", (drop,))


default = IdempotencyStore()
