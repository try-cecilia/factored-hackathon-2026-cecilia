"""Throughput of everything except the LLM, on the real warehouse.

Runs the full orchestrator (session, policy, classifier guard, tools on the
4.4M-row warehouse, rendering, escalation, tracing) with the scripted model
from eval/, across N threads, and reports turns/second and latency
percentiles. The LLM provider's own rate limit and latency are NOT included
— they dominate in production and are covered by `make eval-live`.

    python -m ops.loadtest --threads 8 --turns 400            # make loadtest (needs the real warehouse)
    python -m ops.loadtest --fixture --threads 8 --turns 400  # the same on the hand-made fixture warehouse
    python -m ops.loadtest --http                             # make loadtest-http: overload of the HTTP surface

`--http` boots the real API (uvicorn, on a free local port) on the fixture warehouse with a model that answers after
`--llm-ms` (default 1800, the measured p50 of Claude Sonnet 5 in eval/reports/SYSTEM_EVAL_LIVE.md), and drives it
with closed-loop clients at growing concurrency. It reports, per level, what was served, what the limits refused
(429 rate limit, 503 saturated, both with Retry-After) and the latency of each. The model is simulated: it measures the
limits and the behaviour under overload, not the provider.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import socket
import statistics
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


FIXTURE_CUSTOMERS = ("CLI-FIX0001", "CLI-FIX0004")  # active customers of tests/fixtures/raw with products


def build_fixture(tmp: str) -> None:
    """The fixture warehouse (tests/fixtures/raw) in `tmp`: what a machine without the organizer's data can run."""
    os.environ["DUCKDB_PATH"] = f"{tmp}/fixture.duckdb"
    from data.pipeline import RunConfig, run_pipeline

    run_pipeline(["branches", "daily_exchange_rates", "customers", "products", "transactions"],
                 RunConfig(source="local", raw_dir=Path("tests/fixtures/raw")))
    from agent.tools import db

    db.close_all()


def isolate(tmp: str) -> None:
    os.environ.update({"HUMAN_QUEUE_PATH": f"{tmp}/q.jsonl", "AUDIT_LOG_PATH": f"{tmp}/a.jsonl", "TRACE_LOG_PATH": f"{tmp}/t.jsonl",
                       "TRACE_REQUESTS_PATH": f"{tmp}/r.jsonl"})


def run_direct(a) -> None:
    from agent.core.orchestrator import Orchestrator
    from agent.session.auth import SessionStore

    tmp = tempfile.mkdtemp()
    isolate(tmp)
    if a.fixture:
        from eval.fake_llm import FakeLLMClient, tool_call_response

        build_fixture(tmp)
        jobs = [FIXTURE_CUSTOMERS[i % len(FIXTURE_CUSTOMERS)] for i in range(a.turns)]

        def one(customer):
            store = SessionStore()
            tok = store.issue(customer, {"segment": "Premium", "country": "Mexico", "customer_status": "Active"}).token
            llm = FakeLLMClient([tool_call_response("get_account_summary", {})])
            t0 = time.perf_counter()
            Orchestrator(store, llm=lambda: llm).handle_message(tok, "cual es mi saldo")
            return (time.perf_counter() - t0) * 1000
    else:
        from eval.run_system_eval import ScriptedLLM
        from eval.workload import load

        cases = [c for c in load(Path("eval/workload/cases_test.jsonl")) if c.fault is None and len(c.turns) == 1]
        jobs = [cases[i % len(cases)] for i in range(a.turns)]

        def one(case):
            store = SessionStore()
            tok = store.issue(case.customer_id, {"segment": case.segment, "country": case.country, "customer_status": case.customer_status}).token
            llm = ScriptedLLM(case)
            t0 = time.perf_counter()
            Orchestrator(store, llm=lambda: llm).handle_message(tok, case.turns[0])
            return (time.perf_counter() - t0) * 1000

    one(jobs[0])  # warm caches/connections
    t0 = time.perf_counter()
    with ThreadPoolExecutor(a.threads) as ex:
        lat = sorted(ex.map(one, jobs))
    wall = time.perf_counter() - t0
    q = lambda p: lat[min(len(lat) - 1, int(p * (len(lat) - 1)))]  # noqa: E731
    print(f"{'fixture' if a.fixture else 'warehouse'} threads={a.threads} turns={len(lat)} throughput={len(lat) / wall:.1f} turns/s "
          f"p50={q(0.5):.1f}ms p95={q(0.95):.1f}ms p99={q(0.99):.1f}ms mean={statistics.mean(lat):.1f}ms (LLM excluded)")


