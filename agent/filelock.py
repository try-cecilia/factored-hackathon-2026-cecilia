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
import time
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
def locked(path: str | os.PathLike, timeout: float | None = None) -> Iterator[None]:
    """Hold the exclusive lock of `path` (the data file's own path, not the lock's) for the block.

    Without `timeout` it waits as long as it takes. With one it tries without blocking, again every few milliseconds, and
    raises TimeoutError once `timeout` seconds have passed (0 = try once): what a writer with a deadline uses, so a lock held by
    another process, or by a purge, cannot hold its turn past its budget."""
    if fcntl is None:  # pragma: no cover
        yield
        return
    lock = lock_path(path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if timeout is None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            give_up = time.monotonic() + max(0.0, timeout)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= give_up:
                        raise TimeoutError(f"could not take the lock of {Path(path).name} within {timeout:.2f}s") from None
                    time.sleep(min(0.005, max(0.0, give_up - time.monotonic())))
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
    """Put the operator desk's appends under the lock too, from outside.

    The desk lives in agent/policy/, whose files eval/fingerprint.py hashes: editing them invalidates the committed
    evaluation reports, and they can only be regenerated against the full warehouse. So instead of editing it, its write
    method is wrapped here (idempotently), and the API calls this at start-up. When it is next edited on purpose, it can
    call `append_line` (or wrap its write in `locked(self.path)`) itself, and this wrapper can go.

    The ticket queue is no longer wrapped: `HumanQueue.enqueue` takes the lock itself, with a timeout, inside the handoff's
    budget (a wrapper cannot bound a wait it does not know the budget of).
    """
    from agent.policy.desk import TicketDesk

    for cls, name in ((TicketDesk, "_record"),):
        method = getattr(cls, name)
        if not getattr(method, "__wrapped_by_filelock__", False):
            setattr(cls, name, _serialized(method))
