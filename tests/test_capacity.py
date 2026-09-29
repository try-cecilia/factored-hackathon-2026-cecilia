"""Capacity limits: request size, concurrency with a queue, rate limits with Retry-After, cost budgets, prompt size."""
from __future__ import annotations

import asyncio
import math
import time

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from agent.core import orchestrator as orch_mod
from agent.core.orchestrator import fit_prompt
from agent.llm import prompts
from agent.session import identity
from agent.session.identity import derive_test_pin
from api import main, middleware


@pytest.fixture
def client(monkeypatch):
    identity.default_identity._failures.clear()
    for name in ("login_limiter", "chat_limiter", "chat_customer_limiter", "chat_ip_limiter"):
        monkeypatch.setattr(main, name, main.RateLimiter(100, 60))
    return TestClient(main.app)


def token(client, cid="CLI-FIX0001") -> str:
    return client.post("/auth/session", json={"customer_id": cid, "pin": derive_test_pin(cid)}).json()["token"]


def say(client, tok, text="hola"):
    return client.post("/chat", json={"session_token": tok, "message": text})


# --- size ---------------------------------------------------------------------------------------------------------

def test_a_message_over_1000_characters_is_refused_before_any_work(client):
    assert say(client, token(client), "x" * 1001).status_code == 422
    assert say(client, token(client), "x" * 1000).status_code == 200


def test_a_body_over_the_limit_is_refused_by_its_declared_size_without_reading_it(client):
    r = client.post("/chat", content=b"{" + b" " * 20_000, headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["detail"] == "request body too large" and r.headers["X-Request-ID"]


def test_a_body_that_does_not_declare_its_size_is_counted_as_it_arrives():
    async def run():
        async def chunks():
            for _ in range(40):
                yield b" " * 1024  # 40 KiB in chunks, no Content-Length

        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.post("/chat", content=chunks(), headers={"content-type": "application/json"})

    r = asyncio.run(run())
    assert r.status_code == 413


def test_a_client_that_trickles_its_body_is_cut_off_with_408():
    async def run():
        app = FastAPI()

        @app.post("/chat")
        async def chat():
            return {"ok": True}

        mw = middleware.RequestContextMiddleware(app, body_timeout_s=0.2)
        sent = []

        async def receive():
            await asyncio.sleep(0.15)  # a byte every 0.15 s: each chunk is in time, the whole body never is
            return {"type": "http.request", "body": b" ", "more_body": True}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "method": "POST", "path": "/chat", "headers": [], "query_string": b""}
        await mw(scope, receive, send)
        return sent[0]["status"]

    assert asyncio.run(run()) == 408


def test_refused_sizes_are_counted_for_the_operator(client):
    before = middleware.stats.snapshot()["rejected"]["too_large"]
    client.post("/chat", content=b" " * 20_000, headers={"content-type": "application/json"})
    assert middleware.stats.snapshot()["rejected"]["too_large"] == before + 1


# --- concurrency: 503 + Retry-After ---------------------------------------------------------------------------------

def slow_app(service_s: float, **limits) -> httpx.AsyncClient:
    app = FastAPI()

    @app.post("/chat")
    async def chat(request: Request):
        await asyncio.sleep(service_s)
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    app.add_middleware(middleware.RequestContextMiddleware, **limits)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def burst(n: int, service_s: float, **limits) -> list[httpx.Response]:
    async def run():
        async with slow_app(service_s, **limits) as c:
            return await asyncio.gather(*(c.post("/chat", json={}) for _ in range(n)))

    return asyncio.run(run())


def test_past_the_slots_and_the_queue_the_service_answers_503_with_retry_after_at_once():
    t0 = time.perf_counter()
    rs = burst(6, 0.3, max_inflight=2, max_queue=1, queue_wait_s=2.0, retry_after_s=7)
    codes = sorted(r.status_code for r in rs)
    assert codes == [200, 200, 200, 503, 503, 503]  # 2 running + 1 queued get served; the rest are turned away
    busy = [r for r in rs if r.status_code == 503]
    assert all(r.headers["Retry-After"] == "7" and r.headers["X-Request-ID"] for r in busy)
    assert busy[0].json()["detail"] == "the service is busy, try again shortly"
    assert time.perf_counter() - t0 < 1.5  # served in two waves of 0.3 s: the refusals did not wait for anyone


