"""The API on the tests' fixture warehouse with a keyword-driven stand-in for the language model, so the web front can be
developed and demoed with no S3 access and no model key.

    python -m ops.serve_fixture [PORT]      # default 8000; state lives under data/warehouse/dev-fixture/

OFFLINE SIMULATION. Everything after the model is the real code (policy, tools, rendering, tickets, traces, sessions):
only the choice of tool is a keyword match instead of a model's judgment, like eval/fake_llm.py. It says nothing about
how a live model behaves. DEMO_MODE=1 and DEMO_CONSOLE=1 unless already set. Each start rebuilds the warehouse and the sandbox logs.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "warehouse" / "dev-fixture"
shutil.rmtree(STATE, ignore_errors=True)
STATE.mkdir(parents=True)
os.environ.update({
    "DUCKDB_PATH": str(STATE / "fixture.duckdb"), "AUDIT_LOG_PATH": str(STATE / "audit_log.jsonl"),
    "HUMAN_QUEUE_PATH": str(STATE / "human_queue.jsonl"), "TRACE_LOG_PATH": str(STATE / "traces.jsonl"),
    "TRACE_REQUESTS_PATH": str(STATE / "trace_requests.jsonl"), "HUMAN_DESK_PATH": str(STATE / "human_desk.jsonl"),
    "ANTHROPIC_API_KEY": "", "GROQ_API_KEY": "", "TOGETHER_API_KEY": "",  # nothing here may reach a real model
})
os.environ.setdefault("DEMO_IDP_SECRET", "dev-fixture-secret")
os.environ.setdefault("DEMO_MODE", "1")
os.environ.setdefault("DEMO_CONSOLE", "1")
os.environ.pop("STATE_DB_PATH", None)

from data.pipeline import RunConfig, run_pipeline  # noqa: E402

run_pipeline(["branches", "daily_exchange_rates", "customers", "products", "transactions"],
             RunConfig(source="local", raw_dir=ROOT / "tests" / "fixtures" / "raw"))

from eval.keyword_llm import KeywordModel  # noqa: E402
from ops.demo_customers import pick  # noqa: E402

os.environ.setdefault("DEMO_PUBLIC_CUSTOMERS", ",".join(pick()))

import api.main  # noqa: E402
from agent.core.orchestrator import default_orchestrator  # noqa: E402

MODEL = KeywordModel()
default_orchestrator._llm = lambda: MODEL

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(api.main.app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
