"""What every request goes through before a route sees it: trace ids, size and concurrency limits, a safe last resort.

Pure ASGI (no BaseHTTPMiddleware), so a streamed body and a client that disconnects behave.

- **Trace id.** Each request gets a server-made trace id, returned as `X-Request-ID` and in `traceparent`, and set for
  the code that runs inside it: the orchestrator adopts it as the turn's `trace_id`, so it is the same id in the
  response body, the trace record, the tool audit, the ticket and the logs (agent/observability.py). The caller's own
  `traceparent` / `X-Request-ID` are validated and kept beside it, never used as ours.
- **Size and slowness.** A body over MAX_REQUEST_BYTES (default 16 KiB; a chat message is at most 1,000 characters) is
  refused with 413, by its Content-Length when it declares one and by counting when it does not (chunked, or lying). A
  client that has not finished sending its body within REQUEST_BODY_TIMEOUT_SECONDS (default 10) gets 408: it cannot
  hold a connection open by trickling bytes.
- **Concurrency.** POST /chat is the expensive route (a model call of seconds). At most MAX_CONCURRENT_CHATS run at
  once (default 32, under the 40 threads of the server's pool, so the pool never queues silently behind it); up to
  CHAT_QUEUE_MAX (default 64) more wait at most CHAT_QUEUE_WAIT_SECONDS (default 5) for a slot; anything beyond that,
  or that waits longer, gets 503 with `Retry-After` at once instead of piling up behind a slow provider.
- **Last resort.** An exception nothing else handled becomes a 500 that says only "internal error" and carries the
  request id, and the type of the exception goes to the log. Nothing of the exception's text reaches the client.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import weakref
from typing import Any

from agent import observability
from agent.tools.audit import current_trace_id

logger = logging.getLogger("cecilai.api")


def _int_env(name: str, default: int) -> int:
    return int(os.environ.get(name) or default)


def limits() -> dict[str, Any]:
    """The limits in force, from the environment (read when the middleware is built, and by /admin/capacity)."""
    return {"max_request_bytes": _int_env("MAX_REQUEST_BYTES", 16_384), "max_concurrent_chats": _int_env("MAX_CONCURRENT_CHATS", 32),
            "chat_queue_max": _int_env("CHAT_QUEUE_MAX", 64), "chat_queue_wait_seconds": float(os.environ.get("CHAT_QUEUE_WAIT_SECONDS") or 5),
            "retry_after_seconds": _int_env("CHAT_RETRY_AFTER_SECONDS", 3),
            "request_body_timeout_seconds": float(os.environ.get("REQUEST_BODY_TIMEOUT_SECONDS") or 10)}


TIMED_OUT = b"timed out"  # a sentinel that no real body can be: identity-compared


class CapacityStats:
    """Counters an operator reads at /admin/capacity: how often each limit refused a request, and the peak load."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.inflight = self.waiting = self.inflight_peak = self.waiting_peak = 0
        self.rejected: dict[str, int] = {"busy": 0, "too_large": 0, "slow_body": 0}
        self.served = 0

    def bump(self, **deltas: int) -> None:
        with self._lock:
            for k, v in deltas.items():
                setattr(self, k, getattr(self, k) + v)
            self.inflight_peak = max(self.inflight_peak, self.inflight)
            self.waiting_peak = max(self.waiting_peak, self.waiting)

    def reject(self, why: str) -> None:
        with self._lock:
            self.rejected[why] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"inflight": self.inflight, "waiting": self.waiting, "inflight_peak": self.inflight_peak,
                    "waiting_peak": self.waiting_peak, "rejected": dict(self.rejected), "served": self.served}


stats = CapacityStats()


