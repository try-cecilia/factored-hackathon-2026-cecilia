"""Silver and gold as Parquet files with a manifest: an open, portable copy that can be checked byte by byte.

    python -m data.lake                       # write data/lake/{silver,gold}/<table>.parquet and data/lake/manifest.json
    python -m data.lake --verify              # re-hash the files and re-read them; exit 1 if anything differs from the manifest

The DuckDB warehouse stays the source of truth. This is how its tables leave it: one zstd Parquet file per table, and a
manifest that names, for every file, its rows, size, SHA-256 and columns with their types, plus the silver load
(`_ingestion_log` run ids) and gold build (`_gold_log` run ids) it was written from. `--verify` needs no warehouse: it hashes
each file and reads its row count and schema back, so a copy that was edited, truncated or swapped fails. Pointing
`--db` at the warehouse also compares the row counts with the tables.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from data.gold import MARTS
from data.pipeline import TABLES, _git_sha

MANIFEST = "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _columns(con, source: str) -> list[dict]:
    return [{"name": r[0], "type": r[1]} for r in con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()]


def _latest_runs(con, log: str) -> dict:
    """The newest successful run of each table (silver) or mart (gold), from its log table; empty when there is no log."""
    present = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()}
    if log not in present:
        return {}
    if log == "_ingestion_log":
        q = "SELECT table_name, run_id FROM _ingestion_log WHERE status = 'success' QUALIFY row_number() OVER (PARTITION BY table_name ORDER BY finished_at DESC) = 1"
    else:
        q = "SELECT mart, gold_run_id FROM _gold_log WHERE status = 'built' QUALIFY row_number() OVER (PARTITION BY mart ORDER BY finished_at DESC) = 1"
    return dict(con.execute(q).fetchall())


def export(con, out: Path) -> dict:
    """Write every silver table and gold mart the warehouse has. The manifest is written last, so a half-written export has none."""
    present = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()}
    layers = [("silver", [t.name for t in TABLES]), ("gold", [m.name for m in MARTS])]
    files = []
    for layer, names in layers:
        for name in (n for n in names if n in present):
            target = out / layer / f"{name}.parquet"
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".parquet.tmp")
            con.execute(f"COPY (SELECT * FROM {name}) TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
            os.replace(tmp, target)
            files.append({"layer": layer, "table": name, "path": f"{layer}/{name}.parquet", "rows": con.execute(f"SELECT count(*) FROM {name}").fetchone()[0],
                          "bytes": target.stat().st_size, "sha256": _sha256(target), "columns": _columns(con, name)})
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "code_version": _git_sha(),
                "silver_runs": _latest_runs(con, "_ingestion_log"), "gold_runs": _latest_runs(con, "_gold_log"), "files": files}
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return manifest


def verify(out: Path, con=None) -> list[str]:
    """Check the files against the manifest; with the warehouse connection, also each table's row count."""
    try:
        manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{out / MANIFEST} does not exist"]
    problems = []
    reader = duckdb.connect(":memory:")
    try:
        for f in manifest["files"]:
            path = out / f["path"]
            if not path.exists():
                problems.append(f"{f['path']}: the file is missing")
                continue
            if _sha256(path) != f["sha256"]:
                problems.append(f"{f['path']}: the SHA-256 differs from the manifest")
                continue
            uri = path.as_posix()
            rows = reader.execute(f"SELECT count(*) FROM read_parquet('{uri}')").fetchone()[0]
            if rows != f["rows"]:
                problems.append(f"{f['path']}: {rows} rows read back, the manifest says {f['rows']}")
            if _columns(reader, f"read_parquet('{uri}')") != f["columns"]:
                problems.append(f"{f['path']}: the columns read back differ from the manifest")
            if con is not None:
                live = con.execute(f"SELECT count(*) FROM {f['table']}").fetchone()[0]
                if live != f["rows"]:
                    problems.append(f"{f['path']}: the warehouse table now has {live} rows, the export {f['rows']}")
    finally:
        reader.close()
    return problems


def main() -> None:
    p = argparse.ArgumentParser(description="Export silver and gold to Parquet with a manifest of hashes, or verify an export")
    p.add_argument("--db", default=os.environ.get("DUCKDB_PATH", "data/warehouse/full.duckdb"))
    p.add_argument("--out", default="data/lake")
    p.add_argument("--verify", action="store_true", help="check an existing export; add --with-db to compare row counts with the warehouse")
    p.add_argument("--with-db", action="store_true")
    a = p.parse_args()
    out = Path(a.out)
    if a.verify:
        con = duckdb.connect(a.db, read_only=True) if a.with_db else None
        problems = verify(out, con)
        print("\n".join(problems) or "every file matches the manifest")
        sys.exit(1 if problems else 0)
    con = duckdb.connect(a.db, read_only=True)
    try:
        manifest = export(con, out)
    finally:
        con.close()
    for f in manifest["files"]:
        print(f"[{f['layer']}/{f['table']}] rows={f['rows']:,} bytes={f['bytes']:,} sha256={f['sha256'][:12]}")


if __name__ == "__main__":
    main()
