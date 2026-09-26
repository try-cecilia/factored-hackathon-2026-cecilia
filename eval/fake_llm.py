"""Scripted stand-in for agent.llm.client.LLMClient, shared by unit tests and
the offline guardrail evaluation harness.

Anything built on this is an OFFLINE SIMULATION: the scripted responses
encode what a well-behaved model *should* do for a given utterance, not what
a live Llama call actually decided. Per the challenge's evaluation-evidence
requirement, this must never be reported as a measured production result —
see the header of eval/run_guardrail_eval.py for how the report labels it.
"""
from __future__ import annotations

import json

from agent.llm.client import LLMResponse


class FakeLLMClient:
    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.call_count = 0

    def chat(self, messages, tools=None, temperature=0.1):
        self.call_count += 1
        if not self._responses:
            raise AssertionError("FakeLLMClient ran out of scripted responses")
        return self._responses.pop(0)


def tool_call_response(name: str, arguments: dict, provider: str = "fake") -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[{"id": "call_1", "name": name, "arguments": json.dumps(arguments)}],
        provider=provider,
        latency_ms=1.0,
    )


def text_response(content: str, provider: str = "fake") -> LLMResponse:
    return LLMResponse(content=content, tool_calls=[], provider=provider, latency_ms=1.0)