def test_a_request_that_waits_longer_than_the_queue_wait_is_turned_away_not_kept():
    rs = burst(3, 0.5, max_inflight=1, max_queue=5, queue_wait_s=0.1)
    assert sorted(r.status_code for r in rs) == [200, 503, 503]


def test_the_queue_serves_in_arrival_order_within_its_wait():
    rs = burst(4, 0.1, max_inflight=1, max_queue=5, queue_wait_s=5.0)
    assert [r.status_code for r in rs] == [200] * 4


def test_only_chat_is_gated_and_slots_are_returned_when_a_request_ends():
    async def run():
        async with slow_app(0.3, max_inflight=1, max_queue=0) as c:
            first = asyncio.create_task(c.post("/chat", json={}))
            await asyncio.sleep(0.05)
            health = await c.get("/health")  # not the expensive route: never refused
            refused = await c.post("/chat", json={})
            await first
            after = await c.post("/chat", json={})
            return health.status_code, refused.status_code, after.status_code

    assert asyncio.run(run()) == (200, 503, 200)


def test_a_slot_is_released_even_when_the_route_fails():
    app = FastAPI()

    @app.post("/chat")
    async def chat():
        raise RuntimeError("boom")

    app.add_middleware(middleware.RequestContextMiddleware, max_inflight=1, max_queue=0)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t") as c:
            return [(await c.post("/chat", json={})).status_code for _ in range(3)]

    assert asyncio.run(run()) == [500, 500, 500]  # never 503: each failure gave its slot back


def test_the_default_gate_stays_under_the_servers_thread_pool():
    cfg = middleware.limits()
    assert cfg["max_concurrent_chats"] < 40  # anyio's default limiter: the pool never queues behind the gate unseen
    assert cfg["chat_queue_wait_seconds"] < 30 and cfg["retry_after_seconds"] >= 1


# --- rate limits: 429 + Retry-After ---------------------------------------------------------------------------------

