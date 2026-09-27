"""HTTP surface for the Account/Payment Inquiries agent.

- /auth/session exchanges customer_id + test PIN for a short-lived token
  (agent/session/identity.py); /chat only ever accepts that token.
- /admin/* require X-Admin-Key == ADMIN_API_KEY and are disabled (503) when
  no key is configured — they expose tickets, audit and traces, which carry
  customer data.
- Input size limits and per-session / per-IP rate limits bound abuse and
  cost. /demo/customers publishes test credentials only for the sandbox
  accounts listed in DEMO_PUBLIC_CUSTOMERS (like any sandbox's test login).
"""
from __future__ import annotations

import hmac
import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent.core.orchestrator import default_orchestrator
from agent.llm.client import default_providers
from agent.policy import intent_guard
from agent.session.identity import AuthError, IdentityUnavailable, LockedOut, default_identity, derive_test_pin
from agent.tools import account_tools
from agent.tools.audit import default_audit_log, default_trace_log
from agent.policy.escalation import default_queue

app = FastAPI(title="LATAM Bank — Account/Payment Inquiries Agent", version="2.0.0")
STATIC = Path(__file__).parent / "static"


class RateLimiter:
    def __init__(self, limit: int, window_s: float):
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


chat_limiter = RateLimiter(int(os.environ.get("CHAT_RATE_PER_MIN", "20")), 60)
login_limiter = RateLimiter(int(os.environ.get("LOGIN_RATE_PER_MIN", "10")), 60)


class SessionRequest(BaseModel):
    customer_id: str = Field(min_length=3, max_length=32)
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class SessionResponse(BaseModel):
    token: str
    session_ref: str
    expires_at: float


class ChatRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    trace_id: str
    disposition: str
    response_text: str
    language: str
    category: str
    ticket_id: str | None = None
    latency_ms: float


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("ADMIN_API_KEY")
    if not expected:
        raise HTTPException(503, "admin endpoints disabled: ADMIN_API_KEY not configured")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(401, "invalid admin key")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health() -> dict:
    try:
        as_of = str(account_tools.data_as_of())
    except Exception as exc:  # noqa: BLE001
        as_of = f"unavailable: {type(exc).__name__}"
    return {"status": "ok", "data_as_of": as_of,
            "llm_providers_configured": [p.name for p in default_providers() if os.environ.get(p.api_key_env)],
            "intent_classifier_loaded": intent_guard.read("hola").model_available}


@app.post("/auth/session", response_model=SessionResponse)
def create_session(req: SessionRequest, request: Request) -> SessionResponse:
    if not login_limiter.allow(request.client.host if request.client else "unknown"):
        raise HTTPException(429, "too many login attempts")
    try:
        s = default_identity.login(req.customer_id, req.pin)
    except IdentityUnavailable:
        raise HTTPException(503, "identity service not configured") from None
    except LockedOut:
        raise HTTPException(429, "too many failed attempts; try later") from None
    except AuthError:
        raise HTTPException(401, "invalid credentials") from None
    return SessionResponse(token=s.token, session_ref=s.ref, expires_at=s.expires_at)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not chat_limiter.allow(req.session_token):
        raise HTTPException(429, "rate limit exceeded for this session")
    r = default_orchestrator.handle_message(req.session_token, req.message)
    return ChatResponse(trace_id=r.trace_id, disposition=r.disposition, response_text=r.response_text,
                        language=r.language, category=r.category, ticket_id=r.ticket_id,
                        latency_ms=round(r.latency_ms, 1))


@app.get("/demo/customers")
def demo_customers() -> list[dict]:
    ids = [c.strip() for c in os.environ.get("DEMO_PUBLIC_CUSTOMERS", "").split(",") if c.strip()]
    try:
        return [{"customer_id": c, "test_pin": derive_test_pin(c)} for c in ids]
    except IdentityUnavailable:
        return []


def _tail(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[-limit:]]


@app.get("/admin/human_queue", dependencies=[Depends(require_admin)])
def human_queue(limit: int = 20) -> list[dict]:
    return _tail(default_queue.path, min(limit, 200))


@app.get("/admin/audit_log", dependencies=[Depends(require_admin)])
def audit_log(limit: int = 50) -> list[dict]:
    return _tail(default_audit_log.path, min(limit, 500))


@app.get("/admin/traces/{trace_id}", dependencies=[Depends(require_admin)])
def trace(trace_id: str) -> dict:
    """A full trace id, or the 8-character code a customer was given when a handoff could not be filed."""
    trace_id = trace_id.strip().lower()  # trace ids are lowercase hex; a customer may read the code out in capitals
    if len(trace_id) < 8:
        raise HTTPException(404, "trace not found")
    for rec in reversed(_tail(default_trace_log.path, 5000)):
        if str(rec.get("trace_id", "")).startswith(trace_id):
            rec["tool_audit"] = [a for a in _tail(default_audit_log.path, 5000) if a.get("trace_id") == rec["trace_id"]]
            return rec
    raise HTTPException(404, "trace not found")


@app.get("/admin/demo_pin/{customer_id}", dependencies=[Depends(require_admin)])
def demo_pin(customer_id: str) -> dict:
    return {"customer_id": customer_id, "test_pin": derive_test_pin(customer_id)}


@app.get("/admin/data_quality", dependencies=[Depends(require_admin)])
def data_quality() -> dict:
    path = Path(os.environ.get("DQ_REPORT_PATH", "data/reports/quality_report.json"))
    if not path.exists():
        raise HTTPException(404, "no quality report")
    rep = json.loads(path.read_text(encoding="utf-8"))
    return {k: rep[k] for k in ("run_id", "contract_version", "summary", "tables", "contract_deviations") if k in rep} | {
        "failed_checks": [c for c in rep["checks"] if c["passed"] is False]}
