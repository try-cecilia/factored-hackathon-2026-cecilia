"""Reliability behavior of agent/llm/client.py with fake provider SDKs."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.llm.client import LLMClient, LLMUnavailable, Provider, anthropic_call, default_providers
from agent.llm.pricing import cost_usd


class StatusError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def completion(content="ok", prompt=10, out=5):
    msg = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=out))


def fake_provider(name, outcomes, calls):
    """outcomes: list of Exception instances or 'ok', consumed per call."""

    def create(**kwargs):
        calls.append(name)
        o = outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return completion()

    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return Provider(name, f"{name}-model", f"{name.upper()}_KEY", lambda key, timeout: sdk)


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("P1_KEY", "k1")
    monkeypatch.setenv("P2_KEY", "k2")


def test_transient_error_retries_once_then_succeeds_with_usage(keys):
    calls, sleeps = [], []
    c = LLMClient([fake_provider("p1", [StatusError(503), "ok"], calls)], sleep=sleeps.append)
    r = c.chat([{"role": "user", "content": "hi"}])
    assert r.provider == "p1" and calls == ["p1", "p1"] and len(sleeps) == 1
    assert (r.usage.prompt_tokens, r.usage.completion_tokens) == (10, 5)


def test_permanent_error_falls_through_to_next_provider_without_sleeping(keys):
    calls, sleeps = [], []
    c = LLMClient([fake_provider("p1", [StatusError(401)], calls), fake_provider("p2", ["ok"], calls)], sleep=sleeps.append)
    r = c.chat([{"role": "user", "content": "hi"}])
    assert r.provider == "p2" and calls == ["p1", "p2"] and sleeps == []


def test_missing_key_is_skipped_instantly(monkeypatch):
    monkeypatch.delenv("P1_KEY", raising=False)
    monkeypatch.setenv("P2_KEY", "k2")
    calls, sleeps = [], []
    c = LLMClient([fake_provider("p1", ["ok"], calls), fake_provider("p2", ["ok"], calls)], sleep=sleeps.append)
    r = c.chat([{"role": "user", "content": "hi"}])
    assert r.provider == "p2" and calls == ["p2"] and sleeps == []
    assert r.attempts[0]["reason"] == "P1_KEY not set"


def test_no_sleep_after_final_attempt_and_unavailable_carries_attempts(keys):
    calls, sleeps = [], []
    c = LLMClient([fake_provider("p1", [TimeoutError(), TimeoutError()], calls),
                   fake_provider("p2", [StatusError(500), StatusError(500)], calls)], sleep=sleeps.append)
    with pytest.raises(LLMUnavailable) as exc:
        c.chat([{"role": "user", "content": "hi"}])
    assert calls == ["p1", "p1", "p2", "p2"]
    assert len(sleeps) == 2  # one between attempts per provider, none after the last
    assert len(exc.value.attempts) == 4


def anthropic_provider(model, responses, requests):
    """A stand-in for the anthropic SDK: records each request, replays responses shaped like BetaMessage."""

    def create(**kwargs):
        requests.append(kwargs)
        return responses.pop(0)

    sdk = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return Provider("anthropic", model, "ANTHROPIC_KEY_TEST", lambda key, timeout: sdk, call=anthropic_call)


def beta_message(blocks, stop_reason="tool_use", model="claude-opus-5", tokens=(1200, 80), cache=(0, 0)):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason, model=model,
                           usage=SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1],
                                                 cache_read_input_tokens=cache[0], cache_creation_input_tokens=cache[1]))


TOOL = {"type": "function", "function": {"name": "get_account_summary", "description": "Saldos.",
                                         "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": []}}}


def test_claude_request_carries_system_tools_and_no_sampling_params_and_its_tool_call_is_parsed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_KEY_TEST", "k")
    requests = []
    reply = beta_message([SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text="Consulto."),
                          SimpleNamespace(type="tool_use", id="toolu_1", name="get_account_summary", input={"product_id": "P1"})],
                         cache=(900, 0))
    c = LLMClient([anthropic_provider("claude-opus-5", [reply], requests)])
    r = c.chat([{"role": "system", "content": "reglas"}, {"role": "system", "content": "catálogo"},
                {"role": "user", "content": "saldo"}, {"role": "assistant", "content": "[respondido]"},
                {"role": "user", "content": "¿y la otra?"}], tools=[TOOL])
    sent = requests[0]
    # the fixed rules (with the tools rendered before them) are cached; the per-customer catalog is not
    assert sent["model"] == "claude-opus-5" and sent["system"] == [
        {"type": "text", "text": "reglas", "cache_control": {"type": "ephemeral"}}, {"type": "text", "text": "catálogo"}]
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant", "user"]
    assert sent["tools"] == [{"name": "get_account_summary", "description": "Saldos.",
                              "input_schema": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": []}}]
    assert "temperature" not in sent and sent["output_config"] == {"effort": "low"}
    assert sent["fallbacks"] == "default" and sent["betas"] == ["server-side-fallback-2026-07-01"]
    assert r.provider == "anthropic" and r.model == "claude-opus-5"
    assert r.tool_calls == [{"id": "toolu_1", "name": "get_account_summary", "arguments": '{"product_id": "P1"}'}]
    assert (r.usage.prompt_tokens, r.usage.completion_tokens, r.usage.cache_read_tokens) == (1200, 80, 900)


def test_a_dated_model_id_returned_by_the_api_is_priced_like_its_alias():
    # the API answers claude-haiku-4-5 requests with a dated snapshot id; cost must not become "not defined"
    assert cost_usd("anthropic", "claude-haiku-4-5-20251001", 1000, 100) == pytest.approx(0.0015)


def test_cached_prompt_tokens_are_billed_at_a_tenth_and_cache_writes_at_a_quarter_more():
    # claude-opus-5 list price: 5 USD/MTok in, 25 out -> 1000*5 + 100*25 + 1000*0.5 + 1000*6.25 = 14,250 USD/1e6
    assert cost_usd("anthropic", "claude-opus-5", 1000, 100, cache_read_tokens=1000, cache_write_tokens=1000) == pytest.approx(0.01425)


def test_haiku_gets_neither_effort_nor_server_side_fallbacks(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_KEY_TEST", "k")
    requests = []
    c = LLMClient([anthropic_provider("claude-haiku-4-5", [beta_message([], "end_turn", "claude-haiku-4-5")], requests)])
    c.chat([{"role": "user", "content": "hola"}], tools=[TOOL])
    assert not {"output_config", "fallbacks", "betas"} & set(requests[0])


def test_a_refusal_is_not_an_answer_and_the_next_provider_takes_the_turn(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_KEY_TEST", "k")
    monkeypatch.setenv("P2_KEY", "k2")
    calls, requests = [], []
    c = LLMClient([anthropic_provider("claude-opus-5", [beta_message([], "refusal")], requests), fake_provider("p2", ["ok"], calls)],
                  sleep=lambda s: None)
    r = c.chat([{"role": "user", "content": "hola"}], tools=[TOOL])
    assert r.provider == "p2" and len(requests) == 1  # permanent: not retried on the same provider
    assert r.attempts[0]["provider"] == "anthropic" and r.attempts[0]["kind"] == "permanent"


def test_provider_order_follows_LLM_PROVIDERS(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "anthropic, groq")
    assert [p.name for p in default_providers()] == ["anthropic", "groq"]


def test_every_default_provider_model_has_a_price(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDERS", raising=False)
    assert all(cost_usd(p.name, p.model, 1000, 100) is not None for p in default_providers())


def test_circuit_breaker_skips_a_provider_that_keeps_failing(keys):
    calls = []
    p1 = fake_provider("p1", [TimeoutError(), TimeoutError(), "ok"], calls)
    p2 = fake_provider("p2", ["ok", "ok"], calls)
    c = LLMClient([p1, p2], sleep=lambda s: None, breaker_threshold=2, breaker_cooldown_s=60)
    assert c.chat([{"role": "user", "content": "a"}]).provider == "p2"
    calls.clear()
    r = c.chat([{"role": "user", "content": "b"}])
    assert r.provider == "p2" and calls == ["p2"]  # p1 not even tried while the breaker is open
    assert r.attempts[0]["reason"] == "circuit_open"
