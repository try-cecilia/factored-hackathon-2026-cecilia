"""Throughput of everything except the LLM, on the real warehouse.

Runs the full orchestrator (session, policy, classifier guard, tools on the
4.4M-row warehouse, grounding, escalation, tracing) with the scripted model
from eval/, across N threads, and reports turns/second and latency
percentiles. The LLM provider's own rate limit and latency are NOT included
— they dominate in production and are covered by `make eval-live`.

    python -m ops.loadtest --threads 8 --turns 400
"""
from __future__ import annotations

import argparse
import os
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

from agent.core.orchestrator import Orchestrator
from agent.session.auth import SessionStore
from eval.run_system_eval import ScriptedLLM
from eval.workload import load


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--turns", type=int, default=400)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp()
    os.environ.update({"HUMAN_QUEUE_PATH": f"{tmp}/q.jsonl", "AUDIT_LOG_PATH": f"{tmp}/a.jsonl", "TRACE_LOG_PATH": f"{tmp}/t.jsonl"})
    from pathlib import Path

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
    print(f"threads={a.threads} turns={len(lat)} throughput={len(lat) / wall:.1f} turns/s "
          f"p50={q(0.5):.1f}ms p95={q(0.95):.1f}ms p99={q(0.99):.1f}ms mean={statistics.mean(lat):.1f}ms (LLM excluded)")


if __name__ == "__main__":
    main()
