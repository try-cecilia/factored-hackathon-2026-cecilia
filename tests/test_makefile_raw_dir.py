"""`make pipeline` reads the raw files from one folder, RAW_DATA_DIR: the load and the lineage check must agree on it."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="needs make")


def _make(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["make", *args, f"PY={sys.executable}"], cwd=ROOT, capture_output=True, text=True, env={**os.environ, **(env or {})})


def test_the_whole_chain_points_at_the_same_raw_folder():
    dry = _make("-n", "pipeline", "INGEST=ingest-local", "RAW_DATA_DIR=/somewhere/else/raw")
    assert dry.returncode == 0, dry.stderr
    commands = {line.split(" -m ")[1].split()[0]: line for line in dry.stdout.splitlines() if " -m data." in line}
    assert "--raw-dir /somewhere/else/raw" in commands["data.pipeline"]
    assert "--raw-dir /somewhere/else/raw" in commands["data.lineage"]
    assert "data/raw" not in commands["data.lineage"]


def test_without_a_raw_folder_both_steps_use_data_raw():
    dry = _make("-n", "pipeline", "INGEST=ingest-local")
    commands = {line.split(" -m ")[1].split()[0]: line for line in dry.stdout.splitlines() if " -m data." in line}
    assert "--raw-dir data/raw" in commands["data.pipeline"] and "--raw-dir data/raw" in commands["data.lineage"]


def test_a_load_from_a_folder_outside_the_repo_passes_its_lineage_check(tmp_path):
    raw = tmp_path / "elsewhere" / "raw"
    shutil.copytree(FIXTURES / "raw", raw)
    env = {"DUCKDB_PATH": str(tmp_path / "w.duckdb"), "RAW_DATA_DIR": str(raw), "QUALITY_REPORT": str(tmp_path / "quality.json")}
    done = _make("ingest-local", "lineage", env=env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "lineage holds" in done.stdout
    (raw / "customers.csv").write_text("customer_id\nx\n")  # a file changed after the load is still caught, there
    broken = _make("lineage", env=env)
    assert broken.returncode != 0 and "customers.csv" in broken.stdout + broken.stderr
