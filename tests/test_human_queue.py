"""What the operator's queue endpoint returns: the latest tickets, and every ticket that still needs a person however old it is.

The queue and the desk are JSONL files written here directly (the tickets carry only what the endpoint reads), and the
operator moves go through the real desk, so the states are the ones `TicketDesk.state` replays.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.policy.desk import default_desk
from api import main

ADMIN = {"X-Admin-Key": "test-admin-key"}
TOTAL = 260  # more than the 200 the console asks for


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("HUMAN_QUEUE_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("HUMAN_DESK_PATH", str(tmp_path / "desk.jsonl"))


def ticket(n: int) -> dict:
    return {"ticket_id": f"T-{n:04d}", "created_at": 1000.0 + n, "queue": "payments_ops", "priority": "High", "customer_id": "CLI-FIX0001",
            "category": "fraud", "country": "México", "language": "es", "request": f"caso {n}", "pending_action": None}


def fill_queue(total: int = TOTAL) -> None:
    lines = (json.dumps(ticket(n)) for n in range(total))
    Path(main.default_queue.path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def ids(rows: list[dict]) -> list[str]:
    return [t["ticket_id"] for t in rows]


def queue(limit: int = 200) -> list[dict]:
    return TestClient(main.app).get(f"/admin/human_queue?limit={limit}", headers=ADMIN).json()


def test_an_old_open_or_claimed_ticket_is_still_in_the_queue_past_the_latest_200():
    fill_queue()
    default_desk.act("T-0000", "claim", "ana")  # the oldest, taken and never decided
    default_desk.act("T-0003", "claim", "ana")
    default_desk.act("T-0003", "release", "ana")  # an old one already closed

    listed = ids(queue())
    assert "T-0000" in listed and "T-0001" in listed  # claimed and open, oldest of all
    assert "T-0003" not in listed  # a closed one falls off with the age
    assert listed[-200:] == [f"T-{n:04d}" for n in range(TOTAL - 200, TOTAL)]  # the latest are all there
    assert listed == sorted(listed)  # oldest first, as the file has them


def test_every_ticket_that_needs_a_person_arrives_and_a_closed_old_one_does_not():
    fill_queue()
    for n in range(0, 50):  # the oldest 50 are decided
        default_desk.act(f"T-{n:04d}", "claim", "ana")
        default_desk.act(f"T-{n:04d}", "release", "ana")
    default_desk.act("T-0050", "claim", "ben")

    listed = ids(queue())
    assert len(listed) == TOTAL - 50  # nothing pending was dropped, nothing closed and old was kept
    assert listed[0] == "T-0050" and "T-0049" not in listed


def test_a_small_limit_returns_the_latest_plus_everything_pending():
    fill_queue()
    default_desk.act("T-0002", "claim", "ana")
    default_desk.act("T-0002", "release", "ana")
    listed = ids(queue(limit=5))
    assert listed[-5:] == [f"T-{n:04d}" for n in range(TOTAL - 5, TOTAL)]
    assert len(listed) == TOTAL - 1  # the rest are pending, and one is closed


def test_each_row_carries_exactly_the_state_the_desk_replays():
    fill_queue(30)
    default_desk.act("T-0004", "claim", "ana")
    default_desk.act("T-0007", "claim", "ana")
    default_desk.act("T-0007", "reject", "ana", reason="no")
    default_desk.act("T-0009", "claim", "ben")
    for row in queue():
        assert row["desk"] == default_desk.state(row["ticket_id"])


def test_the_desk_file_is_read_once_for_the_whole_queue(monkeypatch):
    fill_queue(30)
    default_desk.act("T-0004", "claim", "ana")
    reads = []
    real = Path.read_text

    def counting(self, *args, **kwargs):
        if self == default_desk.path:
            reads.append(self)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    assert len(queue()) == 30
    assert len(reads) == 1


def test_an_empty_queue_and_a_queue_with_no_desk_events():
    assert queue() == []
    fill_queue(3)
    rows = queue()
    assert [r["desk"]["status"] for r in rows] == ["open"] * 3 and all(r["desk"]["version"] == 0 for r in rows)
