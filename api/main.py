"""HTTP surface for the Account/Payment Inquiries agent.

- /auth/session exchanges customer_id + test PIN for a short-lived token
  (agent/session/identity.py); /chat only ever accepts that token.
- /admin/* require X-Admin-Key == ADMIN_API_KEY and are disabled (503) when
  no key is configured — they expose tickets, audit and traces, which carry
  customer data.
- Input size limits and per-session / per-IP rate limits bound abuse and
  cost. /demo/customers publishes test credentials only for the sandbox
  accounts listed in DEMO_PUBLIC_CUSTOMERS (like any sandbox's test login).
- With DEMO_MODE=1 (the jury sandbox), api/demo.py adds guided scenarios, the
  bank view of the session's own tickets, fault buttons and a "why" on every
  /chat reply.
"""
from __future__ import annotations

import hmac
import json
import os
import threading
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent.llm.budget import default_budget
from agent.llm.client import default_providers
from agent.policy import intent_guard
from agent.session.auth import ExpiredSession, InvalidSession
from agent.session.identity import AuthError, IdentityUnavailable, LockedOut, default_identity, derive_test_pin
from agent.tools import account_tools
from agent.tools.audit import default_audit_log, default_trace_log
from agent.policy.desk import Conflict, DeskError, NotFound, default_desk
from agent.policy.escalation import default_queue
from api import demo

app = FastAPI(title="LATAM Bank — Account/Payment Inquiries Agent", version="2.0.0")
app.include_router(demo.router)
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
    expires_in: int  # seconds left, independent of the client's clock


class ChatRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    trace_id: str
    disposition: str
    response_text: str
    language: str
    category: str
    policy_rule: str = ""
    ticket_id: str | None = None
    latency_ms: float
    why: dict | None = None  # DEMO_MODE only: the rule, what the model received and chose, what the code verified


def client_ip(request: Request) -> str:
    """The caller's address, for per-client limits. Behind Render the peer is one of its internal proxies and the
    real address comes in CF-Connecting-IP, set by its Cloudflare edge, which no client can forge (measured
    2026-09-27; Render sends no X-Forwarded-For). Anywhere else that header is the client's own words, so it is
    read only when CLIENT_IP_HEADER names it."""
    header = os.environ.get("CLIENT_IP_HEADER")
    return (header and request.headers.get(header)) or (request.client.host if request.client else "unknown")


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
            "llm_budget_exhausted": default_budget.exhausted(),
            "intent_classifier_loaded": intent_guard.read("hola").model_available}


@app.post("/auth/session", response_model=SessionResponse)
def create_session(req: SessionRequest, request: Request) -> SessionResponse:
    if not login_limiter.allow(client_ip(request)):
        raise HTTPException(429, "too many login attempts")
    try:
        s = default_identity.login(req.customer_id, req.pin)
    except IdentityUnavailable:
        raise HTTPException(503, "identity service not configured") from None
    except LockedOut:
        raise HTTPException(429, "too many failed attempts; try later") from None
    except AuthError:
        raise HTTPException(401, "invalid credentials") from None
    return SessionResponse(token=s.token, session_ref=s.ref, expires_at=s.expires_at, expires_in=round(s.expires_at - s.issued_at))


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not chat_limiter.allow(req.session_token):
        raise HTTPException(429, "rate limit exceeded for this session")
    r = demo.orchestrator_for(req.session_token).handle_message(req.session_token, req.message)
    shown = demo.enabled()  # which rule decided is for the trace log; outside the jury demo it would guide an attacker
    return ChatResponse(trace_id=r.trace_id, disposition=r.disposition, response_text=r.response_text,
                        language=r.language, category=r.category, policy_rule=r.policy_rule if shown else "",
                        ticket_id=r.ticket_id, latency_ms=round(r.latency_ms, 1),
                        why=demo.explain(r, req.session_token) if shown else None)


