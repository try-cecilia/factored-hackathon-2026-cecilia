"""The jury demo's console: a visitor who signed in as a public sandbox customer resolves, as the bank, the cases that same
session filed, without an operator key.

Only with DEMO_MODE=1 and DEMO_CONSOLE=1, each exactly "1": with anything else every request under /demo/desk is the same 404
as a route that does not exist, whatever its method or body (`ConsoleSwitch`, which answers before routing and before the body
is parsed; the routes' own dependencies stay, for the access matrix). There is no operator session: the credential is the customer's session token (X-Session-Token), and it opens
these routes only for an account in DEMO_PUBLIC_CUSTOMERS, read again on every call. The isolation is here, in the API, not in
the web: the public accounts' PINs are published, so anyone can call this with their own token. Every ticket is looked up and
must have been filed by the caller's session (`session_ref`); someone else's answers exactly like one that does not exist, and is
looked up the same way (`_session_tickets`), so not even the time taken tells them apart. The actor of every move is "demo", set
here, never by the body, and a name no real operator may have (agent/session/operators.py). The moves are the real desk's (agent/policy/desk.py), with its
versions and its conflicts, so approving a trace opens it in the sandbox's tracing service, once.

Checks, in order: the switches (404), a live session (401), a public account (403), the rate limits (429), the ticket (404).
"""
from __future__ import annotations

import json
import os
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from agent.policy import desk as desk_policy
from agent.policy.desk import Conflict, DeskError, HeldByAnother, NotFound, default_desk
from agent.policy.escalation import default_queue
from agent.session.auth import Session, SessionError, default_store
from agent.session.operators import DEMO_ACTOR
from agent.session.public_accounts import public_customer_ids
from agent.tools.traces import default_traces
from api import customer_context
from api.demo import _of_session, enabled as demo_enabled, require_demo
from api.human_queue import _DeskSnapshot
from api.limits import RateLimiter, too_many

ACTOR = DEMO_ACTOR
PREFIX = "/demo/desk"
NOT_FOUND = "ticket not found"
TAKEN = "another person took this case"


def console_enabled() -> bool:
    return os.environ.get("DEMO_CONSOLE") == "1"


def require_demo_console() -> None:
    if not console_enabled():
        raise HTTPException(404, "Not Found")


class ConsoleSwitch:
    """ASGI guard: with either switch off, anything under /demo/desk is the 404 of a route that does not exist. It runs before
    routing and before the body is read, so a method the routes do not take is not a 405 and a malformed body is not a 422.
    It sits inside the request middleware (api/main.py), so the body cap answers it as it answers any other path."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if (path == PREFIX or path.startswith(PREFIX + "/")) and not (demo_enabled() and console_enabled()):
            await JSONResponse({"detail": "Not Found"}, status_code=404)(scope, receive, send)
            return
        await self.app(scope, receive, send)


# Per visitor (session) and, to bound the total, per public account: every visitor of one account shares the second.
session_limiter = RateLimiter(int(os.environ.get("DEMO_DESK_RATE_PER_MIN", "60")), 60, "demo_desk")
customer_limiter = RateLimiter(int(os.environ.get("DEMO_DESK_CUSTOMER_RATE_PER_MIN", "300")), 60, "demo_desk_customer")


def demo_visitor(x_session_token: str | None = Header(default=None)) -> Session:
    """The caller's live session, if it belongs to a public sandbox account and is within its limits."""
    try:
        session = default_store.validate(x_session_token or "")
    except SessionError:
        raise HTTPException(401, "no live session") from None
    if session.customer_id not in public_customer_ids():
        raise HTTPException(403, "not a public sandbox account")
    if not session_limiter.allow(session.ref):
        raise too_many(session_limiter, session.ref, "rate limit exceeded for this session")
    if not customer_limiter.allow(session.customer_id):
        raise too_many(customer_limiter, session.customer_id, "rate limit exceeded for this account")
    return session


router = APIRouter(prefix="/demo/desk", dependencies=[Depends(require_demo), Depends(require_demo_console)])


