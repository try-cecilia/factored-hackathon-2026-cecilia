"""Lineage queries: from a row the agent serves back to the bytes it was loaded from.

Every served row carries `_run_id`, `_source_file` and `_ingested_at` (written by data/pipeline.py). The run's
`_ingestion_log` row says which contract and code version loaded it and with what parameters; `_source_files` says
which files that load read, how big, and their SHA-256. Three questions this module answers:

- `trace(con)`: per table, the last good load and its files with hashes.
- `trace_row(con, table, key)`: the load and the file behind one row.
- `verify(con, raw_dir)`: does the chain hold? Every served row has lineage, every run it names is a successful load
  of that table, every file it names was recorded with a hash, and (with `raw_dir`) the files on disk still have it.

    python -m data.lineage                                  # per-table summary
    python -m data.lineage --row transactions TXN-0001      # one row
    python -m data.lineage --verify --raw-dir data/raw      # exit 1 if the chain is broken
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from data.contracts import PRIMARY_KEYS
from data.pipeline import TABLES, _LAST_LOADS, file_sha256, get_connection

SERVING = tuple(t.name for t in TABLES if t.profile == "serving")
SHA256 = re.compile(r"[0-9a-f]{64}")
LOAD_COLUMNS = ("run_id", "mode", "contract_version", "code_version", "params", "started_at", "finished_at")


def _present(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}


def manifest_sha256(files: list[dict]) -> str:
    """One hash for a load's input: the files' names and hashes, in name order."""
    digest = hashlib.sha256()
    for f in sorted(files, key=lambda f: f["source_file"]):
        digest.update(f"{f['source_file']}\0{f['sha256']}\n".encode())
    return digest.hexdigest()


def _files(con, run_id: str, table: str) -> list[dict]:
    cur = con.execute("SELECT source_file, source_uri, n_bytes, sha256, partition_date FROM _source_files "
                      "WHERE run_id = ? AND table_name = ? ORDER BY source_file", [run_id, table])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _load(con, run_id: str, table: str) -> dict | None:
    cur = con.execute(f"SELECT {', '.join(LOAD_COLUMNS)} FROM _ingestion_log "
                      "WHERE run_id = ? AND table_name = ? AND status = 'success'", [run_id, table])
    row = cur.fetchone()
    return None if row is None else {**dict(zip(LOAD_COLUMNS, row)), "params": json.loads(row[4] or "{}")}


def trace(con, tables: tuple[str, ...] | None = None) -> dict[str, dict]:
    """Per table: rows served, the runs those rows come from, and the last good load with its files."""
    present = _present(con)
    out = {}
    for name in tables or [t.name for t in TABLES if t.name in present]:
        if name not in present:
            continue
        runs = [r[0] for r in con.execute(f"SELECT DISTINCT _run_id FROM {name} ORDER BY 1").fetchall()]
        last = con.execute(f"SELECT run_id FROM ({_LAST_LOADS}) WHERE table_name = ?", [name]).fetchone()
        files = _files(con, last[0], name) if last else []
        out[name] = {"rows": con.execute(f"SELECT count(*) FROM {name}").fetchone()[0], "runs_in_rows": runs,
                     "last_load": _load(con, last[0], name) if last else None,
                     "files": files, "manifest_sha256": manifest_sha256(files) if files else None}
    return out


def trace_row(con, table: str, key: str | list[str]) -> dict | None:
    """The load and the source file behind one served row, found by its primary key."""
    pk = PRIMARY_KEYS[table]
    key = [key] if isinstance(key, str) else list(key)
    if len(key) != len(pk):
        raise ValueError(f"{table} has the key {pk}: {len(pk)} value(s) needed, got {len(key)}")
    row = con.execute(f"SELECT _run_id, _source_file, _ingested_at FROM {table} WHERE "
                      + " AND ".join(f'CAST("{c}" AS VARCHAR) = ?' for c in pk), key).fetchone()
    if row is None:
        return None
    run_id, source_file, ingested_at = row
    file = next((f for f in _files(con, run_id, table) if f["source_file"] == source_file), None)
    return {"table": table, "key": dict(zip(pk, key)), "run_id": run_id, "ingested_at": str(ingested_at),
            "source_file": source_file, "source_sha256": file["sha256"] if file else None,
            "source_uri": file["source_uri"] if file else None, "load": _load(con, run_id, table)}


def _incomplete_load(load: dict) -> list[str]:
    """What a load's row must say for it to explain the rows it produced: the contract and the code that ran, and when."""
    empty = lambda v: v is None or not str(v).strip()  # noqa: E731
    return [c for c in ("mode", "contract_version", "code_version", "started_at", "finished_at") if empty(load.get(c))]


