"""Idempotency-Key for POST /chat.

A client that loses the answer to a turn (the connection drops after the server got the message) cannot know whether
the turn ran. It retries with the same key and gets the stored reply instead of a second turn, so a retry cannot file a
second ticket or confirm an action twice. Replies are kept per (session, key) for a short time in the same SQLite file
as sessions and conversations (STATE_DB_PATH, or memory). The same key with another message is refused: it is a
client bug, and answering it with the first message's reply would hide it.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from agent.tools import state

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_ENTRIES = 50_000


class KeyReused(Exception):
    """The key was used before with a different message."""


@dataclass
class Slot:
    replay: str | None  # the stored reply (JSON) when this key already ran, else None
    _save: "callable" = field(default=lambda body: None, repr=False)

    def save(self, body: str) -> None:
        self._save(body)


class IdempotencyStore:
    def __init__(self, ttl_seconds: int | None = None, db_path: str | None = None):
        self._ttl = ttl_seconds if ttl_seconds is not None else int(os.environ.get("IDEMPOTENCY_TTL_SECONDS", "600"))
        self._db = state.connect(db_path)
        self._db.execute("CREATE TABLE IF NOT EXISTS idempotency (session_ref TEXT NOT NULL, key TEXT NOT NULL, "
                         "message_hash TEXT NOT NULL, response TEXT NOT NULL, created_at REAL NOT NULL, "
                         "PRIMARY KEY (session_ref, key))")
        self._lock = threading.Lock()
        self._running: dict[tuple[str, str], list] = {}  # key -> [its lock, how many are holding or waiting for it]

    @staticmethod
    def _hash(message: str) -> str:
        return hashlib.sha256(message.encode()).hexdigest()

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM idempotency").fetchone()[0]

    @contextmanager
    def guard(self, session_ref: str, key: str, message: str) -> Iterator[Slot]:
        """One turn per key at a time: a retry that arrives while the first is still running waits for its reply
        rather than running a second turn. Raises KeyReused for the same key with another message."""
        ident = (session_ref, key)
        with self._lock:
            entry = self._running.setdefault(ident, [threading.Lock(), 0])
            entry[1] += 1
        with entry[0]:
            try:
                digest = self._hash(message)
                with self._lock, self._db:
                    self._db.execute("DELETE FROM idempotency WHERE created_at < ?", (time.time() - self._ttl,))
                    row = self._db.execute("SELECT message_hash, response FROM idempotency WHERE session_ref = ? AND key = ?",
                                           ident).fetchone()
                if row and row[0] != digest:
                    raise KeyReused(key)

                def save(body: str) -> None:
                    with self._lock, self._db:
                        if self._db.execute("SELECT COUNT(*) FROM idempotency").fetchone()[0] >= MAX_ENTRIES:
                            self._db.execute("DELETE FROM idempotency WHERE rowid IN "
                                             "(SELECT rowid FROM idempotency ORDER BY created_at LIMIT 1000)")
                        self._db.execute("INSERT OR REPLACE INTO idempotency VALUES (?, ?, ?, ?, ?)",
                                         (*ident, digest, body, time.time()))

                yield Slot(replay=row[1] if row else None, _save=save)
            finally:
                with self._lock:
                    entry[1] -= 1
                    if entry[1] == 0:
                        del self._running[ident]


default = IdempotencyStore()
