"""Hermetic test setup: a tiny warehouse built from tests/fixtures/raw with the
real pipeline (local source), so no test needs S3, credentials, or the real
700MB warehouse. Tests that do hit S3 are marked `integration` and skipped
unless RUN_INTEGRATION=1.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Some settings are read when modules are imported (rate limiters, classifier paths), before any fixture runs,
# and agent/tools/db.py loads a local .env at import without overriding what is already set. Pinning them
# here, at collection time, keeps a developer's .env from changing test outcomes.
os.environ.update({"CHAT_RATE_PER_MIN": "20", "LOGIN_RATE_PER_MIN": "10", "SESSION_TTL_SECONDS": "900"})
for _var in ("INTENT_MODEL_PATH", "INTENT_META_PATH", "DQ_REPORT_PATH"):
    os.environ.pop(_var, None)


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: needs S3 access and credentials (RUN_INTEGRATION=1)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="integration test; set RUN_INTEGRATION=1")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


SERVING = ["branches", "daily_exchange_rates", "customers", "products", "transactions"]


def build_fixture_warehouse(raw_dir: Path = FIXTURES / "raw", **cfg) -> tuple:
    """Builds into whatever DUCKDB_PATH currently points at (callers set it)."""
    from data.pipeline import RunConfig, run_pipeline

    return run_pipeline(SERVING, RunConfig(source="local", raw_dir=raw_dir, **cfg))


@pytest.fixture(scope="session", autouse=True)
def fixture_warehouse(tmp_path_factory):
    """Every test runs against the fixture warehouse unless it builds its own."""
    from agent.tools import db

    db_path = tmp_path_factory.mktemp("warehouse") / "fixture.duckdb"
    mp = pytest.MonkeyPatch()
    mp.setenv("AUDIT_LOG_PATH", str(db_path.parent / "audit_log.jsonl"))
    mp.setenv("HUMAN_QUEUE_PATH", str(db_path.parent / "human_queue.jsonl"))
    mp.setenv("TRACE_LOG_PATH", str(db_path.parent / "traces.jsonl"))
    mp.setenv("DEMO_IDP_SECRET", "test-secret")
    mp.setenv("ADMIN_API_KEY", "test-admin-key")
    mp.setenv("GROQ_API_KEY", "")
    mp.setenv("TOGETHER_API_KEY", "")
    mp.setenv("ANTHROPIC_API_KEY", "")  # hermetic: no test may reach a real model
    # agent/tools/db.py loads a local .env at import; model settings from it must not change test outcomes.
    for var in ("LLM_PROVIDERS", "LLM_MODEL", "GROQ_MODEL", "TOGETHER_MODEL", "ANTHROPIC_MODEL", "ANTHROPIC_EFFORT",
                "ANTHROPIC_FALLBACKS", "FRESHNESS_ENFORCE", "FRESHNESS_SLO_HOURS", "DEMO_PUBLIC_CUSTOMERS"):
        mp.delenv(var, raising=False)
    mp.setenv("DUCKDB_PATH", str(db_path))
    build_fixture_warehouse()
    db.close_all()
    yield db_path
    db.close_all()
    mp.undo()
