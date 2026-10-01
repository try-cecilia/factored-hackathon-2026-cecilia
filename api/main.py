"""HTTP surface for the Account/Payment Inquiries agent.

- /auth/session exchanges customer_id + test PIN for a short-lived token
  (agent/session/identity.py); /chat only ever accepts that token. GET
  /auth/session with X-Session-Token reads the session back without extending
  it; DELETE revokes it (always 204). A web BFF holds the token and calls these.
- Behind that BFF, CLIENT_IP_HEADER=X-Client-IP makes per-IP limits use the end
  user's address, safe only when nothing but the BFF can reach the API.
- /admin/* require X-Admin-Key == ADMIN_API_KEY and are disabled (503) when
  no key is configured — they expose tickets, audit and traces, which carry
  customer data. Acting on a ticket takes an operator key instead, and /metrics
  takes the admin key or a scraper's METRICS_TOKEN. api/access.py is the matrix of
  who may call what; the service refuses to start if a route is not in it.
- /livez says the process is up, /readyz that the warehouse and state store answer
  (api/observability.py); /metrics is Prometheus text (agent/metrics.py).
- Input size limits, per-session / per-customer / per-IP rate limits and a
  concurrency gate on /chat bound abuse and cost (api/middleware.py); every
  request gets a trace id, returned as X-Request-ID and traceparent. /demo/customers publishes test credentials only for the sandbox
  accounts listed in DEMO_PUBLIC_CUSTOMERS (like any sandbox's test login).
- With DEMO_MODE=1 (the jury sandbox), api/demo.py adds guided scenarios, the
  bank view of the session's own tickets, fault buttons and a "why" on every
  /chat reply. Everything demo-only (/demo/*, /admin/demo_pin) is a 404 without it.
- Responses carry security headers and there is no CORS unless CORS_ALLOWED_ORIGINS
  names origins (api/security.py).
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import metrics
from agent.filelock import serialize_policy_writers
from agent.core.experiments import cohorts, read_log as read_shadow_log, summarize_shadow
from agent import observability
from agent.core.orchestrator import default_orchestrator
from agent.llm.budget import default_budget
from agent.llm.client import default_providers
from agent.policy import intent_guard
from agent.resilience import bounded_ops_stats, handoff_budget_seconds, request_budget_seconds, turn_budget_seconds
from agent.session.auth import ExpiredSession, InvalidSession, default_store, session_ref
from agent.session.identity import AuthError, IdentityUnavailable, LockedOut, default_identity, derive_test_pin
from agent.session.operators import OperatorDirectory
from agent.tools import account_tools
from agent.tools.audit import default_audit_log, default_trace_log
from agent.tools.traces import default_traces
from agent.policy.desk import Conflict, DeskError, NotFound, default_desk
from agent.policy.escalation import default_queue
from api import access, customer_context, demo, idempotency, middleware
from api.human_queue import listing as human_queue_listing
from api.observability import ObservabilityMiddleware, RouteTemplates, readiness
from api.security import SecurityHeadersMiddleware, configure_cors, constant_time_equals
from ops.drift import recent_rows, report as drift_report, save_baseline as save_drift_baseline

serialize_policy_writers()  # the ticket queue and the desk append under the same lock as the retention purge (agent/filelock.py)

observability.configure_logging()
# The API's schema and interactive docs are not published unless EXPOSE_API_DOCS=1 (development).
_docs = os.environ.get("EXPOSE_API_DOCS") == "1"
app = FastAPI(title="LATAM Bank — Account/Payment Inquiries Agent", version="2.0.0",
              docs_url="/docs" if _docs else None, redoc_url="/redoc" if _docs else None,
              openapi_url="/openapi.json" if _docs else None)
app.add_middleware(middleware.RequestContextMiddleware)
app.include_router(demo.router)
STATIC = Path(__file__).parent / "static"
# Outermost last: CORS answers a browser's preflight before anything else, then metrics see every request, headers go on every reply.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ObservabilityMiddleware, templates=RouteTemplates(app))
configure_cors(app)


class RateLimiter:
    """A sliding window per key, in memory: it resets on restart and is not shared between replicas (a second replica
    needs Redis). Bounded: keys that have gone quiet are dropped, and past MAX_KEYS the oldest go first."""

    MAX_KEYS = 100_000
    SWEEP_EVERY = 1_000

    def __init__(self, limit: int, window_s: float, name: str = ""):
        self.limit, self.window_s, self.name = limit, window_s, name
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def _prune(self, key: str, now: float) -> deque:
        q = self._hits[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        return q

    def _sweep(self, now: float) -> None:
        for key in [k for k, q in self._hits.items() if not q or now - q[-1] > self.window_s]:
            del self._hits[key]
        while len(self._hits) > self.MAX_KEYS:
            del self._hits[next(iter(self._hits))]

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._calls += 1
            if self._calls % self.SWEEP_EVERY == 0:
                self._sweep(now)
            q = self._prune(key, now)
            if len(q) >= self.limit:
                if self.name:
                    metrics.default.rate_limited.labels(self.name).inc()
                return False
            q.append(now)
            return True

    def over(self, key: str) -> bool:
        """Whether this key has used up its hits in the window. Looking does not count as a hit."""
        with self._lock:
            return len(self._prune(key, time.time())) >= self.limit

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.time())

    def retry_after(self, key: str) -> int:
        """Whole seconds until this key has a hit to spend again (at least 1)."""
        now = time.time()
        with self._lock:
            q = self._prune(key, now)
            return max(1, math.ceil(self.window_s - (now - q[0]))) if q else 1

    def __len__(self) -> int:
        return len(self._hits)


def too_many(limiter: "RateLimiter", key: str, detail: str) -> HTTPException:
    return HTTPException(429, detail, headers={"Retry-After": str(limiter.retry_after(key))})


chat_limiter = RateLimiter(int(os.environ.get("CHAT_RATE_PER_MIN", "20")), 60, "chat")
login_limiter = RateLimiter(int(os.environ.get("LOGIN_RATE_PER_MIN", "10")), 60, "login")
# Across every session of one customer, and from one client address. Behind the BFF the address is the end user's only
# when CLIENT_IP_HEADER is set; without it every user shares the BFF's, so the default is generous.
chat_customer_limiter = RateLimiter(int(os.environ.get("CHAT_CUSTOMER_RATE_PER_MIN", "40")), 60, "chat_customer")
chat_ip_limiter = RateLimiter(int(os.environ.get("CHAT_IP_RATE_PER_MIN", "120")), 60, "chat_ip")


class SessionRequest(BaseModel):
    customer_id: str = Field(min_length=3, max_length=32)
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class SessionResponse(BaseModel):
    token: str
    session_ref: str
    expires_at: float
    expires_in: int  # seconds left, independent of the client's clock


class SessionInfo(BaseModel):
    customer_id: str
    session_ref: str
    segment: str
    country: str
    customer_status: str
    expires_at: float
    expires_in: int


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
    degraded: bool = False  # limited mode: the model was unavailable, so the code answered alone (the screen says so)
    why: dict | None = None  # DEMO_MODE only: the rule, what the model received and chose, what the code verified


def client_ip(request: Request) -> str:
    """The caller's address, for per-client limits. Behind Render the peer is one of its internal proxies and the
    real address comes in CF-Connecting-IP, set by its Cloudflare edge, which no client can forge (measured
    2026-09-27; Render sends no X-Forwarded-For). Anywhere else that header is the client's own words, so it is
    read only when CLIENT_IP_HEADER names it."""
    header = os.environ.get("CLIENT_IP_HEADER")
    return (header and request.headers.get(header)) or (request.client.host if request.client else "unknown")


# Failed admin, metrics and operator credentials count per client address: past the limit even the right key is refused until
# the window passes, so a key cannot be guessed at line speed.
operator_fail_limiter = RateLimiter(int(os.environ.get("OPERATOR_AUTH_FAILS_PER_MIN", "10")), 60, "auth_failures")


def _refuse_if_guessing(request: Request, kind: str) -> str:
    origin = client_ip(request)
    if operator_fail_limiter.over(origin):
        metrics.default.rate_limited.labels("auth_failures").inc()
        default_audit_log.event(f"{kind}_auth_failed", origin=origin, reason="blocked")
        raise too_many(operator_fail_limiter, origin, "too many failed attempts")
    return origin


def _bad_credential(origin: str, kind: str, detail: str) -> HTTPException:
    operator_fail_limiter.record(origin)
    default_audit_log.event(f"{kind}_auth_failed", origin=origin, reason="invalid")
    return HTTPException(401, detail)


def require_admin(request: Request, x_admin_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("ADMIN_API_KEY")
    if not expected:
        raise HTTPException(503, "admin endpoints disabled: ADMIN_API_KEY not configured")
    origin = _refuse_if_guessing(request, "admin")
    if not constant_time_equals(x_admin_key, expected):
        raise _bad_credential(origin, "admin", "invalid admin key")


def require_metrics(request: Request, authorization: str | None = Header(default=None),
                    x_admin_key: str | None = Header(default=None)) -> None:
    """A scraper's bearer METRICS_TOKEN, or the admin key (as a bearer or in X-Admin-Key). The token opens only this endpoint."""
    keys = [k for k in (os.environ.get("METRICS_TOKEN"), os.environ.get("ADMIN_API_KEY")) if k]
    if not keys:
        raise HTTPException(503, "metrics disabled: neither METRICS_TOKEN nor ADMIN_API_KEY is configured")
    origin = _refuse_if_guessing(request, "metrics")
    scheme, _, bearer = (authorization or "").partition(" ")
    presented = [x_admin_key, bearer.strip() if scheme.lower() == "bearer" else None]
    ok = False
    for candidate in presented:
        for key in keys:  # every pair is compared, with no early exit
            ok |= constant_time_equals(candidate, key)
    if not ok:
        raise _bad_credential(origin, "metrics", "invalid metrics credentials")


