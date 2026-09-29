"""The `local` provider (Ollama or any OpenAI-compatible server) against a fake server on 127.0.0.1: no key, no network,
and the same bounded retries, circuit breaker, deadline and fallback as every other provider."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent.core.orchestrator import Orchestrator
from agent.llm.client import LLMClient, LLMUnavailable, default_providers, local_base_url
from agent.llm.pricing import cost_usd
from agent.session.auth import SessionStore

TOOL_ANSWER = {"model": "gpt-oss:20b", "choices": [{"finish_reason": "tool_calls", "message": {
    "role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {
        "name": "get_account_summary", "arguments": json.dumps({"product_id": "PRD-FIX0001"})}}]}}],
    "usage": {"prompt_tokens": 1200, "completion_tokens": 40}}


class FakeOllama:
    """Serves scripted answers to POST /v1/chat/completions: (status, body, delay_s) per request, then repeats the last."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization")})
                status, payload, delay = outer.script.pop(0) if len(outer.script) > 1 else outer.script[0]
                time.sleep(delay)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def ollama(monkeypatch):
    servers = []

    def start(*script):
        s = FakeOllama(script)
        servers.append(s)
        monkeypatch.setenv("LOCAL_LLM_BASE_URL", s.url)
        monkeypatch.setenv("LLM_PROVIDERS", "local")
        return s

    yield start
    for s in servers:
        s.close()


MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "saldo"}]


def client(**kw):
    return LLMClient(sleep=lambda s: None, **kw)


def test_the_local_provider_needs_no_key_and_parses_a_tool_call_and_its_usage(ollama):
    server = ollama((200, TOOL_ANSWER, 0))
    r = client().chat(MESSAGES, tools=[{"type": "function", "function": {"name": "get_account_summary", "parameters": {}}}])
    assert r.provider == "local" and r.model == "gpt-oss:20b"
    assert r.tool_calls == [{"id": "call_1", "name": "get_account_summary", "arguments": '{"product_id": "PRD-FIX0001"}'}]
    assert (r.usage.prompt_tokens, r.usage.completion_tokens) == (1200, 40)
    sent = server.requests[0]
    assert sent["path"] == "/v1/chat/completions" and sent["auth"] is None  # no credential goes anywhere
    assert sent["body"]["model"] == "gpt-oss:20b" and sent["body"]["tool_choice"] == "auto" and sent["body"]["max_tokens"] == 4096


def test_the_model_and_the_address_come_from_the_environment(ollama, monkeypatch):
    server = ollama((200, TOOL_ANSWER, 0))
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen3:8b")
    client().chat(MESSAGES)
    assert server.requests[0]["body"]["model"] == "qwen3:8b"
    monkeypatch.delenv("LOCAL_LLM_BASE_URL")
    assert local_base_url() == "http://127.0.0.1:11434/v1"  # Ollama's own default outside the compose


def test_it_is_tried_only_when_it_is_listed_and_counts_as_configured_then(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDERS", raising=False)
    assert "local" not in [p.name for p in default_providers()]
    monkeypatch.setenv("LLM_PROVIDERS", "local,anthropic")
    listed = {p.name: p.configured() for p in default_providers()}
    assert listed == {"local": True, "anthropic": False}  # anthropic has no key in the tests


def test_it_costs_nothing_whatever_the_model():
    assert cost_usd("local", "gpt-oss:20b", 1_000_000, 1_000_000) == 0.0
    assert cost_usd("local", "any-model-at-all", 5, 5, 3, 3) == 0.0
    assert cost_usd("anthropic", "some-unpriced-model", 5, 5) is None  # only local is free by definition


def test_a_busy_server_is_retried_a_bounded_number_of_times_then_succeeds(ollama):
    server = ollama((503, {"error": "busy"}, 0), (200, TOOL_ANSWER, 0))
    r = client(max_attempts_per_provider=2).chat(MESSAGES)
    assert r.provider == "local" and len(server.requests) == 2 and [a["outcome"] for a in r.attempts] == ["error", "ok"]


def test_a_server_that_stays_down_is_tried_at_most_max_attempts_and_the_circuit_opens(ollama):
    server = ollama((503, {"error": "loading model"}, 0))
    c = client(max_attempts_per_provider=2, breaker_threshold=2)
    with pytest.raises(LLMUnavailable):
        c.chat(MESSAGES)
    assert len(server.requests) == 2
    with pytest.raises(LLMUnavailable) as e:
        c.chat(MESSAGES)
    assert len(server.requests) == 2 and e.value.attempts == [{"provider": "local", "outcome": "skipped", "reason": "circuit_open"}]


def test_a_client_error_is_permanent_and_not_retried(ollama):
    server = ollama((404, {"error": "model 'gpt-oss:20b' not found"}, 0))
    with pytest.raises(LLMUnavailable) as e:
        client(max_attempts_per_provider=3).chat(MESSAGES)
    assert len(server.requests) == 1 and e.value.attempts[0]["kind"] == "permanent"


def test_nothing_listening_is_a_transient_failure_that_ends_in_llm_unavailable_not_a_crash(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:9/v1")  # the discard port: connection refused
    with pytest.raises(LLMUnavailable) as e:
        client(max_attempts_per_provider=2).chat(MESSAGES)
    assert [a["kind"] for a in e.value.attempts if a["outcome"] == "error"] == ["transient", "transient"]


def test_a_model_that_is_too_slow_times_out_and_the_turns_budget_holds(ollama):
    server = ollama((200, TOOL_ANSWER, 1.0))  # a model still loading: it answers after 1 s
    t0 = time.perf_counter()
    with pytest.raises(LLMUnavailable) as e:
        client(timeout_s=0.2, total_budget_s=0.5, max_attempts_per_provider=5).chat(MESSAGES)
    assert time.perf_counter() - t0 < 0.9 and len(server.requests) <= 3  # bounded by the budget, not by the 5 attempts
    assert any("timeout" in a.get("error", "").lower() for a in e.value.attempts)


def orchestrator(llm):
    orch = Orchestrator(SessionStore(ttl_seconds=900), llm=lambda: llm)
    tok = orch.session_store.issue("CLI-FIX0001", {"segment": "Premium", "country": "México", "customer_status": "Active"}).token
    return orch, tok


def test_a_turn_answered_by_the_local_model_is_rendered_from_verified_data_and_costs_zero(ollama):
    ollama((200, TOOL_ANSWER, 0))
    orch, tok = orchestrator(LLMClient(sleep=lambda s: None))
    r = orch.handle_message(tok, "¿saldo de mi ahorro 0001?")
    assert r.disposition == "AUTO_RESOLVE" and "2,455.81" in r.response_text
    assert (r.provider, r.cost_usd, r.llm_calls) == ("local", 0.0, 1)


def test_a_local_model_that_is_down_ends_in_the_same_safe_handoff(ollama):
    ollama((503, {"error": "down"}, 0))
    orch, tok = orchestrator(LLMClient(sleep=lambda s: None))
    r = orch.handle_message(tok, "movimientos de mi tarjeta")
    assert (r.disposition, r.category) == ("ESCALATE", "llm_unavailable") and r.ticket_id and r.verified_facts == []
