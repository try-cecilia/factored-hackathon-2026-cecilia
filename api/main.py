"""FastAPI surface for the Account/Payment Inquiries agent.

Two things this API deliberately does NOT do, both on purpose:
- It never accepts a customer_id on the /chat endpoint — only a session
  token. /auth/session is the one place a customer_id is exchanged for a
  token, standing in for "the bank's real login/IVR already authenticated
  this person" (see agent/session/auth.py's docstring).
- It exposes /admin/human_queue and /admin/audit_log read-only, purely so a
  demo/judge can see the escalation handoff and tracing artifacts this
  system produces, without needing to open the JSONL files directly.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent.core.orchestrator import default_orchestrator
from agent.session.auth import default_store

app = FastAPI(title="LATAM Bank — Account/Payment Inquiries Agent")


class SessionRequest(BaseModel):
    customer_id: str


class SessionResponse(BaseModel):
    token: str
    customer_id: str
    expires_at: float


class ChatRequest(BaseModel):
    session_token: str
    message: str


class ChatResponse(BaseModel):
    disposition: str
    response_text: str
    ticket_id: str | None = None
    provider: str | None = None
    latency_ms: float


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/session", response_model=SessionResponse)
def create_session(req: SessionRequest) -> SessionResponse:
    """Test-only stand-in for a real login/IVR flow: issues a session token
    for a given customer_id with no further verification. A real deployment
    replaces this endpoint entirely with the bank's actual identity provider;
    downstream code only ever trusts the resulting token, never a bare id."""
    session = default_store.issue(req.customer_id)
    return SessionResponse(token=session.token, customer_id=session.customer_id, expires_at=session.expires_at)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    result = default_orchestrator.handle_message(req.session_token, req.message)
    return ChatResponse(
        disposition=result.disposition,
        response_text=result.response_text,
        ticket_id=result.ticket_id,
        provider=result.provider,
        latency_ms=result.latency_ms,
    )


@app.get("/admin/human_queue")
def human_queue(limit: int = 20) -> list[dict]:
    path = Path("data/warehouse/human_queue.jsonl")
    if not path.exists():
        return []
    lines = path.read_text().splitlines()[-limit:]
    return [json.loads(line) for line in lines]


@app.get("/admin/audit_log")
def audit_log(limit: int = 50) -> list[dict]:
    path = Path("data/warehouse/audit_log.jsonl")
    if not path.exists():
        return []
    lines = path.read_text().splitlines()[-limit:]
    return [json.loads(line) for line in lines]
