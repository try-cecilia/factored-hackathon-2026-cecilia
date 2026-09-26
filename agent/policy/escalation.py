"""Structured human handoff.

Per the brief: "Provide the human agent with the request, verified facts,
actions taken, supporting evidence, and unresolved questions" — never a raw
transcript dump. This module builds that object and writes it to a mock
human queue (a JSONL file standing in for a real ticketing system / CRM).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agent.policy.router import Decision


@dataclass
class EscalationTicket:
    ticket_id: str
    created_at: float
    customer_id: str
    session_token: str
    original_request: str
    reason: str
    verified_facts: dict[str, Any]
    actions_taken: list[dict[str, Any]]
    open_questions: list[str]
    language: str = "es"
    priority: str = "Medium"


class HumanQueue:
    def __init__(self, path: str | None = None):
        self.path = Path(path or os.environ.get("HUMAN_QUEUE_PATH", "data/warehouse/human_queue.jsonl"))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def enqueue(self, ticket: EscalationTicket) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps(asdict(ticket), default=str) + "\n")


default_queue = HumanQueue()


def build_ticket(
    customer_id: str,
    session_token: str,
    original_request: str,
    decision: Decision,
    actions_taken: list[dict[str, Any]],
    language: str = "es",
) -> EscalationTicket:
    priority = "Critical" if any(
        kw in original_request.lower() for kw in ("fraude", "robaron", "clonaron", "roubaram", "roubo")
    ) else "Medium"
    return EscalationTicket(
        ticket_id=str(uuid.uuid4()),
        created_at=time.time(),
        customer_id=customer_id,
        session_token=session_token,
        original_request=original_request,
        reason=decision.reason,
        verified_facts=decision.verified_facts,
        actions_taken=actions_taken,
        open_questions=decision.open_questions,
        language=language,
        priority=priority,
    )


def escalate(
    customer_id: str,
    session_token: str,
    original_request: str,
    decision: Decision,
    actions_taken: list[dict[str, Any]],
    language: str = "es",
) -> EscalationTicket:
    ticket = build_ticket(customer_id, session_token, original_request, decision, actions_taken, language)
    default_queue.enqueue(ticket)
    return ticket