OperatorDirectory.from_env()  # a bad OPERATOR_KEYS stops the service from starting, rather than failing at the first request


def require_operator(request: Request, x_operator_key: str | None = Header(default=None)) -> str:
    """The authenticated operator's name, from the key they present: never from anything they send. Only failures
    count against the limit; once over it, even the right key is refused until the window passes."""
    directory = OperatorDirectory.from_env()
    if not directory.enabled:
        raise HTTPException(503, "operator endpoints disabled: OPERATOR_KEYS not configured")
    origin = _refuse_if_guessing(request, "operator")
    name = directory.authenticate(x_operator_key)
    if name is None:
        raise _bad_credential(origin, "operator", "invalid operator key")
    return name


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
            "llm_providers_configured": [p.name for p in default_providers() if p.configured()],
            "llm_budget_exhausted": default_budget.exhausted(),
            "intent_classifier_loaded": intent_guard.read("hola").model_available}


@app.get("/livez")
def livez() -> dict:
    """The process is up and answering. Says nothing about its dependencies: a restart cannot fix those (see /readyz)."""
    return {"status": "alive"}


@app.get("/readyz")
def readyz(response: Response) -> dict:
    """Whether to send this instance traffic: the warehouse, the state store and the data directory all answer."""
    checks = readiness()
    ready = all(checks.values())
    response.status_code = 200 if ready else 503
    return {"status": "ready" if ready else "not_ready", "checks": checks}