def _incomplete_file(file: dict) -> list[str]:
    """What a recorded source file must say: where it was, how big, and a well-formed SHA-256 of its bytes."""
    bad = [c for c in ("source_uri",) if file.get(c) is None or not str(file[c]).strip()]
    if file.get("n_bytes") is None or file["n_bytes"] < 0:
        bad.append("n_bytes")
    if not SHA256.fullmatch(str(file.get("sha256") or "")):
        bad.append("sha256")
    return bad


def verify(con, raw_dir: Path | None = None, tables: tuple[str, ...] = SERVING) -> list[str]:
    """Every way the chain from served rows to source bytes is broken; an empty list means it holds."""
    problems, present = [], _present(con)
    for name in tables:
        if name not in present:
            problems.append(f"{name}: the table is not in the warehouse")
            continue
        if "_source_file" not in {r[0] for r in con.execute(f"DESCRIBE {name}").fetchall()}:
            problems.append(f"{name}: rows carry no lineage columns")
            continue
        missing = con.execute(f"SELECT count(*) FROM {name} WHERE _run_id IS NULL OR _source_file IS NULL "
                              "OR _ingested_at IS NULL").fetchone()[0]
        if missing:
            problems.append(f"{name}: {missing} row(s) without _run_id, _source_file or _ingested_at")
        for run_id, source_file in con.execute(f"SELECT DISTINCT _run_id, _source_file FROM {name} "
                                               "WHERE _run_id IS NOT NULL AND _source_file IS NOT NULL").fetchall():
            load = _load(con, run_id, name)
            if load is None:
                problems.append(f"{name}: rows name run {run_id}, which is not a successful load of the table")
                continue
            if incomplete := _incomplete_load(load):
                problems.append(f"{name}: run {run_id} does not record {', '.join(incomplete)}")
            file = next((f for f in _files(con, run_id, name) if f["source_file"] == source_file), None)
            if file is None:
                problems.append(f"{name}: rows name {source_file} in run {run_id}, but no file with a hash was recorded")
                continue
            if incomplete := _incomplete_file(file):
                problems.append(f"{name}: {source_file} in run {run_id} has a missing or malformed {', '.join(incomplete)}")
            elif raw_dir is not None:
                path = Path(raw_dir).resolve() / source_file
                if not path.exists():
                    problems.append(f"{name}: {source_file} is no longer under {raw_dir}")
                elif file_sha256(path) != file["sha256"]:
                    problems.append(f"{name}: {source_file} has other bytes than the ones loaded in run {run_id}")
    return problems


def main() -> None:
    p = argparse.ArgumentParser(description="Trace served rows back to their source files")
    p.add_argument("--table", help="limit the summary to one table")
    p.add_argument("--row", nargs="+", metavar=("TABLE", "KEY"), help="trace one row: the table, then its primary key value(s)")
    p.add_argument("--verify", action="store_true", help="check the whole chain and exit 1 if it is broken")
    p.add_argument("--raw-dir", help="with --verify, also re-hash the files in this directory")
    a = p.parse_args()
    con = get_connection(read_only=True)
    try:
        if a.row:
            result = trace_row(con, a.row[0], a.row[1:])
        elif a.verify:
            problems = verify(con, Path(a.raw_dir) if a.raw_dir else None)
            print("\n".join(problems) or "lineage holds")
            sys.exit(1 if problems else 0)
        else:
            result = trace(con, (a.table,) if a.table else None)
        print(json.dumps(result, indent=2, default=str))
    finally:
        con.close()


if __name__ == "__main__":
    main()