# --- the HTTP surface under overload ----------------------------------------------------------------------------------

def serve_in_thread(app) -> tuple[str, "object"]:
    import uvicorn

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", timeout_keep_alive=5))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", server


def percentile(values: list[float], p: float) -> float | None:
    values = sorted(values)
    return round(values[min(len(values) - 1, int(p * (len(values) - 1)))], 1) if values else None


async def drive(base: str, clients: int, requests: int, sessions: list[str], honor_retry_after: bool = True) -> dict:
    """Closed loop: each client sends its next message as soon as the last answer arrives, until `requests` are sent.
    A well-behaved client waits out `Retry-After` after a 429 or 503; `honor_retry_after=False` is a client that hammers."""
    import httpx

    left = [requests]
    results: list[tuple[int, float, bool]] = []
    async with httpx.AsyncClient(base_url=base, timeout=60, limits=httpx.Limits(max_connections=clients + 5)) as c:
        async def client(i: int) -> None:
            # A ramp of 5 ms per client: 128+ connections opened in the same instant overflow the OS accept queue
            # (128 on macOS, `kern.ipc.somaxconn`), and the dropped SYNs read as multi-second stalls that are not the service's.
            await asyncio.sleep(i * 0.005)
            tok = sessions[i % len(sessions)]
            while left[0] > 0:
                left[0] -= 1
                t0 = time.perf_counter()
                r = await c.post("/chat", json={"session_token": tok, "message": "cual es mi saldo"})
                results.append((r.status_code, (time.perf_counter() - t0) * 1000, "retry-after" in r.headers))
                if honor_retry_after and r.status_code in (429, 503):
                    await asyncio.sleep(min(float(r.headers.get("retry-after", 1)), 10))

        t0 = time.perf_counter()
        await asyncio.gather(*(client(i) for i in range(clients)))
        wall = time.perf_counter() - t0
    by = lambda code: [ms for c_, ms, _ in results if c_ == code]  # noqa: E731
    refused = [(c_, ra) for c_, _, ra in results if c_ in (429, 503)]
    return {"clients": clients, "sent": len(results), "ok": len(by(200)), "rate_limited_429": len(by(429)), "busy_503": len(by(503)),
            "other": len([1 for c_, _, _ in results if c_ not in (200, 429, 503)]), "served_per_s": round(len(by(200)) / wall, 1),
            "ok_p50_ms": percentile(by(200), 0.5), "ok_p95_ms": percentile(by(200), 0.95),
            "refused_p95_ms": percentile(by(503) + by(429), 0.95), "refusals_with_retry_after": f"{sum(ra for _, ra in refused)}/{len(refused)}"}


