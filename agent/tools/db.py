"""Read-only DuckDB connection for the tool layer.

The tool layer never writes to the warehouse — ingestion (data/pipeline.py)
is the only writer. Opening read-only also lets the API and the pipeline run
concurrently without file-lock contention.
"""
from __future__ import annotations

import os
import threading

import duckdb
from dotenv import load_dotenv

load_dotenv(override=False)

_local = threading.local()


def _duckdb_path() -> str:
    return os.environ.get("DUCKDB_PATH", "data/warehouse/bank.duckdb")


def get_connection() -> duckdb.DuckDBPyConnection:
    """Thread-local read-only connection, opened lazily."""
    con = getattr(_local, "con", None)
    if con is None:
        con = duckdb.connect(_duckdb_path(), read_only=True)
        _local.con = con
    return con
