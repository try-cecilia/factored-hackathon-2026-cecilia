"""Scripted stand-in for agent.llm.client.LLMClient, shared by tests and the
offline evaluation harness.

Anything built on this is an OFFLINE SIMULATION: the scripted responses
encode what a well-behaved model *should* do for a given utterance, not what
a live model decided. It exercises every deterministic layer (policy, tools,
rendering, escalation) for real; it measures nothing about the model's own
judgment, latency or cost. Reports that use it say so in their header.
"""
from __future__ import annotations

import json

from agent.llm.client import LLMResponse, LLMUnavailable, Usage


class FakeLLMClient:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.call_count = 0
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools=None, temperature=0.0):
        self.call_count += 1
        self.calls.append(list(messages))
        if not self._responses:
            raise AssertionError("FakeLLMClient ran out of scripted responses")
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def tool_call_response(name: str, arguments: dict, *more: tuple[str, dict]) -> LLMResponse:
    calls = [(name, arguments), *more]
    return LLMResponse(content=None, provider="scripted", latency_ms=0.0, model="scripted", usage=Usage(),
                       tool_calls=[{"id": f"call_{i}", "name": n, "arguments": json.dumps(a)} for i, (n, a) in enumerate(calls)])


def text_response(content: str) -> LLMResponse:
    return LLMResponse(content=content, tool_calls=[], provider="scripted", latency_ms=0.0, model="scripted", usage=Usage())


def unavailable() -> LLMUnavailable:
    return LLMUnavailable("scripted outage", [{"provider": "scripted", "outcome": "error", "kind": "transient"}])