class RequestContextMiddleware:
    GATED = ("POST", "/chat")

    def __init__(self, app, max_body: int | None = None, max_inflight: int | None = None, max_queue: int | None = None,
                 queue_wait_s: float | None = None, retry_after_s: int | None = None, body_timeout_s: float | None = None):
        self.app = app
        cfg = limits()
        self.max_body = cfg["max_request_bytes"] if max_body is None else max_body
        self.max_inflight = cfg["max_concurrent_chats"] if max_inflight is None else max_inflight
        self.max_queue = cfg["chat_queue_max"] if max_queue is None else max_queue
        self.queue_wait_s = cfg["chat_queue_wait_seconds"] if queue_wait_s is None else queue_wait_s
        self.retry_after_s = cfg["retry_after_seconds"] if retry_after_s is None else retry_after_s
        self.body_timeout_s = cfg["request_body_timeout_seconds"] if body_timeout_s is None else body_timeout_s
        # A semaphore belongs to the event loop that waits on it; in production there is one loop, under test several.
        self._sems: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()

    def _semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        sem = self._sems.get(loop)
        if sem is None:
            sem = self._sems[loop] = asyncio.Semaphore(self.max_inflight)
        return sem

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        trace_id, span_id = observability.new_trace_id(), observability.new_span_id()
        ids = [(b"x-request-id", trace_id.encode()), (b"traceparent", observability.format_traceparent(trace_id, span_id).encode())]
        started = False

        async def send_with_ids(message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message = {**message, "headers": [*(h for h in message.get("headers", []) if h[0].lower() not in (b"x-request-id", b"traceparent")), *ids]}
            await send(message)

        async def refuse(status: int, detail: str, *extra: tuple[bytes, bytes]) -> None:
            body = json.dumps({"detail": detail, "request_id": trace_id}).encode()
            await send_with_ids({"type": "http.response.start", "status": status,
                                 "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *extra]})
            await send_with_ids({"type": "http.response.body", "body": body})

        token = current_trace_id.set(trace_id)
        ctx_token = observability.current_request.set({"span_id": span_id, **observability.request_context(headers)})
        try:
            declared = headers.get("content-length", "")
            if declared.isdigit() and int(declared) > self.max_body:
                stats.reject("too_large")
                await refuse(413, "request body too large")
                return
            body = await self._read_body(receive)
            if body is None:
                stats.reject("too_large")
                await refuse(413, "request body too large")
                return
            if body is TIMED_OUT:
                stats.reject("slow_body")
                await refuse(408, "request body not received in time")
                return
            sent_body = False

            async def replay():
                """The buffered body once, then the real channel, so a disconnect is still seen."""
                nonlocal sent_body
                if not sent_body:
                    sent_body = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            gated = (scope["method"], scope["path"]) == self.GATED
            if gated and not await self._admit():
                stats.reject("busy")
                await refuse(503, "the service is busy, try again shortly", (b"retry-after", str(self.retry_after_s).encode()))
                return
            try:
                await self.app(scope, replay, send_with_ids)
            finally:
                if gated:
                    self._semaphore().release()
                    stats.bump(inflight=-1)
        except Exception as exc:  # noqa: BLE001 - last resort: nothing of the exception reaches the client
            logger.error("request failed (%s) %s %s", type(exc).__name__, scope["method"], scope["path"],
                         extra={"fields": {"error_type": type(exc).__name__}})
            if not started:
                await refuse(500, "internal error")
        finally:
            observability.current_request.reset(ctx_token)
            current_trace_id.reset(token)

    async def _read_body(self, receive) -> bytes | None:
        """The whole request body, or None if it goes over the limit (counted as it arrives, so a body that lies about or
        omits its Content-Length is caught too), or TIMED_OUT if the client stops sending. The limit is small, so buffering
        it costs little, and it lets the refusal be a clean 413 instead of an error from deep inside the route."""
        chunks, size = [], 0
        deadline = asyncio.get_running_loop().time() + self.body_timeout_s  # for the whole body: trickling bytes does not extend it
        while True:
            try:
                message = await asyncio.wait_for(receive(), max(0.0, deadline - asyncio.get_running_loop().time()))
            except asyncio.TimeoutError:
                return TIMED_OUT
            if message["type"] != "http.request":
                return b""  # the client left; the route will see the disconnect
            chunks.append(message.get("body", b""))
            size += len(chunks[-1])
            if size > self.max_body:
                return None
            if not message.get("more_body", False):
                return b"".join(chunks)

    async def _admit(self) -> bool:
        """A slot for this chat, or False if the queue is full or the wait ran out. The slot is released by the caller."""
        sem = self._semaphore()
        if not sem.locked():
            await sem.acquire()
            stats.bump(inflight=1, served=1)
            return True
        if stats.waiting >= self.max_queue:
            return False
        stats.bump(waiting=1)
        try:
            await asyncio.wait_for(sem.acquire(), self.queue_wait_s)
        except asyncio.TimeoutError:
            return False
        finally:
            stats.bump(waiting=-1)
        stats.bump(inflight=1, served=1)
        return True
