"""A lock between processes for the JSONL files this service appends to, so the retention purge can rewrite one without losing
a record another process was writing.

Every writer takes it around opening and appending (`with locked(path): ...`) and the purge takes it around reading, filtering
and swapping the file in. The lock is `flock` on a small file next to the data (`<name>.lock`, created on demand and left in place:
a lock on the data file itself would not survive its replacement). flock locks belong to the open file description, so it
serializes threads of one process as well as processes; it is released by the kernel if the holder dies. Readers do not lock:
they already tolerate a half-written last line.

Where fcntl does not exist (Windows) the lock does nothing and the old, tiny window between a purge's last read and its swap
is back; LIMITATIONS.md says so.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - not on Linux or macOS
    fcntl = None  # type: ignore[assignment]


def lock_path(path: str | os.PathLike) -> Path:
    p = Path(path)
    return p.with_name(p.name + ".lock")


@contextlib.contextmanager
def locked(path: str | os.PathLike) -> Iterator[None]:
    """Hold the exclusive lock of `path` (the data file's own path, not the lock's) for the block."""
    if fcntl is None:  # pragma: no cover
        yield
        return
    lock = lock_path(path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def append_line(path: str | os.PathLike, line: str) -> None:
    """Append one line (a newline is added) under the lock: what a writer should call instead of opening the file itself."""
    with locked(path), open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _serialized(method):
    """`method` (of an object with a `.path`) run under the lock of that path."""
    import functools

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with locked(self.path):
            return method(self, *args, **kwargs)

    wrapper.__wrapped_by_filelock__ = True  # type: ignore[attr-defined]
    return wrapper


def serialize_policy_writers() -> None:
    """Put the ticket queue's and the operator desk's appends under the lock too, from outside.

    Those two writers live in agent/policy/, whose files eval/fingerprint.py hashes: editing them invalidates the committed
    evaluation reports, and they can only be regenerated against the full warehouse. So instead of editing them, their write
    methods are wrapped here (idempotently), and the API calls this at start-up. When they are next edited on purpose, they can
    call `append_line` (or wrap their write in `locked(self.path)`) themselves, and this wrapper can go.
    """
    from agent.policy.desk import TicketDesk
    from agent.policy.escalation import HumanQueue

    for cls, name in ((HumanQueue, "enqueue"), (TicketDesk, "_record")):
        method = getattr(cls, name)
        if not getattr(method, "__wrapped_by_filelock__", False):
            setattr(cls, name, _serialized(method))
