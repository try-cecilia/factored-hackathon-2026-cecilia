"""What the operator's queue lists: the latest tickets plus every ticket that still needs a person, however old.

A ticket that is open or claimed is work nobody has decided; if it fell off with its age, nobody would see it. Approved,
rejected, handed back and stale ones are history, so only the latest of those travel. The desk file is read once for the
whole list (not once per ticket), and each ticket's state is still replayed by `TicketDesk.state`, so versions, stale and
history mean exactly what they do everywhere else.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from agent import observability
from agent.policy.desk import TERMINAL, TicketDesk

logger = logging.getLogger(__name__)


class _DeskSnapshot(TicketDesk):
    """The desk as one read of its file saw it: `state()` is the parent's, only where the events come from changes."""

    def __init__(self, path: Path):
        super().__init__()
        self._by_ticket: dict[str, list[dict]] = defaultdict(list)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    event = json.loads(line)
                    self._by_ticket[event["ticket_id"]].append(event)

    def _events(self, ticket_id: str) -> list[dict]:
        return self._by_ticket.get(ticket_id, [])


def listing(queue_path: Path, desk: TicketDesk, limit: int) -> list[dict]:
    """The queue's tickets, oldest first, each with its desk state: the last `limit`, plus all that are not terminal."""
    if not queue_path.exists():
        return []
    snapshot = _DeskSnapshot(desk.path)
    tickets = _readable(queue_path)
    recent_from = max(len(tickets) - limit, 0)
    rows = []
    for position, ticket in enumerate(tickets):
        state = snapshot.state(ticket["ticket_id"])
        if position >= recent_from or state["status"] not in TERMINAL:
            rows.append({**ticket, "desk": state})
    return rows


def _readable(queue_path: Path) -> list[dict]:
    """The queue's tickets that parse. A line that does not (a torn write, a bad edit) is counted and logged by its number, never
    by its content, and must not take the whole queue down; the desk's file is not treated this way, its events decide state."""
    tickets = []
    for number, line in enumerate(queue_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            ticket = json.loads(line)
            ticket["ticket_id"]
        except (ValueError, TypeError, KeyError):
            observability.count_failure("queue_line_unreadable")
            logger.warning("a line of the ticket queue is unreadable and was skipped: line %d", number)
            continue
        tickets.append(ticket)
    return tickets
