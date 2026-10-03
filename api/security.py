"""What every response carries, who may call the API from a browser, and how secrets are compared.

- Headers: nosniff, no framing, no referrer, no caching of API answers, and a Content-Security-Policy. The one HTML page
  (api/static/index.html) may run only its own inline script, pinned by hash; every JSON answer gets a policy that allows
  nothing. Strict-Transport-Security only when SECURITY_HSTS=1 (every client reaches the service over HTTPS).
- CORS: off. The frontend calls the API from its own server, so a browser never needs it. CORS_ALLOWED_ORIGINS lists exact
  origins that may (a wildcard is refused at startup), for GET, POST and DELETE with a session token; the admin and operator
  keys are never an allowed header, so no web page can carry them across origins.
- Secrets are compared with `constant_time_equals` (agent/session/secure_compare.py), which does not fail on non-ASCII input.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
from pathlib import Path

from agent.session.secure_compare import constant_time_equals  # noqa: F401 - re-exported: the API's one way to compare a secret
from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

STATIC_INDEX = Path(__file__).parent / "static" / "index.html"
ALLOWED_CORS_HEADERS = ["Content-Type", "X-Session-Token"]
ALLOWED_CORS_METHODS = ["GET", "POST", "DELETE"]


def page_csp(html: str | None = None) -> str:
    """The policy for the HTML page: its inline scripts are allowed by hash, nothing else runs. Inline styles stay allowed
    (the page styles elements with style attributes); they cannot run code."""
    # FileResponse sends the stored bytes unchanged; preserve CRLF too so the
    # CSP hash is identical to the inline script the browser receives.
    html = STATIC_INDEX.read_bytes().decode("utf-8") if html is None else html
    hashes = " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()}'"
                      for s in re.findall(r"<script>(.*?)</script>", html, re.S))
    return ("default-src 'none'; script-src %s; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'" % hashes)


API_CSP = "default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool | None = None) -> None:
        self.app = app
        self.hsts = os.environ.get("SECURITY_HSTS") == "1" if hsts is None else hsts
        self.page_csp = page_csp()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_page = scope["path"] == "/" and scope["method"] == "GET"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h.setdefault("X-Content-Type-Options", "nosniff")
                h.setdefault("X-Frame-Options", "DENY")
                h.setdefault("Referrer-Policy", "no-referrer")
                h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
                h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
                h.setdefault("Content-Security-Policy", self.page_csp if is_page else API_CSP)
                h.setdefault("Cache-Control", "no-store")
                if self.hsts:
                    h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            await send(message)

        await self.app(scope, receive, send_with_headers)


def cors_origins(raw: str | None = None) -> list[str]:
    """CORS_ALLOWED_ORIGINS as exact origins. Refuses a wildcard or anything that is not scheme://host[:port]."""
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "") if raw is None else raw
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    for o in origins:
        if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d{1,5})?", o):
            raise ValueError(f"CORS_ALLOWED_ORIGINS: {o!r} is not an exact origin like https://app.example.com (no wildcard, no path)")
    return origins


def configure_cors(app, origins: list[str] | None = None) -> None:
    origins = cors_origins() if origins is None else origins
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=ALLOWED_CORS_METHODS,
                           allow_headers=ALLOWED_CORS_HEADERS, allow_credentials=False, max_age=600)
