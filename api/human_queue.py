"""What the operator's queue lists: the latest tickets plus every ticket that still needs a person, however old.

A ticket that is open or claimed is work nobody has decided; if it fell off with its age, nobody would see it. Approved,
rejected, handed back and stale ones are history, so only the latest of those travel. The desk file is read once for the
whole list (not once per ticket), and each ticket's state is still replayed by `TicketDesk.state`, so versions, stale and
history mean exactly what they do everywhere else.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from agent.policy.desk import TERMINAL, TicketDesk


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
    tickets = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    recent_from = max(len(tickets) - limit, 0)
    rows = []
    for position, ticket in enumerate(tickets):
        state = snapshot.state(ticket["ticket_id"])
        if position >= recent_from or state["status"] not in TERMINAL:
            rows.append({**ticket, "desk": state})
    return rows