@app.get("/case/{ticket_id}")
def case_status(ticket_id: str, x_session_token: str | None = Header(default=None)) -> dict:
    """Where the customer's own ticket stands (claimed, approved, rejected...). Someone else's ticket is a 404."""
    try:
        found = demo.orchestrator_for(x_session_token or "").case_status(x_session_token or "", ticket_id)
    except (InvalidSession, ExpiredSession):
        raise HTTPException(401, "invalid or expired session") from None
    if found is None:
        raise HTTPException(404, "case not found")
    return found


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
    return [{**t, "desk": default_desk.state(t["ticket_id"])} for t in _tail(default_queue.path, min(limit, 200))]


class DeskAction(BaseModel):
    operator: str = Field(min_length=1, max_length=80)
    expected_version: int | None = None  # the version the operator saw; a newer one refuses the decision
    reason: str | None = Field(default=None, max_length=300)


@app.get("/admin/tickets/{ticket_id}", dependencies=[Depends(require_admin)])
def ticket(ticket_id: str) -> dict:
    found = default_queue.get(ticket_id)
    if found is None:
        raise HTTPException(404, "ticket not found")
    return {**found, "desk": default_desk.state(ticket_id)}


@app.post("/admin/tickets/{ticket_id}/{action}", dependencies=[Depends(require_admin)])
def ticket_action(ticket_id: str, action: Literal["claim", "approve", "reject", "release"], body: DeskAction) -> dict:
    """An operator takes a ticket, approves or rejects the action it carries, or hands the conversation back."""
    try:
        return default_desk.act(ticket_id, action, body.operator, body.expected_version, body.reason)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from None
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except DeskError as exc:
        raise HTTPException(400, str(exc)) from None


@app.get("/admin/audit_log", dependencies=[Depends(require_admin)])
def audit_log(limit: int = 50) -> list[dict]:
    return _tail(default_audit_log.path, min(limit, 500))


@app.get("/admin/trace_log", dependencies=[Depends(require_admin)])
def trace_log(limit: int = 500) -> list[dict]:
    """The last turns' trace records, oldest first: what a review of the live demo reads (docs/red_team.md)."""
    return _tail(default_trace_log.path, min(max(limit, 1), 5000))


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


@app.get("/admin/ops", dependencies=[Depends(require_admin)])
def ops(limit: int = 1000) -> dict:
    """What an operator watches while the demo is live, from the last turns' trace records (docs/operations.md)."""
    rows = _tail(default_trace_log.path, min(max(limit, 1), 5000))
    rules = [str(r.get("policy_rule") or "") for r in rows]
    lat = sorted(float(r.get("latency_ms") or 0) for r in rows)
    pct = lambda p: round(lat[min(len(lat) - 1, int(round(p * (len(lat) - 1))))], 1) if lat else None  # noqa: E731
    return {
        "turns": len(rows), "from_ts": rows[0].get("ts") if rows else None, "to_ts": rows[-1].get("ts") if rows else None,
        "dispositions": dict(Counter(r.get("disposition") for r in rows)),
        "escalations_by_category": dict(Counter(r.get("category") for r in rows if r.get("disposition") == "ESCALATE")),
        "top_rules": dict(Counter(rules).most_common(15)),
        "degraded_turns": sum(rule.startswith("degraded:") for rule in rules),
        "llm_unavailable": sum(rule.startswith("llm_unavailable") for rule in rules),
        "handoff_unverified": sum(rule.endswith("|handoff_unverified") for rule in rules),
        "traces_opened": rules.count("action:trace_opened"),
        "llm_calls": sum(int(r.get("llm_calls") or 0) for r in rows),
        "cost_usd": round(sum(float(r["cost_usd"]) for r in rows if r.get("cost_usd") is not None), 6),
        "unpriced_turns": sum(r.get("cost_usd") is None for r in rows),
        "latency_ms_p50": pct(0.5), "latency_ms_p95": pct(0.95),
        "models": dict(Counter(f"{r.get('provider')}/{r.get('model')}" for r in rows if r.get("llm_calls"))),
        "llm_budget": llm_budget(),
    }


@app.get("/admin/llm_budget", dependencies=[Depends(require_admin)])
def llm_budget() -> dict:
    """Today's (UTC) model spend against LLM_DAILY_BUDGET_USD; past it the assistant runs in degraded mode."""
    return {"limit_usd": default_budget.limit_usd, "spent_today_usd": round(default_budget.spent_today(), 6),
            "exhausted": default_budget.exhausted()}


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
