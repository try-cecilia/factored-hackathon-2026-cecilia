"""LLM client: Groq, Together AI, Anthropic (Claude) and a local model (Ollama or any
OpenAI-compatible server, no key) in a configurable order (LLM_PROVIDERS), with bounded retries.

Reliability contract (what "bounded retries, safe fallback" means here):
- Every request has a timeout; every turn has a total time budget, which is also capped by the turn's own deadline
  (agent/resilience.py) when the orchestrator has started one. Output is capped (LLM_MAX_OUTPUT_TOKENS).
- Only transient failures (timeouts, connection errors, 429, 5xx) are
  retried, with jittered exponential backoff, no sleep after the last attempt
  and no sleep that would outlast the budget. Permanent ones (auth, bad
  request, missing key) move straight to the next provider.
- A per-provider circuit breaker skips a provider that just failed
  repeatedly, so an outage costs one timeout, not one per request.
- If every provider fails, LLMUnavailable is raised; the orchestrator turns
  that into an escalation, never a crash or a guessed answer.
Each response carries token usage and the attempt log for tracing and cost.
"""
from __future__ import annotations

import contextvars
import dataclasses
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from agent.resilience import backoff_delay, current_deadline

logger = logging.getLogger(__name__)

# The wall-clock instant (time.perf_counter) by which the model call in this context must be over, or None.
call_limit: contextvars.ContextVar[float | None] = contextvars.ContextVar("call_limit", default=None)


class DeadlineTransport:
    """Marks an httpx transport that puts a limit on a whole model call, not only on each read (the SDKs' timeouts are per
    read, so a server that keeps sending pieces, of the headers or of the body, never trips them). The limit comes from
    `call_limit` and is enforced at the network layer, on every connect, read and write: each wait is capped to what is
    left, and a read that returns after the limit raises, which makes the client close the connection. Headers and body
    are both covered because both arrive through those reads. The call runs on the caller's own thread, so cancelling it
    needs no extra thread and leaves nothing behind. Built by `deadline_transport` for whichever httpx the client uses:
    the SDKs ship their own (`httpx2`, over `httpcore2`), the local provider uses `httpx` (over `httpcore`)."""


def deadline_transport(mod: Any, max_connections: int = 200) -> Any:
    import importlib

    class Transport(DeadlineTransport, mod.BaseTransport):
        def __init__(self) -> None:
            self._inner = mod.HTTPTransport(limits=mod.Limits(max_connections=max_connections, max_keepalive_connections=min(50, max_connections)))
            core = importlib.import_module(type(self._inner._pool).__module__.partition(".")[0])  # httpcore or httpcore2
            self._inner._pool._network_backend = _limited_backend(core, self._inner._pool._network_backend)

        def handle_request(self, request):
            limit = call_limit.get()
            if limit is not None:
                left = limit - time.perf_counter()
                if left <= 0:
                    raise mod.ConnectTimeout("the call's time limit had passed before it started")
                # The wait for a free connection of the pool (`pool`) is a phase of the call like the others: without this
                # cap it runs on the client's own timeout, outside the limit, when the pool is busy.
                timeout = request.extensions.get("timeout") or {}
                request.extensions["timeout"] = {k: min(timeout.get(k) or left, left) for k in ("connect", "read", "write", "pool")}
            return self._inner.handle_request(request)

        def close(self) -> None:
            self._inner.close()

    return Transport()


def _limited_backend(core: Any, inner: Any) -> Any:
    """`inner` (an httpcore network backend) with the call's limit enforced on every connect, read and write."""

    def cap(timeout: float | None) -> float | None:
        limit = call_limit.get()
        if limit is None:
            return timeout
        left = limit - time.perf_counter()
        if left <= 0:
            raise core.ReadTimeout("the call's time limit passed")
        return left if timeout is None else min(timeout, left)

    def check() -> None:
        limit = call_limit.get()
        if limit is not None and time.perf_counter() > limit:
            raise core.ReadTimeout("the call's time limit passed while its answer was still arriving")

    class Stream(core.NetworkStream):
        def __init__(self, stream):
            self._stream = stream

        def read(self, max_bytes, timeout=None):
            data = self._stream.read(max_bytes, cap(timeout))
            check()  # a piece that arrived in time but after the limit is dropped, and the connection with it
            return data

        def write(self, buffer, timeout=None):
            self._stream.write(buffer, cap(timeout))

        def close(self):
            self._stream.close()

        def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            return Stream(self._stream.start_tls(ssl_context, server_hostname, cap(timeout)))

        def get_extra_info(self, info):
            return self._stream.get_extra_info(info)

    class Backend(core.NetworkBackend):
        def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            return Stream(inner.connect_tcp(host, port, cap(timeout), local_address, socket_options))

        def connect_unix_socket(self, path, timeout=None, socket_options=None):
            return Stream(inner.connect_unix_socket(path, cap(timeout), socket_options))

        def sleep(self, seconds):
            inner.sleep(seconds)

    return Backend()


