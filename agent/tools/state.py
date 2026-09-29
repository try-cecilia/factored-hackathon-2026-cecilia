"""One small SQLite file for the state that must outlive the process: sessions and conversations.

STATE_DB_PATH names it (on Render: the persistent disk, next to the warehouse). Unset, the stores use a private
in-memory database, so tests and one-off runs behave as before. SQLite gives real transactions and survives a restart;
it has one writer at a time, so this is not a multi-replica design (LIMITATIONS.md: that needs Redis or Postgres).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, customer_id TEXT NOT NULL, issued_at REAL NOT NULL,
    expires_at REAL NOT NULL, attributes TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conversations (
    key TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    """The state database at `path` (default STATE_DB_PATH), or a private in-memory one. Callers serialize their own
    access with a lock: the connection is shared across the server's threads."""
    path = path or os.environ.get("STATE_DB_PATH")
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path or ":memory:", check_same_thread=False, timeout=10)
    if path:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn
