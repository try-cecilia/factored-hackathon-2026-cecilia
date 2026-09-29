"""A model call that outlives its budget is cancelled, not abandoned: its connection is closed, no thread is left running
it, and the server sees the client go away. Checked against a server that never stops sending."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent.llm.client import LLMClient, LLMUnavailable


class Endless(BaseHTTPRequestHandler):
    """Sends a chunk of a never-finishing JSON answer every 50 ms for up to 10 s, and notes when the client goes."""

    def do_POST(self):
        self.server.active += 1
        try:
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            piece = b'{"choices": [' + b" " * 40
            for _ in range(200):
                self.wfile.write(f"{len(piece):x}\r\n".encode() + piece + b"\r\n")
                self.wfile.flush()
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError, OSError):
            self.server.disconnected += 1
        finally:
            self.server.active -= 1

    def log_message(self, *a):
        pass


@pytest.fixture
def endless():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Endless)
    server.daemon_threads = True
    server.active = server.disconnected = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def wait_until(check, seconds=2.0):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


def three_expired_calls(client, server):
    with pytest.raises(LLMUnavailable):  # a first call to load the SDK's lazy modules, which is not what is being timed
        client.chat([{"role": "user", "content": "hi"}], tools=None)
    wait_until(lambda: server.active == 0)
    server.disconnected = 0
    for _ in range(3):
        t0 = time.perf_counter()
        with pytest.raises(LLMUnavailable):
            client.chat([{"role": "user", "content": "hi"}], tools=None)
        assert time.perf_counter() - t0 < 0.5


def test_expired_local_calls_leave_no_thread_and_no_open_connection(endless, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", f"http://127.0.0.1:{endless.server_address[1]}/v1")
    baseline = threading.active_count()
    three_expired_calls(LLMClient(sleep=lambda s: None, timeout_s=5, total_budget_s=0.15, max_attempts_per_provider=1, breaker_threshold=100), endless)
    assert wait_until(lambda: endless.active == 0 and endless.disconnected == 3), (endless.active, endless.disconnected)
    # the server saw each client leave: the connections were closed, not left to drain for the 10 s it would go on sending
    assert not [t for t in threading.enumerate() if t.name == "llm-call"] and threading.active_count() <= baseline


def test_the_same_holds_for_the_anthropic_sdk(endless, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{endless.server_address[1]}")
    three_expired_calls(LLMClient(sleep=lambda s: None, timeout_s=5, total_budget_s=0.15, max_attempts_per_provider=1, breaker_threshold=100), endless)
    assert wait_until(lambda: endless.active == 0 and endless.disconnected == 3), (endless.active, endless.disconnected)


def test_every_sdk_client_is_built_over_the_deadline_transport():
    from agent.llm import client as c

    for name, factory in (("anthropic", c._anthropic_factory), ("groq", c._groq_factory), ("together", c._together_factory)):
        sdk = factory("test-key", 5)
        http = getattr(sdk, "_client", None)
        assert isinstance(getattr(http, "_transport", None), c.DeadlineTransport), name


# --- the limit covers the headers too --------------------------------------------------------------------------------

class SlowHeaders(BaseHTTPRequestHandler):
    """Answers with its status line and headers a few bytes at a time (30 ms apart, 0.9 s in all): each read is in time."""

    def do_POST(self):
        self.server.active += 1
        try:
            self.rfile.read(int(self.headers["Content-Length"]))
            head = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nX-Padding: " + b"a" * 20 + b"\r\nContent-Length: 2\r\n\r\n{}"
            for i in range(0, len(head), 3):
                self.wfile.write(head[i:i + 3])
                self.wfile.flush()
                time.sleep(0.03)
        except (BrokenPipeError, ConnectionResetError, OSError):
            self.server.disconnected += 1
        finally:
            self.server.active -= 1

    def log_message(self, *a):
        pass


@pytest.fixture
def slow_headers():
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHeaders)
    server.daemon_threads = True
    server.active = server.disconnected = 0
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("provider", ["local", "anthropic", "groq", "together"])
def test_a_server_that_dribbles_its_headers_cannot_outlast_the_calls_limit(slow_headers, monkeypatch, provider):
    base = f"http://127.0.0.1:{slow_headers.server_address[1]}"
    monkeypatch.setenv("LLM_PROVIDERS", provider)
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", base + "/v1")
    for var, key in (("ANTHROPIC", "ANTHROPIC_API_KEY"), ("GROQ", "GROQ_API_KEY"), ("TOGETHER", "TOGETHER_API_KEY")):
        monkeypatch.setenv(key, "test-key")
        monkeypatch.setenv(f"{var}_BASE_URL", base)
    client = LLMClient(sleep=lambda s: None, timeout_s=5, total_budget_s=0.1, max_attempts_per_provider=1, breaker_threshold=100)
    with pytest.raises(LLMUnavailable):  # a first call loads the SDK's lazy modules: not what is timed
        client.chat([{"role": "user", "content": "hi"}])
    t0 = time.perf_counter()
    with pytest.raises(LLMUnavailable):
        client.chat([{"role": "user", "content": "hi"}])
    assert time.perf_counter() - t0 < 0.3, "the 0.9 s of dribbled headers outlasted the 0.1 s budget"
    assert wait_until(lambda: slow_headers.active == 0)  # and the connection was closed, not left to finish