def _sdk_http_client(sdk: Any) -> Any:
    """An HTTP client for `sdk` (its module) over the deadline transport. Each SDK refuses a client from any httpx but
    its own (anthropic ships `httpx2`, groq and together use `httpx`), so the one to build on is read off the SDK's
    own default client class."""
    import importlib

    root = next(c.__module__.partition(".")[0] for c in sdk.DefaultHttpxClient.__mro__ if c.__module__.partition(".")[0].startswith("httpx"))
    mod = importlib.import_module(root)
    return mod.Client(transport=deadline_transport(mod), follow_redirects=True)


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


class IncompleteResponse(ValueError):
    """The answer was cut off (token or context limit): a tool call in it may be truncated, so it is not acted on."""


@dataclass(frozen=True)
class Provider:
    name: str
    model: str
    api_key_env: str
    factory: Callable[[str, float], Any]
    per_request_timeout: bool = True  # SDK accepts timeout= on create()
    call: Callable[..., tuple] | None = None  # None: OpenAI-compatible chat.completions
    keyless: bool = False  # a local server: listed in LLM_PROVIDERS means wanted, and no key is needed

    def configured(self) -> bool:
        return self.keyless or bool(os.environ.get(self.api_key_env))


def _recover_failed_tool_call(exc: Exception, tools: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Groq validates the model's tool call against our schema server-side and answers 400 tool_use_failed when it
    sent `null` for a slot the customer left unfilled (allowing null in the schema is rejected by Groq's metaschema
    check). The rejected call comes back in `failed_generation`: recover it when it names an offered tool. The
    orchestrator still sanitizes its arguments and drops nulls, so this only saves the turn from a needless failure."""
    body = getattr(exc, "body", None)
    body = body.get("error", body) if isinstance(body, dict) else None
    if not body or body.get("code") != "tool_use_failed":
        return None
    try:
        call = json.loads(body.get("failed_generation") or "")
        name, args = call["name"], call.get("arguments") or {}
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if not isinstance(args, dict) or name not in {t["function"]["name"] for t in tools or []}:
        return None
    return {"id": "recovered", "name": name, "arguments": json.dumps(args, ensure_ascii=False)}


def max_output_tokens() -> int:
    """The cap on what one model call may generate (LLM_MAX_OUTPUT_TOKENS): it bounds cost and time per call."""
    return int(os.environ.get("LLM_MAX_OUTPUT_TOKENS") or ANTHROPIC_MAX_TOKENS)


def openai_compatible_call(sdk, p: Provider, messages, tools, temperature: float, timeout: float) -> tuple:
    kwargs: dict[str, Any] = {"model": p.model, "messages": messages, "temperature": temperature,
                              "max_tokens": max_output_tokens()}
    if p.per_request_timeout:
        kwargs["timeout"] = timeout
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    try:
        completion = sdk.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 - only Groq's tool_use_failed is recovered; anything else propagates
        recovered = _recover_failed_tool_call(exc, tools)
        if recovered is None:
            raise
        return None, [recovered], Usage(), p.model, exc
    if getattr(completion.choices[0], "finish_reason", None) == "length":
        raise IncompleteResponse(f"{p.model} hit its output limit")
    msg = completion.choices[0].message
    tool_calls = [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                  for tc in (getattr(msg, "tool_calls", None) or [])]
    u = getattr(completion, "usage", None)
    return msg.content, tool_calls, Usage(getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0), p.model, completion


ANTHROPIC_MAX_TOKENS = 4096  # covers adaptive thinking plus the tool call on models that think by default
SERVER_FALLBACK_MODELS = {"claude-opus-5"}  # server-side refusal fallback ("default" routing by refusal category)


def anthropic_effort(model: str) -> str | None:
    """The effort sent with a Claude request (ANTHROPIC_EFFORT, low by default); Haiku 4.5 takes none."""
    effort = os.environ.get("ANTHROPIC_EFFORT", "low")
    return effort if effort and not model.startswith("claude-haiku") else None


def anthropic_call(sdk, p: Provider, messages, tools, temperature: float, timeout: float) -> tuple:
    """Claude Messages API. No sampling parameters (current models reject
    them); effort instead, except on Haiku, which rejects effort. A refusal
    raises ModelRefusal so the next provider, or an escalation, takes over."""
    turns = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
    while turns and turns[0]["role"] != "user":  # the Messages API requires the customer to speak first
        turns.pop(0)
    kwargs: dict[str, Any] = {"model": p.model, "max_tokens": max_output_tokens(), "timeout": timeout, "messages": turns}
    system = [{"type": "text", "text": m["content"]} for m in messages if m["role"] == "system"]
    if system:
        # Cache breakpoint on the first (fixed) system block: tools render before it, so both are cached;
        # per-customer blocks after it are not. Below the model's minimum prefix it silently doesn't cache.
        system[0]["cache_control"] = {"type": "ephemeral"}
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                            "input_schema": t["function"]["parameters"]} for t in tools]
    if effort := anthropic_effort(p.model):
        kwargs["output_config"] = {"effort": effort}
    if p.model in SERVER_FALLBACK_MODELS and os.environ.get("ANTHROPIC_FALLBACKS", "1") != "0":
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"
    msg = sdk.beta.messages.create(**kwargs)
    if msg.stop_reason == "refusal":
        raise ModelRefusal(f"{p.model} declined the request")
    if msg.stop_reason not in ("end_turn", "tool_use", "stop_sequence"):
        raise IncompleteResponse(f"{p.model} stopped with {msg.stop_reason}")
    text = "".join(b.text for b in msg.content if b.type == "text") or None
    tool_calls = [{"id": b.id, "name": b.name, "arguments": json.dumps(b.input, ensure_ascii=False)}
                  for b in msg.content if b.type == "tool_use"]
    u = msg.usage
    usage = Usage(u.input_tokens, u.output_tokens, getattr(u, "cache_read_input_tokens", 0) or 0,
                  getattr(u, "cache_creation_input_tokens", 0) or 0)
    return text, tool_calls, usage, msg.model, msg


def _groq_factory(api_key: str, timeout: float):
    from groq import Groq

    import groq

    return Groq(api_key=api_key, timeout=timeout, max_retries=0, http_client=_sdk_http_client(groq))


def _together_factory(api_key: str, timeout: float):
    from together import Together

    try:
        import together

        return Together(api_key=api_key, timeout=timeout, max_retries=0, http_client=_sdk_http_client(together))
    except TypeError:  # older SDKs don't take these kwargs
        return Together(api_key=api_key)


class _LocalCompletions:
    """POST {base}/chat/completions, the OpenAI wire format that Ollama, llama.cpp and vLLM serve. Over httpx, so no
    SDK and no key. Answers come back as attribute-style objects, like the SDKs' (openai_compatible_call reads them
    the same way); an HTTP error status raises with `.response.status_code`, which classify_error already reads."""

    def __init__(self, base_url: str, timeout: float):
        import httpx

        self._http = httpx.Client(base_url=base_url.rstrip("/") + "/", timeout=timeout, transport=deadline_transport(httpx))

    def create(self, **kwargs):
        from types import SimpleNamespace

        timeout = kwargs.pop("timeout", None)
        r = self._http.post("chat/completions", json=kwargs, timeout=timeout)
        r.raise_for_status()
        return json.loads(r.text, object_hook=lambda d: SimpleNamespace(**d))


def local_base_url() -> str:
    return os.environ.get("LOCAL_LLM_BASE_URL") or "http://127.0.0.1:11434/v1"


def _local_factory(api_key: str, timeout: float):
    from types import SimpleNamespace

    return SimpleNamespace(chat=SimpleNamespace(completions=_LocalCompletions(local_base_url(), timeout)))


def _anthropic_factory(api_key: str, timeout: float):
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0, http_client=_sdk_http_client(anthropic))


def _known_providers() -> dict[str, Provider]:
    return {
        # llama-3.3-70b-versatile left Groq's free/developer tiers on 2026-08-16; gpt-oss-120b is Groq's replacement.
        "groq": Provider("groq", os.environ.get("GROQ_MODEL", os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")),
                         "GROQ_API_KEY", _groq_factory),
        "together": Provider("together", os.environ.get("TOGETHER_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
                             "TOGETHER_API_KEY", _together_factory, per_request_timeout=False),
        # A model served on this machine or in this compose (Ollama by default): no account, no key, no cost. Only
        # tried when LLM_PROVIDERS names it. Local models can be slow: raise LLM_TIMEOUT_SECONDS and the budgets.
        "local": Provider("local", os.environ.get("LOCAL_LLM_MODEL", "gpt-oss:20b"), "LOCAL_LLM_BASE_URL", _local_factory,
                          keyless=True),
        # Sonnet 5: the higher safe automated resolution and the lower cost per safe resolution on the held-out
        # workload (eval/reports/SYSTEM_EVAL_LIVE.md), and what render.yaml runs.
        "anthropic": Provider("anthropic", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"), "ANTHROPIC_API_KEY",
                              _anthropic_factory, call=anthropic_call),
    }


def default_providers() -> list[Provider]:
    """In LLM_PROVIDERS order (default: anthropic, groq, together: Claude is the provider measured live so far);
    a provider without its key is skipped at call time."""
    known = _known_providers()
    order = [n.strip() for n in os.environ.get("LLM_PROVIDERS", "anthropic,groq,together").split(",")]
    return [known[n] for n in order if n in known]


def candidate_client(spec: str) -> "LLMClient":
    """A client for one `provider:model` (e.g. groq:openai/gpt-oss-120b) with no fallback to another provider: a
    candidate under test has to fail on its own, or its numbers would be the fallback's."""
    name, _, model = spec.partition(":")
    known = _known_providers()
    if name not in known or not model:
        raise ValueError(f"expected provider:model with a provider in {sorted(known)}, got {spec!r}")
    return LLMClient(providers=[dataclasses.replace(known[name], model=model)], max_attempts_per_provider=1)


