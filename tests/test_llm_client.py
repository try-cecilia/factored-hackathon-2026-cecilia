"""Reliability behavior of agent/llm/client.py with fake provider SDKs."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.llm.client import LLMClient, LLMUnavailable, Provider


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
