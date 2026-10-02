"""Response headers, CORS and the surfaces that are off unless asked for."""
from __future__ import annotations

import base64
import hashlib
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.session import identity
from api import main, security

EVIL = "https://evil.example"


@pytest.fixture
def client(monkeypatch):
    identity.default_identity._failures.clear()
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(100, 60))
    monkeypatch.delenv("DEMO_MODE", raising=False)
    return TestClient(main.app)


def test_every_answer_carries_the_security_headers(client):
    for path in ("/livez", "/health", "/no-such-route", "/admin/ops"):  # a success, an unknown route and a refusal too
        h = client.get(path).headers
        assert h["x-content-type-options"] == "nosniff", path
        assert h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer", path
        assert h["cache-control"] == "no-store" and "camera=()" in h["permissions-policy"], path
        assert h["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'", path


def test_a_method_a_route_does_not_list_is_a_405_that_names_the_allowed_ones(client):
    """V14.5.1: only the methods in use. The routing refuses the rest before any handler or credential check runs."""
    cases = [("PATCH", "/health", "GET"), ("DELETE", "/livez", "GET"), ("PUT", "/chat", "POST"), ("POST", "/admin/human_queue", "GET")]
    for method, path, allowed in cases:
        r = client.request(method, path)
        assert r.status_code == 405, (method, path)
        assert allowed in r.headers["allow"], (method, path)
    assert client.request("PATCH", "/auth/session").status_code == 405


def test_the_page_may_run_only_its_own_script_by_hash(client):
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    script = re.search(r"<script>(.*?)</script>", r.text, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in csp and "unsafe-inline" not in csp.split("style-src")[0]
    assert "frame-ancestors 'none'" in csp and "connect-src 'self'" in csp and "default-src 'none'" in csp


def test_strict_transport_security_only_when_asked_for(client):
    assert "strict-transport-security" not in client.get("/livez").headers
    scratch = FastAPI()
    scratch.add_middleware(security.SecurityHeadersMiddleware, hsts=True)
    scratch.get("/x")(lambda: {})
    assert "max-age=31536000" in TestClient(scratch).get("/x").headers["strict-transport-security"]


def test_there_is_no_cors_by_default(client):
    pre = client.options("/chat", headers={"Origin": EVIL, "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in pre.headers
    assert "access-control-allow-origin" not in client.get("/health", headers={"Origin": EVIL}).headers


def test_cors_allows_exactly_the_listed_origins_and_never_the_keys():
    scratch = FastAPI()
    scratch.get("/x")(lambda: {})
    security.configure_cors(scratch, security.cors_origins("https://app.example.com/, http://localhost:3000"))
    c = TestClient(scratch)
    ask = lambda origin, headers="X-Session-Token": c.options("/x", headers={  # noqa: E731
        "Origin": origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": headers})
    ok = ask("https://app.example.com")
    assert ok.headers["access-control-allow-origin"] == "https://app.example.com"
    assert "access-control-allow-credentials" not in ok.headers
    assert "access-control-allow-origin" not in ask(EVIL).headers
    assert ask("https://app.example.com", "X-Admin-Key").status_code == 400  # a page cannot carry the admin key across origins
    assert ask("https://app.example.com", "X-Operator-Key").status_code == 400


@pytest.mark.parametrize("bad", ["*", "https://*.example.com", "https://app.example.com/path", "app.example.com", "javascript:alert(1)"])
def test_a_wildcard_or_loose_origin_stops_the_service_from_starting(bad):
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        security.cors_origins(bad)


def test_the_api_schema_and_docs_are_not_published_by_default(client):
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 404


def test_the_pin_hint_and_pins_are_not_available_outside_the_sandbox(client, monkeypatch):
    monkeypatch.setenv("DEMO_PUBLIC_CUSTOMERS", "CLI-FIX0001")
    assert client.get("/demo/customers").status_code == 404
    assert client.get("/admin/demo_pin/CLI-FIX0001", headers={"X-Admin-Key": "test-admin-key"}).status_code == 404
    monkeypatch.setenv("DEMO_MODE", "1")
    assert client.get("/demo/customers").status_code == 200
    assert client.get("/admin/demo_pin/CLI-FIX0001", headers={"X-Admin-Key": "test-admin-key"}).status_code == 200


def test_chat_shows_no_policy_rule_outside_the_sandbox(client):
    from agent.session.identity import derive_test_pin

    token = client.post("/auth/session", json={"customer_id": "CLI-FIX0001", "pin": derive_test_pin("CLI-FIX0001")}).json()["token"]
    reply = client.post("/chat", json={"session_token": token, "message": "Me clonaron la tarjeta"}).json()
    assert reply["policy_rule"] == "" and reply["why"] is None


def test_the_demo_ui_endpoints_that_read_a_session_refuse_a_dead_one(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    for path in ("/demo/tickets", "/demo/traces"):
        assert client.post(path, json={"session_token": "0" * 24}).status_code == 401
