"""The wait for a free connection is inside the model call's limit.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from agent import observability
from agent.core import render
from agent.core.orchestrator import Orchestrator
from agent.llm.client import call_limit, deadline_transport
from agent.policy import escalation
from agent.session.auth import SessionStore
from agent.tools import account_tools
from eval.fake_llm import FakeLLMClient


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    for var in ("TRACE_REQUESTS_PATH", "HUMAN_QUEUE_PATH", "AUDIT_LOG_PATH", "TRACE_LOG_PATH"):
        monkeypatch.setenv(var, str(tmp_path / f"{var}.jsonl"))
    from agent.policy import intent_guard

    intent_guard.read("hola")


def tickets() -> list[dict]:
    path = os.environ["HUMAN_QUEUE_PATH"]
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def orchestrator():
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: FakeLLMClient([]))
    return orch, orch.session_store.issue("CLI-FIX0001", {"segment": "Premium", "country": "México", "customer_status": "Active"}).token


def alive(name):
    return [t for t in threading.enumerate() if t.name == name]


def wait_until(check, seconds=3.0):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


# --- 3. the pool wait is inside the call's limit ------------------------------------------------------------------------------

class Hold(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        time.sleep(0.8)
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_waiting_for_a_free_connection_counts_against_the_calls_limit():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Hold)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = httpx.Client(transport=deadline_transport(httpx, max_connections=1), timeout=5)
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        busy = threading.Thread(target=lambda: client.post(url, json={}), daemon=True)
        busy.start()
        time.sleep(0.1)  # the only connection is now in use for 0.7 s more
        token = call_limit.set(time.perf_counter() + 0.05)
        try:
            t0 = time.perf_counter()
            with pytest.raises(httpx.TimeoutException):
                client.post(url, json={})
            assert time.perf_counter() - t0 < 0.05 + 0.1
        finally:
            call_limit.reset(token)
        busy.join()
    finally:
        server.shutdown()
        server.server_close()