@app.get("/metrics", dependencies=[Depends(require_metrics)])
def prometheus_metrics() -> Response:
    """Prometheus text format (agent/metrics.py). Admin key, or the scraper's METRICS_TOKEN as a bearer."""
    return Response(metrics.default.render(), media_type=metrics.CONTENT_TYPE)


@app.post("/auth/session", response_model=SessionResponse)
def create_session(req: SessionRequest, request: Request) -> SessionResponse:
    origin = client_ip(request)
    if not login_limiter.allow(origin):
        metrics.default.logins.labels("rate_limited").inc()
        raise too_many(login_limiter, origin, "too many login attempts")
    try:
        s = default_identity.login(req.customer_id, req.pin)
    except IdentityUnavailable:
        metrics.default.logins.labels("unavailable").inc()
        raise HTTPException(503, "identity service not configured") from None
    except LockedOut:
        metrics.default.logins.labels("locked_out").inc()
        raise HTTPException(429, "too many failed attempts; try later") from None
    except AuthError:
        metrics.default.logins.labels("invalid").inc()
        raise HTTPException(401, "invalid credentials") from None
    metrics.default.logins.labels("ok").inc()
    return SessionResponse(token=s.token, session_ref=s.ref, expires_at=s.expires_at, expires_in=round(s.expires_at - s.issued_at))