def _session_tickets(session: Session) -> dict[str, dict]:
    """Every ticket this session filed, by id. The whole queue is read and only this session's lines are parsed, whatever id is
    asked for: finding another session's ticket costs what finding none does (a lookup by id stops at the line it finds)."""
    path = default_queue.path
    if not path.exists():
        return {}
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if session.ref not in line:
            continue
        try:
            ticket = json.loads(line)
        except ValueError:
            continue
        if (isinstance(ticket, dict) and isinstance(ticket.get("ticket_id"), str) and ticket.get("session_ref") == session.ref
                and ticket.get("customer_id") == session.customer_id):
            found[ticket["ticket_id"]] = ticket
    return found


def _own_ticket(ticket_id: str, session: Session) -> dict:
    """The ticket, if this session filed it. Anyone else's answers the same 404 as one that does not exist."""
    ticket = _session_tickets(session).get(ticket_id)
    if ticket is None:
        raise HTTPException(404, NOT_FOUND)
    return ticket


@router.get("/tickets")
def tickets(session: Session = Depends(demo_visitor)) -> list[dict]:
    """The tickets this session filed, newest first (at most 20), each with its desk state: the rows of /admin/human_queue."""
    snapshot = _DeskSnapshot(default_desk.path)
    return [{**t, "desk": snapshot.state(t["ticket_id"])} for t in _of_session(default_queue.path, session.token)]


@router.get("/tickets/{ticket_id}")
def ticket(ticket_id: str, session: Session = Depends(demo_visitor)) -> dict:
    """One of this session's tickets with its desk state and the results it may be resolved with (codes of its family, in
    order; empty when it carries an action, which is approved or rejected instead)."""
    found = _own_ticket(ticket_id, session)
    return {**found, "desk": default_desk.state(ticket_id), "resolve_results": list(desk_policy.results_for(found))}


@router.get("/tickets/{ticket_id}/customer_context")
def ticket_customer_context(ticket_id: str, session: Session = Depends(demo_visitor)) -> dict:
    """What /admin/tickets/{id}/customer_context answers, with the other cases and traces of this session alone."""
    found = _own_ticket(ticket_id, session)
    return customer_context.for_ticket(found, default_queue, default_desk, default_traces, session_ref=session.ref, actor=ACTOR)


class DemoDeskAction(BaseModel):
    model_config = ConfigDict(extra="forbid")  # no operator, no other field: who acts is set here
    expected_version: int | None = Field(default=None, strict=True, ge=0, le=1_000_000)
    reason: str | None = Field(default=None, max_length=300)  # reject: a note for the console, never the customer
    result_code: str | None = Field(default=None, max_length=64)  # resolve: a predefined result of the ticket's family
    message: str | None = Field(default=None, max_length=500)  # resolve, optional: the person's words, after the result


@router.post("/tickets/{ticket_id}/{action}")
def ticket_action(ticket_id: str, action: Literal["claim", "approve", "reject", "release", "resolve"], body: DemoDeskAction,
                  session: Session = Depends(demo_visitor)) -> dict:
    """The real desk's move on one of this session's tickets, as "demo". A resolution names one of the ticket's results and may
    add a message, which the customer reads after it in the fixed quote."""
    found = _own_ticket(ticket_id, session)
    message = (body.message or "").strip() or None
    if action != "resolve" and (body.result_code is not None or message is not None):
        raise HTTPException(422, "a result and a message are only for resolve")
    if action == "resolve":
        if body.result_code is None:
            raise HTTPException(400, "a result is required to resolve a case")
        if body.result_code not in desk_policy.results_for(found):
            raise HTTPException(422, "that result is not one of this case's")
    try:
        return default_desk.act(ticket_id, action, ACTOR, body.expected_version, body.reason, message,
                                result=body.result_code if action == "resolve" else None)
    except NotFound:
        raise HTTPException(404, NOT_FOUND) from None
    except HeldByAnother:  # a real operator holds the case: they are not named, whatever the move
        raise HTTPException(409, TAKEN) from None
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from None
    except DeskError as exc:
        raise HTTPException(400, str(exc)) from None
