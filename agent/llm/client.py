"""LLM client: Groq, Together AI and Anthropic (Claude) in a configurable
order (LLM_PROVIDERS), with bounded retries.

Reliability contract (what "bounded retries, safe fallback" means here):
- Every request has a timeout; every turn has a total time budget.
- Only transient failures (timeouts, connection errors, 429, 5xx) are
  retried, with jittered exponential backoff and no sleep after the last
  attempt. Permanent ones (auth, bad request, missing key) move straight to
  the next provider.
- A per-provider circuit breaker skips a provider that just failed
  repeatedly, so an outage costs one timeout, not one per request.
- If every provider fails, LLMUnavailable is raised; the orchestrator turns
  that into an escalation, never a crash or a guessed answer.
Each response carries token usage and the attempt log for tracing and cost.
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class Usage:
    prompt_tokens: int = 0  # uncached input
    completion_tokens: int = 0
    cache_read_tokens: int = 0  # Anthropic prompt caching: billed at 0.1x input
    cache_write_tokens: int = 0  # billed at 1.25x input

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.prompt_tokens + other.prompt_tokens, self.completion_tokens + other.completion_tokens,
                     self.cache_read_tokens + other.cache_read_tokens, self.cache_write_tokens + other.cache_write_tokens)

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass
class LLMResponse:
    content: Optional[str]
    tool_calls: list[dict[str, Any]]
    provider: str
    latency_ms: float
    model: str | None = None
    usage: Usage = field(default_factory=Usage)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    raw: Any = None


class LLMUnavailable(Exception):
    def __init__(self, message: str, attempts: list[dict[str, Any]]):
        super().__init__(message)
        self.attempts = attempts


class ModelRefusal(ValueError):
    """The model declined the request (stop_reason "refusal"): not an answer, and not worth retrying."""


@dataclass(frozen=True)
class Provider:
    name: str
    model: str
    api_key_env: str
    factory: Callable[[str, float], Any]
    per_request_timeout: bool = True  # SDK accepts timeout= on create()
    call: Callable[..., tuple] | None = None  # None: OpenAI-compatible chat.completions


def openai_compatible_call(sdk, p: Provider, messages, tools, temperature: float, timeout: float) -> tuple:
    kwargs: dict[str, Any] = {"model": p.model, "messages": messages, "temperature": temperature}
    if p.per_request_timeout:
        kwargs["timeout"] = timeout
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    completion = sdk.chat.completions.create(**kwargs)
    msg = completion.choices[0].message
    tool_calls = [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                  for tc in (getattr(msg, "tool_calls", None) or [])]
    u = getattr(completion, "usage", None)
    return msg.content, tool_calls, Usage(getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0), p.model, completion


ANTHROPIC_MAX_TOKENS = 4096  # covers adaptive thinking plus the tool call on models that think by default
SERVER_FALLBACK_MODELS = {"claude-opus-5"}  # server-side refusal fallback ("default" routing by refusal category)


def anthropic_call(sdk, p: Provider, messages, tools, temperature: float, timeout: float) -> tuple:
    """Claude Messages API. No sampling parameters (current models reject
    them); effort instead, except on Haiku, which rejects effort. A refusal
    raises ModelRefusal so the next provider, or an escalation, takes over."""
    kwargs: dict[str, Any] = {
        "model": p.model, "max_tokens": ANTHROPIC_MAX_TOKENS, "timeout": timeout,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")],
    }
    system = [{"type": "text", "text": m["content"]} for m in messages if m["role"] == "system"]
    if system:
        # Cache breakpoint on the first (fixed) system block: tools render before it, so both are cached;
        # per-customer blocks after it are not. Below the model's minimum prefix it silently doesn't cache.
        system[0]["cache_control"] = {"type": "ephemeral"}
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                            "input_schema": t["function"]["parameters"]} for t in tools]
    effort = os.environ.get("ANTHROPIC_EFFORT", "low")
    if effort and not p.model.startswith("claude-haiku"):
        kwargs["output_config"] = {"effort": effort}
    if p.model in SERVER_FALLBACK_MODELS and os.environ.get("ANTHROPIC_FALLBACKS", "1") != "0":
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"
    msg = sdk.beta.messages.create(**kwargs)
    if msg.stop_reason == "refusal":
        raise ModelRefusal(f"{p.model} declined the request")
    text = "".join(b.text for b in msg.content if b.type == "text") or None
    tool_calls = [{"id": b.id, "name": b.name, "arguments": json.dumps(b.input, ensure_ascii=False)}
                  for b in msg.content if b.type == "tool_use"]
    u = msg.usage
    usage = Usage(u.input_tokens, u.output_tokens, getattr(u, "cache_read_input_tokens", 0) or 0,
                  getattr(u, "cache_creation_input_tokens", 0) or 0)
    return text, tool_calls, usage, msg.model, msg


def _groq_factory(api_key: str, timeout: float):
    from groq import Groq

    return Groq(api_key=api_key, timeout=timeout, max_retries=0)


def _together_factory(api_key: str, timeout: float):
    from together import Together

    try:
        return Together(api_key=api_key, timeout=timeout, max_retries=0)
    except TypeError:  # older SDKs don't take these kwargs
        return Together(api_key=api_key)


def _anthropic_factory(api_key: str, timeout: float):
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)


def default_providers() -> list[Provider]:
    """In LLM_PROVIDERS order (default: groq, together, anthropic); a provider without its key is skipped at call time."""
    known = {
        "groq": Provider("groq", os.environ.get("GROQ_MODEL", os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")),
                         "GROQ_API_KEY", _groq_factory),
        "together": Provider("together", os.environ.get("TOGETHER_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
                             "TOGETHER_API_KEY", _together_factory, per_request_timeout=False),
        "anthropic": Provider("anthropic", os.environ.get("ANTHROPIC_MODEL", "claude-opus-5"), "ANTHROPIC_API_KEY",
                              _anthropic_factory, call=anthropic_call),
    }
    order = [n.strip() for n in os.environ.get("LLM_PROVIDERS", "groq,together,anthropic").split(",")]
    return [known[n] for n in order if n in known]


def classify_error(exc: Exception) -> str:
    if isinstance(exc, (TypeError, ValueError, AttributeError, KeyError)):
        return "permanent"  # our bug or an SDK contract mismatch; retrying can't help
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return "transient" if status == 429 or status >= 500 else "permanent"
    name = type(exc).__name__.lower()
    if any(k in name for k in ("timeout", "connection", "ratelimit", "unavailable", "internalserver")):
        return "transient"
    if any(k in name for k in ("authentication", "permission", "badrequest", "notfound", "invalid")):
        return "permanent"
    return "transient"


class LLMClient:
    def __init__(
        self,
        providers: list[Provider] | None = None,
        timeout_s: float | None = None,
        total_budget_s: float | None = None,
        max_attempts_per_provider: int = 2,
        backoff_base_s: float = 0.5,
        breaker_threshold: int = 2,
        breaker_cooldown_s: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.providers = providers or default_providers()
        self.timeout_s = timeout_s or float(os.environ.get("LLM_TIMEOUT_SECONDS", "12"))
        self.total_budget_s = total_budget_s or float(os.environ.get("LLM_TOTAL_BUDGET_SECONDS", "25"))
        self.max_attempts = max_attempts_per_provider
        self.backoff_base_s = backoff_base_s
        self.breaker_threshold = breaker_threshold
        self.breaker_cooldown_s = breaker_cooldown_s
        self._sleep = sleep
        self._clients: dict[str, Any] = {}
        self._failures: dict[str, int] = {}
        self._down_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def _client(self, p: Provider, api_key: str):
        if p.name not in self._clients:
            self._clients[p.name] = p.factory(api_key, self.timeout_s)
        return self._clients[p.name]

    def _record_failure(self, name: str) -> None:
        with self._lock:
            self._failures[name] = self._failures.get(name, 0) + 1
            if self._failures[name] >= self.breaker_threshold:
                self._down_until[name] = time.time() + self.breaker_cooldown_s

    def _record_success(self, name: str) -> None:
        with self._lock:
            self._failures[name] = 0
            self._down_until.pop(name, None)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             temperature: float = 0.0) -> LLMResponse:
        start = time.time()
        deadline = start + self.total_budget_s
        attempts: list[dict[str, Any]] = []
        for p in self.providers:
            api_key = os.environ.get(p.api_key_env)
            if not api_key:
                attempts.append({"provider": p.name, "outcome": "skipped", "reason": f"{p.api_key_env} not set"})
                continue
            if self._down_until.get(p.name, 0) > time.time():
                attempts.append({"provider": p.name, "outcome": "skipped", "reason": "circuit_open"})
                continue
            for attempt in range(self.max_attempts):
                remaining = deadline - time.time()
                if remaining <= 0:
                    attempts.append({"provider": p.name, "outcome": "skipped", "reason": "turn_budget_exhausted"})
                    break
                t0 = time.time()
                try:
                    content, tool_calls, usage, served_model, raw = (p.call or openai_compatible_call)(
                        self._client(p, api_key), p, messages, tools, temperature, min(self.timeout_s, remaining))
                    attempts.append({"provider": p.name, "outcome": "ok", "ms": round((time.time() - t0) * 1000, 1)})
                    self._record_success(p.name)
                    return LLMResponse(content, tool_calls, p.name, (time.time() - start) * 1000, served_model, usage, attempts, raw)
                except Exception as exc:  # noqa: BLE001 - SDK error types vary by provider
                    kind = classify_error(exc)
                    attempts.append({"provider": p.name, "outcome": "error", "kind": kind, "error": f"{type(exc).__name__}: {exc}"[:300],
                                     "ms": round((time.time() - t0) * 1000, 1)})
                    logger.warning("LLM %s attempt %d failed (%s): %s", p.name, attempt + 1, kind, exc)
                    if kind == "permanent":
                        break
                    self._record_failure(p.name)
                    if attempt < self.max_attempts - 1:
                        delay = self.backoff_base_s * (2 ** attempt) * (1 + random.random() * 0.25)
                        self._sleep(max(0.0, min(delay, deadline - time.time())))
        raise LLMUnavailable("all LLM providers failed or were unavailable", attempts)


_default_client: LLMClient | None = None


def get_default_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