def test_each_rate_limit_answers_429_with_a_retry_after_that_fits_its_window(client, monkeypatch):
    tok = token(client)
    monkeypatch.setattr(main, "chat_limiter", main.RateLimiter(2, 60))
    codes = [say(client, tok).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = say(client, tok)
    assert 1 <= int(r.headers["Retry-After"]) <= 60 and "session" in r.json()["detail"]


def test_a_customer_cannot_multiply_the_limit_by_opening_sessions(client, monkeypatch):
    monkeypatch.setattr(main, "chat_customer_limiter", main.RateLimiter(3, 60))
    tokens = [token(client) for _ in range(3)]
    codes = [say(client, tok).status_code for tok in tokens for _ in range(2)]
    assert codes.count(200) == 3 and codes.count(429) == 3  # three messages for the customer, however many sessions
    other = token(client, "CLI-FIX0004")
    assert say(client, other).status_code == 200  # another customer is unaffected


def test_one_address_has_one_limit_across_sessions_and_customers(client, monkeypatch):
    monkeypatch.setattr(main, "chat_ip_limiter", main.RateLimiter(2, 60))
    a, b = token(client, "CLI-FIX0001"), token(client, "CLI-FIX0004")
    assert [say(client, a).status_code, say(client, b).status_code, say(client, a).status_code] == [200, 200, 429]
    assert "address" in say(client, b).json()["detail"]


def test_a_login_flood_gets_retry_after_too(client, monkeypatch):
    monkeypatch.setattr(main, "login_limiter", main.RateLimiter(1, 60))
    body = {"customer_id": "CLI-FIX0004", "pin": derive_test_pin("CLI-FIX0004")}
    client.post("/auth/session", json=body)
    r = client.post("/auth/session", json=body)
    assert r.status_code == 429 and r.headers["Retry-After"].isdigit()


def test_retry_after_counts_down_to_when_the_oldest_hit_leaves_the_window(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(main.time, "time", lambda: now[0])
    lim = main.RateLimiter(2, 60)
    lim.allow("k")
    now[0] += 20
    lim.allow("k")
    assert not lim.allow("k") and lim.retry_after("k") == math.ceil(60 - 20)
    now[0] += 41
    assert lim.allow("k")  # the first hit aged out


def test_the_limiters_do_not_grow_without_bound(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(main.time, "time", lambda: now[0])
    lim = main.RateLimiter(5, 60)
    for i in range(1500):
        lim.allow(f"session-{i}")
    now[0] += 61  # every key has gone quiet
    for i in range(main.RateLimiter.SWEEP_EVERY):
        lim.allow("fresh")
    assert len(lim) == 1
    monkeypatch.setattr(main.RateLimiter, "MAX_KEYS", 10)
    for i in range(main.RateLimiter.SWEEP_EVERY * 2):
        lim.allow(f"flood-{i}")
    assert len(lim) <= 10 + main.RateLimiter.SWEEP_EVERY  # capped at each sweep: the newest keys are the ones kept


# --- what an operator can read --------------------------------------------------------------------------------------

def test_the_limits_in_force_are_readable_by_operators_only(client):
    assert client.get("/admin/capacity").status_code == 401
    body = client.get("/admin/capacity", headers={"X-Admin-Key": "test-admin-key"}).json()
    assert body["limits"]["max_request_bytes"] == 16_384 and body["limits"]["chat_per_min"]["session"] >= 1
    assert {"inflight", "waiting", "inflight_peak", "rejected", "served"} <= set(body["state"])


# --- what the model may cost ---------------------------------------------------------------------------------------

def test_the_prompt_is_bounded_whatever_the_history_holds():
    system = [{"role": "system", "content": prompts.SYSTEM_PROMPT}, {"role": "system", "content": "ctx " * 400}]
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": "y" * 3000} for i in range(orch_mod.MAX_HISTORY_MESSAGES)]
    last = {"role": "user", "content": "z" * 1000}
    fitted = fit_prompt([*system, *history, last], limit=10_000)
    assert fitted[:2] == system and fitted[-1] == last  # the fixed prompt and the customer's message are never cut
    assert sum(len(m["content"]) for m in fitted) <= 10_000 and len(fitted) < len(system) + len(history) + 1
    assert fitted[2:-1] == history[len(history) - len(fitted[2:-1]):]  # what stays is the newest history


def test_the_worst_case_prompt_of_a_real_turn_is_under_the_cap():
    worst_history = orch_mod.MAX_HISTORY_MESSAGES * 1000  # every kept message at the 1,000-character input limit
    fixed = len(prompts.SYSTEM_PROMPT) + len(prompts.context_block("2024-01-16", [
        {"product_id": f"PRD-{i:08d}", "alias": f"P{i}", "product_type": "Savings Account", "currency": "MXN",
         "product_status": "Active", "last4": "1234"} for i in range(20)]))
    assert fixed + worst_history + 1000 < orch_mod.MAX_PROMPT_CHARS  # so trimming only matters for something abnormal


def test_output_is_capped_on_every_provider_kind(monkeypatch):
    from types import SimpleNamespace

    from agent.llm.client import Provider, anthropic_call, openai_compatible_call

    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "777")
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        raise RuntimeError("stop here")

    oa = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(RuntimeError):
        openai_compatible_call(oa, Provider("g", "m", "K", None), [{"role": "user", "content": "hi"}], None, 0.0, 5)
    assert sent["max_tokens"] == 777
    sent.clear()
    an = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    with pytest.raises(RuntimeError):
        anthropic_call(an, Provider("a", "claude-sonnet-5", "K", None), [{"role": "user", "content": "hi"}], None, 0.0, 5)
    assert sent["max_tokens"] == 777