def retry_after_hint(exc: Exception) -> float | None:
    """Seconds a provider asked us to wait: the Retry-After header of the response an SDK error carries."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    try:
        return float(headers.get("retry-after")) if headers is not None else None
    except (TypeError, ValueError):
        return None


# Error codes providers send that say what went wrong without saying anything of what we sent.
KNOWN_ERROR_CODES = frozenset({
    "rate_limit_exceeded", "rate_limit_error", "insufficient_quota", "overloaded_error", "server_error", "api_error",
    "invalid_api_key", "authentication_error", "permission_error", "not_found_error", "model_not_found",
    "invalid_request_error", "context_length_exceeded", "tool_use_failed", "request_too_large", "timeout"})


def safe_error(exc: Exception) -> str:
    """What may be recorded about a provider error: its type, its HTTP status and a code from KNOWN_ERROR_CODES. Never
    its message or body: providers quote the input they rejected, and the input holds what the customer typed."""
    out = type(exc).__name__
    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    if isinstance(status, int):
        out += f" status={status}"
    body = getattr(exc, "body", None)
    if body is None and response is not None:
        try:
            body = json.loads(response.text)
        except (ValueError, TypeError, AttributeError):
            body = None
    err = body.get("error", body) if isinstance(body, dict) else None
    for key in ("code", "type"):
        code = err.get(key) if isinstance(err, dict) else None
        if isinstance(code, str) and code in KNOWN_ERROR_CODES:
            return f"{out} code={code}"
    return out


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
        backoff_cap_s: float = 4.0,
        breaker_threshold: int = 2,
        breaker_cooldown_s: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.providers = providers or default_providers()
        self.timeout_s = timeout_s or float(os.environ.get("LLM_TIMEOUT_SECONDS", "12"))
        self.total_budget_s = total_budget_s or float(os.environ.get("LLM_TOTAL_BUDGET_SECONDS", "25"))
        self.max_attempts = max_attempts_per_provider
        self.backoff_base_s = backoff_base_s
        self.backoff_cap_s = backoff_cap_s
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

    def _record_failure(self, name: str) -> bool:
        """Count a failure; True if the circuit is now open. The counter is not reset by the cooldown, so the first call
        after it is a single probe: one more failure opens the circuit again, one success closes it."""
        with self._lock:
            self._failures[name] = self._failures.get(name, 0) + 1
            if self._failures[name] >= self.breaker_threshold:
                self._down_until[name] = time.time() + self.breaker_cooldown_s
                return True
            return False

    def _record_success(self, name: str) -> None:
        with self._lock:
            self._failures[name] = 0
            self._down_until.pop(name, None)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             temperature: float = 0.0) -> LLMResponse:
        start = time.perf_counter()  # durations and the turn's deadline on a monotonic clock, fine to the millisecond
        deadline = start + self.total_budget_s
        turn = current_deadline.get()  # the orchestrator's clock for the whole turn: the model never gets more than what is left
        if turn is not None:
            deadline = min(deadline, turn.at)
        attempts: list[dict[str, Any]] = []
        for p in self.providers:
            api_key = os.environ.get(p.api_key_env) or ""
            if not p.configured():
                attempts.append({"provider": p.name, "outcome": "skipped", "reason": f"{p.api_key_env} not set"})
                continue
            if self._down_until.get(p.name, 0) > time.time():
                attempts.append({"provider": p.name, "outcome": "skipped", "reason": "circuit_open"})
                continue
            for attempt in range(self.max_attempts):
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    attempts.append({"provider": p.name, "outcome": "skipped", "reason": "turn_budget_exhausted"})
                    break
                t0 = time.perf_counter()
                try:
                    request_s = min(self.timeout_s, remaining)
                    sdk = self._client(p, api_key)  # built (and its SDK imported) before the call's clock starts
                    # The transport enforces the limit on the wall clock. It never goes past the total budget: building the client
                    # (an import, a TLS context, a pause of the garbage collector) is time the budget already counts.
                    limit = call_limit.set(min(time.perf_counter() + request_s, deadline))
                    try:
                        content, tool_calls, usage, served_model, raw = (p.call or openai_compatible_call)(
                            sdk, p, messages, tools, temperature, request_s)
                    finally:
                        call_limit.reset(limit)
                    attempts.append({"provider": p.name, "outcome": "ok", "ms": round((time.perf_counter() - t0) * 1000, 1)})
                    self._record_success(p.name)
                    return LLMResponse(content, tool_calls, p.name, (time.perf_counter() - start) * 1000, served_model, usage, attempts, raw)
                except Exception as exc:  # noqa: BLE001 - SDK error types vary by provider
                    kind = classify_error(exc)
                    hinted = retry_after_hint(exc)
                    attempts.append({"provider": p.name, "outcome": "error", "kind": kind,
                                     "error": safe_error(exc), "ms": round((time.perf_counter() - t0) * 1000, 1),
                                     **({"retry_after_s": round(hinted, 1)} if hinted is not None else {})})
                    logger.warning("LLM %s attempt %d failed (%s): %s", p.name, attempt + 1, kind, safe_error(exc))
                    if kind == "permanent":
                        break
                    if self._record_failure(p.name):
                        break  # the circuit just opened: no more attempts on a provider that is now declared down
                    if attempt < self.max_attempts - 1:
                        delay = backoff_delay(attempt, self.backoff_base_s, self.backoff_cap_s, random.random)
                        if hinted is not None:  # the provider said when to come back: never earlier than that
                            delay = max(delay, hinted)
                        if delay >= deadline - time.perf_counter():  # waiting would leave no time for the retry itself
                            attempts.append({"provider": p.name, "outcome": "skipped", "reason": "turn_budget_exhausted"})
                            break
                        self._sleep(delay)
        raise LLMUnavailable("all LLM providers failed or were unavailable", attempts)


_default_client: LLMClient | None = None


def get_default_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