@app.get("/auth/session", response_model=SessionInfo)
def read_session(x_session_token: str | None = Header(default=None)) -> SessionInfo:
    """Who the token belongs to and how long it has left. Reading does not extend it."""
    try:
        s = default_store.validate(x_session_token or "")
    except (InvalidSession, ExpiredSession):
        raise HTTPException(401, "invalid or expired session") from None
    return SessionInfo(customer_id=s.customer_id, session_ref=s.ref, segment=s.attributes.get("segment", ""),
                       country=s.attributes.get("country", ""), customer_status=s.attributes.get("customer_status", ""),
                       expires_at=s.expires_at, expires_in=max(0, round(s.expires_at - time.time())))


@app.delete("/auth/session", status_code=204)
def end_session(x_session_token: str | None = Header(default=None)) -> Response:
    """Logout. Always 204, so an unknown or already revoked token is not an error."""
    if x_session_token:
        default_orchestrator.conversations.clear_transcript(session_ref(x_session_token))
        default_store.revoke(x_session_token)
    return Response(status_code=204)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, response: Response,
         idempotency_key: str | None = Header(default=None)) -> ChatResponse:
    """One turn. With an Idempotency-Key, a retry of the same message returns the stored reply instead of a new turn."""
    if idempotency_key is None:
        return _chat_turn(req, request)
    if not idempotency.KEY_PATTERN.match(idempotency_key):
        raise HTTPException(422, "Idempotency-Key must be 8-64 characters of letters, digits, - or _")
    session = _live_session(req.session_token)
    if session is None:  # nothing stored is shown to a session that is over
        return _chat_turn(req, request)  # the usual REAUTH_REQUIRED reply
    try:
        with idempotency.default.guard(session_ref(req.session_token), idempotency_key, req.message,
                                       session.expires_at) as slot:
            if slot.replay is not None or slot.processed:
                if _live_session(req.session_token) is None:  # it ended while this retry waited for the first turn
                    return _chat_turn(req, request)
                if slot.replay is None:  # it ran, but the table filled up and its reply was dropped
                    raise HTTPException(409, "already processed: this message was received, its reply is no longer kept")
                response.headers["Idempotent-Replayed"] = "true"  # a replay is not a new turn: no chat-limit hit
                stored = ChatResponse.model_validate_json(slot.replay)
                # Stored whole; what the caller may see is decided now, not when the turn ran.
                return stored if demo.enabled() else stored.model_copy(update={"why": None, "policy_rule": ""})
            _admit(req, request)  # a refusal here ran nothing: the key's place is given back
            slot.begin()  # POINT OF NO RETURN: from here the turn may have effects (a ticket, a trace), so whatever
            reply = _run_turn(req)  # happens next, an error included, the key stays taken and a retry gets a 409
            if reply.disposition == "REAUTH_REQUIRED":  # the session ended first: nothing ran, answered afresh after login
                slot.abandon()
            else:
                slot.save(reply.model_dump_json())
            return reply
    except idempotency.KeyReused:
        raise HTTPException(422, "Idempotency-Key was already used with a different message") from None
    except idempotency.CapacityFull as full:  # refused before the turn ran: nothing changed, the client may retry
        raise HTTPException(503, "too many turns in flight for the idempotency store; retry shortly",
                            headers={"Retry-After": str(full.retry_after)}) from None


