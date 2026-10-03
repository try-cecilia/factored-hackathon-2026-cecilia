"""Who may call what: the access matrix, endpoint by endpoint, and the check that keeps it complete.

Four roles, by the credential the caller presents:
  anonymous  nothing
  customer   a session token (from /auth/session), in X-Session-Token or in the body
  operator   an operator key (X-Operator-Key): the only role that may act on a ticket
  admin      the admin key (X-Admin-Key): reads queues, traces, audit and metrics; never acts
The roles are separate credentials, not a ladder: an admin key does not open /chat and an operator key does not read the audit log.

POLICY has one row per route. `check_app(app)` runs when the service starts (api/main.py) and refuses to start if a route has no
row, a row has no route, or a route that should demand a key does not carry that key's dependency. So a new endpoint cannot ship
unclassified. tests/test_access_matrix.py then calls every row as every role and compares the answer with this table.

`demo_only` rows answer 404 to everyone unless DEMO_MODE=1 (the jury sandbox): they are not part of the surface anywhere else.
`demo_console` rows (the demo's console, api/demo_desk.py) also need DEMO_CONSOLE=1; both rules are checked against the routes'
dependencies (require_demo, require_demo_console) when the service starts.
`optional` rows exist only when EXPOSE_API_DOCS=1.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi.routing import iter_route_contexts


class Role(str, Enum):
    ANONYMOUS = "anonymous"
    CUSTOMER = "customer"
    OPERATOR = "operator"
    ADMIN = "admin"


ANYONE = frozenset(Role)
CUSTOMER, OPERATOR, ADMIN = frozenset({Role.CUSTOMER}), frozenset({Role.OPERATOR}), frozenset({Role.ADMIN})

GUARDS = {"admin": "require_admin", "operator": "require_operator", "metrics": "require_metrics"}
SWITCHES = {"demo_only": "require_demo", "demo_console": "require_demo_console"}


@dataclass(frozen=True)
class Policy:
    roles: frozenset[Role]  # who gets past the door
    guard: str = "none"  # none | session (checked in the handler) | admin | operator | metrics (a dependency on the route)
    demo_only: bool = False
    demo_console: bool = False  # demo_only and, besides, DEMO_CONSOLE=1
    optional: bool = False
    note: str = ""


POLICY: dict[tuple[str, str], Policy] = {
    # Public: the page, the probes, the login
    ("GET", "/"): Policy(ANYONE, note="the chat page; it holds no data"),
    ("GET", "/health"): Policy(ANYONE, note="data as-of date, configured providers, budget flag, classifier loaded"),
    ("GET", "/livez"): Policy(ANYONE, note="the process is up"),
    ("GET", "/readyz"): Policy(ANYONE, note="the warehouse, the state store and the data directory answer; yes/no only"),
    ("POST", "/auth/session"): Policy(ANYONE, note="customer id + PIN; limited per client address, locked after 5 failures"),
    ("DELETE", "/auth/session"): Policy(ANYONE, note="logout: always 204, an unknown token is a no-op"),
    # Customer: a live session
    ("GET", "/auth/session"): Policy(CUSTOMER, "session"),
    ("POST", "/chat"): Policy(CUSTOMER, "session", note="the session token is in the body; a dead one gets REAUTH_REQUIRED"),
    ("GET", "/chat/history"): Policy(CUSTOMER, "session", note="the live session's own conversation, as rendered; nothing after the session ends"),
    ("GET", "/case/{ticket_id}"): Policy(CUSTOMER, "session", note="only the session's own tickets"),
    # Operator: acts on tickets
    ("POST", "/admin/tickets/{ticket_id}/{action}"): Policy(OPERATOR, "operator", note="claim, approve, reject, release, resolve; the actor is the key's name"),
    ("GET", "/admin/operator/me"): Policy(OPERATOR, "operator", note="the operator key's name, touching no ticket (the web BFF's login check)"),
    # Admin: reads
    ("GET", "/metrics"): Policy(ADMIN, "metrics", note="admin key, or the METRICS_TOKEN a scraper holds (which opens only this)"),
    ("GET", "/admin/human_queue"): Policy(ADMIN, "admin", note="the latest `limit` tickets (at most 200) plus every ticket still open or claimed that the file still holds, however old (the 90-day retention removes it); approved, rejected, handed-back, stale and resolved ones are cut by age"),
    ("GET", "/admin/tickets/{ticket_id}"): Policy(ADMIN, "admin"),
    ("GET", "/admin/tickets/{ticket_id}/customer_context"): Policy(ADMIN, "admin", note="the case's customer, read-only: products (last four digits only), latest and pending movements, the customer's other cases and trace requests; the warehouse being down is a 200 that says so"),
    ("GET", "/admin/audit_log"): Policy(ADMIN, "admin"),
    ("GET", "/admin/trace_log"): Policy(ADMIN, "admin"),
    ("GET", "/admin/traces/{trace_id}"): Policy(ADMIN, "admin"),
    ("GET", "/admin/ops"): Policy(ADMIN, "admin"),
    ("GET", "/admin/drift"): Policy(ADMIN, "admin"),
    ("POST", "/admin/drift/snapshot"): Policy(ADMIN, "admin"),
    ("GET", "/admin/experiments"): Policy(ADMIN, "admin"),
    ("GET", "/admin/llm_budget"): Policy(ADMIN, "admin"),
    ("GET", "/admin/data_quality"): Policy(ADMIN, "admin"),
    ("GET", "/admin/capacity"): Policy(ADMIN, "admin", note="limits in force and how often they refused"),
    # The jury sandbox: nothing of this exists outside DEMO_MODE=1
    ("GET", "/demo/customers"): Policy(ANYONE, demo_only=True, note="publishes test PINs for the sandbox accounts"),
    ("GET", "/demo/scenarios"): Policy(ANYONE, demo_only=True, note="guided scenarios, with test PINs"),
    ("GET", "/demo/data_quality"): Policy(ANYONE, demo_only=True, note="aggregates only"),
    ("POST", "/demo/fault"): Policy(CUSTOMER, "session", demo_only=True, note="acts on the caller's own session"),
    ("POST", "/demo/tickets"): Policy(CUSTOMER, "session", demo_only=True, note="the session's own tickets"),
    ("POST", "/demo/traces"): Policy(CUSTOMER, "session", demo_only=True, note="the session's own trace requests"),
    ("GET", "/admin/demo_pin/{customer_id}"): Policy(ADMIN, "admin", demo_only=True, note="derives any customer's test PIN"),
    # The demo's console: the customer's own session acts as the bank, only on a public sandbox account and only on its own tickets
    ("GET", "/demo/desk/tickets"): Policy(CUSTOMER, "session", demo_only=True, demo_console=True,
                                          note="a public sandbox account only; the session's own tickets, with their desk state"),
    ("GET", "/demo/desk/tickets/{ticket_id}"): Policy(CUSTOMER, "session", demo_only=True, demo_console=True,
                                                      note="the session's own ticket; anyone else's is the same 404 as none"),
    ("GET", "/demo/desk/tickets/{ticket_id}/customer_context"): Policy(
        CUSTOMER, "session", demo_only=True, demo_console=True, note="as the admin's, with the other cases and traces of this session only"),
    ("POST", "/demo/desk/tickets/{ticket_id}/{action}"): Policy(
        CUSTOMER, "session", demo_only=True, demo_console=True,
        note="claim, approve, reject, release, resolve on the session's own ticket; the actor is always `demo`"),
    # FastAPI's own pages: the API's schema is not published unless asked for
    ("GET", "/openapi.json"): Policy(ANYONE, optional=True, note="EXPOSE_API_DOCS=1"),
    ("GET", "/docs"): Policy(ANYONE, optional=True, note="EXPOSE_API_DOCS=1"),
    ("GET", "/docs/oauth2-redirect"): Policy(ANYONE, optional=True, note="EXPOSE_API_DOCS=1"),
    ("GET", "/redoc"): Policy(ANYONE, optional=True, note="EXPOSE_API_DOCS=1"),
}


def app_routes(app) -> dict[tuple[str, str], object]:
    """Every (method, path) the app answers, with its route context. HEAD is not a separate surface from GET."""
    found = {}
    for rc in iter_route_contexts(app.routes):
        for method in sorted(rc.methods or ()):
            if method not in ("HEAD", "OPTIONS"):
                found[(method, rc.path)] = rc
    return found


def _dependency_names(dependant) -> set[str]:
    names = set()
    for dep in getattr(dependant, "dependencies", ()):
        if dep.call is not None:
            names.add(getattr(dep.call, "__name__", ""))
        names |= _dependency_names(dep)
    return names


def problems(app, policy: dict[tuple[str, str], Policy] = POLICY) -> list[str]:
    routes = app_routes(app)
    out = [f"{m} {p}: no access policy (add a row to api/access.py)" for (m, p) in sorted(routes) if (m, p) not in policy]
    out += [f"{m} {p}: policy for a route that does not exist" for (m, p), row in sorted(policy.items())
            if (m, p) not in routes and not row.optional]
    for key, row in sorted(policy.items()):
        rc = routes.get(key)
        if rc is None or row.guard not in GUARDS:
            continue
        dependant = getattr(getattr(rc, "route", None), "dependant", None)
        if GUARDS[row.guard] not in _dependency_names(dependant):
            out.append(f"{key[0]} {key[1]}: declared {row.guard!r} but the route does not depend on {GUARDS[row.guard]}")
    for key, row in sorted(policy.items()):
        rc = routes.get(key)
        if rc is None:
            continue
        names = _dependency_names(getattr(getattr(rc, "route", None), "dependant", None))
        for flag, guard in SWITCHES.items():
            if getattr(row, flag) and guard not in names:
                out.append(f"{key[0]} {key[1]}: declared {flag} but the route does not depend on {guard}")
        if row.demo_console and not row.demo_only:
            out.append(f"{key[0]} {key[1]}: demo_console without demo_only")
    for key, row in sorted(policy.items()):
        if key in routes and row.guard not in ("none", "session", *GUARDS):
            out.append(f"{key[0]} {key[1]}: unknown guard {row.guard!r}")
    return out


def check_app(app, policy: dict[tuple[str, str], Policy] = POLICY) -> None:
    found = problems(app, policy)
    if found:
        raise RuntimeError("access policy does not match the routes:\n  " + "\n  ".join(found))


def matrix_markdown(policy: dict[tuple[str, str], Policy] = POLICY) -> str:
    """The matrix as the Markdown table in docs/operations.md ("Access control"); tests/test_access_matrix.py keeps the two equal.
    `yes` = gets past the door; `-` = refused. Demo-only rows say so: without DEMO_MODE=1 they are a 404 for every role, and the
    demo console's also without DEMO_CONSOLE=1."""
    header = ["Endpoint", *(r.value for r in Role), "Notes"]
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for (method, path), row in policy.items():
        note = (("demo console only (DEMO_CONSOLE=1). " if row.demo_console else "demo only. ") if row.demo_only else "") + (
            "with EXPOSE_API_DOCS=1. " if row.optional else "") + row.note
        cells = ["yes" if r in row.roles else "-" for r in Role]
        lines.append(f"| `{method} {path}` | " + " | ".join(cells) + f" | {note.strip()} |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(matrix_markdown())
