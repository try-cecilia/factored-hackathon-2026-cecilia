"""What the API reports about itself: request metrics by route template, liveness and readiness.

- `ObservabilityMiddleware` counts every request and times it under its route *template* (`/admin/tickets/{ticket_id}/{action}`,
  never the concrete path, so ids never become labels). Anything that matches no route is one label, `unmatched`.
- `readiness()` is what a load balancer should ask before sending traffic: the warehouse answers, the state store answers, the
  data directory takes writes. /livez only says the process is up, so a broken warehouse gets traffic withheld, not a restart loop.
"""
from __future__ import annotations

import os
import re
import time

from fastapi.routing import iter_route_contexts
from starlette.types import ASGIApp, Receive, Scope, Send

from agent import metrics


class RouteTemplates:
    """Maps (method, concrete path) to the route template that handles it."""

    def __init__(self, app) -> None:
        self._app = app
        self._compiled: list[tuple[re.Pattern, frozenset[str], str]] | None = None

    def _build(self) -> list[tuple[re.Pattern, frozenset[str], str]]:
        out = []
        for rc in iter_route_contexts(self._app.routes):
            parts = re.split(r"(\{[^}]+\})", rc.path)
            pattern = "".join("[^/]+" if p.startswith("{") else re.escape(p) for p in parts)
            out.append((re.compile(f"^{pattern}$"), frozenset(rc.methods or ()), rc.path))
        return out

    def resolve(self, method: str, path: str) -> str:
        if self._compiled is None:
            self._compiled = self._build()
        for pattern, methods, template in self._compiled:
            if (method in methods or (method == "HEAD" and "GET" in methods)) and pattern.match(path):
                return template
        return "unmatched"


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp, templates: RouteTemplates) -> None:
        self.app, self.templates = app, templates

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start, status = time.perf_counter(), 500

        async def send_and_note(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_note)
        finally:
            method = scope["method"]
            route = self.templates.resolve(method, scope["path"])
            try:
                metrics.default.observe_http(method, route, status, time.perf_counter() - start)
            except Exception:  # noqa: BLE001 - counting must never break a request
                pass


PROBE_TIMEOUT_S = 2.0


def _query_warehouse() -> bool:
    """A real read of the warehouse file as it is now: the file must exist and a *new* read-only connection must answer a query.
    Not data_as_of() (cached) and not the cached connection (on Linux it keeps reading a file that was deleted)."""
    import duckdb

    from agent.tools.db import duckdb_path

    path = duckdb_path()
    if not os.path.isfile(path):
        return False
    con = duckdb.connect(path, read_only=True)
    try:
        return con.execute("SELECT 1 FROM transactions LIMIT 1").fetchone() is not None
    finally:
        con.close()


def _within(seconds: float, probe) -> bool:
    """probe() answered True in time. A probe that hangs is abandoned (its thread finishes on its own), not waited for."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return bool(pool.submit(probe).result(timeout=seconds))
    except (TimeoutError, Exception):  # noqa: BLE001 - any failure means not ready; the reason stays in the logs
        return False
    finally:
        pool.shutdown(wait=False)


def readiness() -> dict[str, bool]:
    """Each dependency a request needs, as a yes or no, read fresh every time. The reasons stay in the logs: this answer is public."""
    from agent.session.auth import default_store
    from agent.tools.audit import default_audit_log

    def state_store() -> bool:
        path = os.environ.get("STATE_DB_PATH")
        return (not path or os.path.isfile(path)) and len(default_store) >= 0  # len() runs a COUNT on the database

    def data_dir_writable() -> bool:
        return os.access(default_audit_log.path.parent, os.W_OK)

    return {"warehouse": _within(PROBE_TIMEOUT_S, _query_warehouse),
            "state_store": _within(PROBE_TIMEOUT_S, state_store),
            "data_dir_writable": _within(PROBE_TIMEOUT_S, data_dir_writable)}
