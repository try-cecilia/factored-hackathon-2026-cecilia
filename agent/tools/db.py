"""Read-only DuckDB connections for the serving layer.

The tool layer never writes to the warehouse — ingestion (data/pipeline.py)
is the only writer. Connections are cached per thread *and per database
path*, so switching DUCKDB_PATH (tests use a fixture warehouse) never reuses
a handle to the wrong file.
"""
from __future__ import annotations

import os
import threading

import duckdb
from dotenv import load_dotenv

load_dotenv(override=False)

_local = threading.local()


def duckdb_path() -> str:
    return os.environ.get("DUCKDB_PATH", "data/warehouse/bank.duckdb")


def get_connection() -> duckdb.DuckDBPyConnection:
    cache = getattr(_local, "cons", None)
    if cache is None:
        cache = _local.cons = {}
    path = duckdb_path()
    con = cache.get(path)
    if con is None:
        con = cache[path] = duckdb.connect(path, read_only=True)
    return con


def close_all() -> None:
    for con in getattr(_local, "cons", {}).values():
        con.close()
    _local.cons = {}