def _live_session(token: str):
    try:
        return default_store.validate(token)
    except (InvalidSession, ExpiredSession):
        return None


def _chat_turn(req: ChatRequest, request: Request) -> ChatResponse:
    _admit(req, request)
    return _run_turn(req)


def _admit(req: ChatRequest, request: Request) -> None:
    """Everything that can refuse a turn before it starts. Nothing has run when this raises."""
    origin = client_ip(request)
    if not chat_ip_limiter.allow(origin):
        raise too_many(chat_ip_limiter, origin, "rate limit exceeded for this address")
    if not chat_limiter.allow(req.session_token):
        raise too_many(chat_limiter, req.session_token, "rate limit exceeded for this session")
    try:  # a customer opening many sessions shares one limit; a bad token is answered by the orchestrator as usual
        customer = default_store.validate(req.session_token).customer_id
    except (InvalidSession, ExpiredSession):
        customer = None
    if customer and not chat_customer_limiter.allow(customer):
        raise too_many(chat_customer_limiter, customer, "rate limit exceeded for this customer")


def _run_turn(req: ChatRequest) -> ChatResponse:
    r = demo.orchestrator_for(req.session_token).handle_message(req.session_token, req.message)
    shown = demo.enabled()  # which rule decided is for the trace log; outside the jury demo it would guide an attacker
    return ChatResponse(trace_id=r.trace_id, disposition=r.disposition, response_text=r.response_text,
                        language=r.language, category=r.category, policy_rule=r.policy_rule if shown else "",
                        ticket_id=r.ticket_id, latency_ms=round(r.latency_ms, 1), degraded=r.degraded,
                        why=demo.explain(r, req.session_token) if shown else None)


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    at: float
    trace_id: str | None = None
    disposition: str | None = None
    category: str | None = None
    language: str | None = None
    ticket_id: str | None = None
    degraded: bool = False


class HistoryCase(BaseModel):
    ticket_id: str
    category: str
    at: float


class History(BaseModel):
    turns: list[HistoryTurn]
    cases: list[HistoryCase]  # the session's handoffs; they outlive the bounded turns that opened them


@app.get("/chat/history", response_model=History, response_model_exclude_none=True)
def chat_history(x_session_token: str | None = Header(default=None)) -> History:
    """The live session's conversation as the customer saw it: their words (card numbers masked) and the rendered replies,
    oldest first, and the cases the session opened. Read only; no model data, no rule, no `why`. Another session's is never
    reachable: the key is the token's."""
    orchestrator = demo.orchestrator_for(x_session_token or "")
    try:
        turns = orchestrator.history(x_session_token or "")
        cases = orchestrator.case_index(x_session_token or "")
    except (InvalidSession, ExpiredSession):
        raise HTTPException(401, "invalid or expired session") from None
    return History(turns=[HistoryTurn(**turn) for turn in turns], cases=[HistoryCase(**case) for case in cases])


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


@app.get("/demo/customers", dependencies=[Depends(demo.require_demo)])
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
    """The latest `limit` tickets (at most 200) and, however old, every one still open or claimed: work nobody decided does not age out."""
    return human_queue_listing(default_queue.path, default_desk, max(min(limit, 200), 0))


class DeskAction(BaseModel):
    expected_version: int | None = None  # the version the operator saw; a newer one refuses the decision
    reason: str | None = Field(default=None, max_length=300)  # reject: a note for the other operators, never the customer
    message: str | None = Field(default=None, max_length=500)  # resolve: what the customer reads (one line, card numbers masked)


@app.get("/admin/operator/me")
def operator_me(operator: str = Depends(require_operator)) -> dict:
    """Who the presented operator key belongs to, without touching any ticket: how the web BFF checks a key at login."""
    return {"operator": operator}


@app.get("/admin/tickets/{ticket_id}", dependencies=[Depends(require_admin)])
def ticket(ticket_id: str) -> dict:
    found = default_queue.get(ticket_id)
    if found is None:
        raise HTTPException(404, "ticket not found")
    return {**found, "desk": default_desk.state(ticket_id)}