def table(rows: list[dict]) -> str:
    cols = list(rows[0])
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols),
                      *("| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows)])


def run_http(a) -> None:
    import httpx

    tmp = tempfile.mkdtemp()
    isolate(tmp)
    build_fixture(tmp)
    os.environ.update({"LOG_LEVEL": "WARNING", "DEMO_IDP_SECRET": "loadtest", "ADMIN_API_KEY": "loadtest", "LOGIN_RATE_PER_MIN": "1000000",
                       "CHAT_RATE_PER_MIN": "1000000", "CHAT_CUSTOMER_RATE_PER_MIN": "1000000", "CHAT_IP_RATE_PER_MIN": "1000000",
                       "LLM_DAILY_BUDGET_USD": "0", "LLM_SESSION_BUDGET_USD": "0", "STATE_DB_PATH": f"{tmp}/state.db"})
    for k in ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY"):
        os.environ[k] = ""
    from agent.session.identity import derive_test_pin
    from eval.fake_llm import tool_call_response
    from agent.llm.client import LLMUnavailable
    from api import main

    class SimulatedModel:
        """Answers a balance question after `llm_ms`, or is down (raises at once) when `down`."""

        down = False

        def chat(self, messages, tools=None, temperature=0.0):
            if self.down:
                raise LLMUnavailable("simulated outage", [{"provider": "sim", "outcome": "error", "kind": "transient"}])
            time.sleep(a.llm_ms / 1000)
            return tool_call_response("get_account_summary", {})

    model = SimulatedModel()
    main.default_orchestrator._llm = lambda: model
    base, server = serve_in_thread(main.app)
    sessions = []
    with httpx.Client(base_url=base) as c:
        for i in range(max(a.levels)):
            cid = FIXTURE_CUSTOMERS[i % len(FIXTURE_CUSTOMERS)]
            sessions.append(c.post("/auth/session", json={"customer_id": cid, "pin": derive_test_pin(cid)}).json()["token"])
        limits = c.get("/admin/capacity", headers={"X-Admin-Key": "loadtest"}).json()["limits"]

    out = [f"# Load test of the HTTP surface (fixture warehouse, model simulated at {a.llm_ms:.0f} ms)\n",
           f"Limits in force: max_concurrent_chats={limits['max_concurrent_chats']} chat_queue_max={limits['chat_queue_max']} "
           f"chat_queue_wait_seconds={limits['chat_queue_wait_seconds']} retry_after_seconds={limits['retry_after_seconds']}; "
           f"rate limits raised out of the way for this run. Clients "
           f"{'ignore Retry-After and resend at once' if a.ignore_retry_after else 'wait out Retry-After'}.\n"]
    for title, down in (("Model answering", False), ("Model down (every turn falls back to a handoff)", True)):
        model.down = down
        rows = []
        for n in a.levels:
            Path(os.environ["HUMAN_QUEUE_PATH"]).write_text("")  # the queue is read linearly: keep each level's tickets its own
            asyncio.run(drive(base, min(n, 4), 8, sessions))  # warm the connections and the warehouse
            rows.append(asyncio.run(drive(base, n, max(a.requests, n * 3), sessions, not a.ignore_retry_after)))
        out.append(f"## {title}\n\n{table(rows)}\n")
    state = httpx.get(f"{base}/admin/capacity", headers={"X-Admin-Key": "loadtest"}).json()["state"]
    out.append(f"Server counters at the end: {state}\n")
    # Rate limits on their real defaults: one session sending as fast as it can.
    main.chat_limiter = main.RateLimiter(20, 60)
    model.down = False
    with httpx.Client(base_url=base) as c:
        codes = [c.post("/chat", json={"session_token": sessions[0], "message": "cual es mi saldo"}) for _ in range(30)]
    limited = [r for r in codes if r.status_code == 429]
    out.append(f"## Per-session rate limit (default 20/min)\n\n30 back-to-back messages from one session: "
               f"{sum(r.status_code == 200 for r in codes)} answered, {len(limited)} refused with 429; "
               f"Retry-After on the first refusal: {limited[0].headers.get('retry-after') if limited else 'n/a'} s.\n")
    server.should_exit = True
    text = "\n".join(out)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--turns", type=int, default=400)
    ap.add_argument("--fixture", action="store_true", help="use the fixture warehouse instead of the real one")
    ap.add_argument("--http", action="store_true", help="drive the real HTTP surface into overload (implies the fixture)")
    ap.add_argument("--llm-ms", type=float, default=1800.0, help="simulated model latency for --http")
    ap.add_argument("--levels", type=int, nargs="+", default=[8, 32, 64, 128, 256], help="concurrent clients for --http")
    ap.add_argument("--requests", type=int, default=200, help="requests per level for --http (at least 3 per client)")
    ap.add_argument("--ignore-retry-after", action="store_true", help="--http clients that resend at once after a 429/503")
    ap.add_argument("--out", help="also write the --http report here")
    a = ap.parse_args()
    (run_http if a.http else run_direct)(a)


if __name__ == "__main__":
    main()