@app.get("/admin/tickets/{ticket_id}/customer_context", dependencies=[Depends(require_admin)])
def ticket_customer_context(ticket_id: str) -> dict:
    """The case's customer, read-only: products (masked), latest movements, other cases and trace requests. See api/customer_context.py."""
    found = default_queue.get(ticket_id)
    if found is None:
        raise HTTPException(404, "ticket not found")
    return customer_context.for_ticket(found, default_queue, default_desk, default_traces)


@app.post("/admin/tickets/{ticket_id}/{action}")
def ticket_action(ticket_id: str, action: Literal["claim", "approve", "reject", "release", "resolve"], body: DeskAction,
                  operator: str = Depends(require_operator)) -> dict:
    """An operator takes a ticket, approves or rejects the action it carries, resolves one that carries none with a
    message for the customer, or hands the conversation back. Who acted is the name of the key they presented; the
    body cannot say otherwise."""
    try:
        return default_desk.act(ticket_id, action, operator, body.expected_version, body.reason, body.message)
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


@app.get("/admin/drift", dependencies=[Depends(require_admin)])
def drift(limit: int = 500) -> dict:
    """The recent traffic against the frozen reference (ops/drift.py): language, intents, confidence, dispositions."""
    return drift_report(min(max(limit, 1), 5000))


@app.post("/admin/drift/snapshot", dependencies=[Depends(require_admin)])
def drift_snapshot(limit: int = 500) -> dict:
    """Freeze the last turns as the reference. Only counts are kept: no traces, no customer data."""
    snap = save_drift_baseline(recent_rows(min(max(limit, 1), 5000)))
    return {"n": snap["n"], "created_at": snap["created_at"]}


@app.get("/admin/experiments", dependencies=[Depends(require_admin)])
def experiments_report(limit: int = 500) -> dict:
    """Shadow and canary (agent/core/experiments.py): the candidate against the usual model, and what each cohort got."""
    limit = min(max(limit, 1), 5000)
    return {"shadow": summarize_shadow(read_shadow_log(default_orchestrator.experiments.log_path, limit)),
            "cohorts": cohorts(recent_rows(limit)),
            "config": {"canary_percent": default_orchestrator.experiments.canary_percent,
                       "shadow_enabled": default_orchestrator.experiments.shadow_enabled,
                       "canary_enabled": default_orchestrator.experiments.canary_enabled}}


@app.get("/admin/capacity", dependencies=[Depends(require_admin)])
def capacity() -> dict:
    """The limits in force and how often they have refused a request since the process started (docs/operations.md)."""
    return {"limits": {**middleware.limits(),
                       "chat_per_min": {"session": chat_limiter.limit, "customer": chat_customer_limiter.limit,
                                        "address": chat_ip_limiter.limit},
                       "login_per_min": login_limiter.limit, "turn_budget_seconds": turn_budget_seconds(),
                       "handoff_budget_seconds": handoff_budget_seconds(), "request_budget_seconds": request_budget_seconds(),
                       "llm_session_budget_usd": default_orchestrator.session_budget.limit_usd},
            "state": middleware.stats.snapshot(), "failures": observability.failure_counts(), "bounded_ops": bounded_ops_stats(),
            "rate_limiter_keys": {"session": len(chat_limiter), "customer": len(chat_customer_limiter), "address": len(chat_ip_limiter)}}


@app.get("/admin/llm_budget", dependencies=[Depends(require_admin)])
def llm_budget() -> dict:
    """Today's (UTC) model spend against LLM_DAILY_BUDGET_USD; past it the assistant runs in degraded mode."""
    return {"limit_usd": default_budget.limit_usd, "spent_today_usd": round(default_budget.spent_today(), 6),
            "exhausted": default_budget.exhausted()}


@app.get("/admin/demo_pin/{customer_id}", dependencies=[Depends(demo.require_demo), Depends(require_admin)])
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


access.check_app(app)  # a route with no row in api/access.py stops the service from starting
