"""The Parquet export: what it writes, that it reads back as the tables, and that a copy that changed is caught."""
from __future__ import annotations

import json

import duckdb
import pytest

from data import gold, lake
from tests.conftest import build_fixture_warehouse


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    path = tmp_path / "w.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(path))
    build_fixture_warehouse()
    con = duckdb.connect(str(path))
    gold.build(con)
    yield con
    con.close()


def test_every_silver_table_and_built_mart_is_exported_with_its_rows_hash_and_columns(warehouse, tmp_path):
    out = tmp_path / "lake"
    manifest = lake.export(warehouse, out)
    by_table = {f["table"]: f for f in manifest["files"]}
    assert {"customers", "products", "transactions", "gold_daily_activity", "gold_customer_summary"} <= set(by_table)
    assert "gold_contact_demand" not in by_table  # no contact-center tables in this warehouse: that mart was skipped
    assert by_table["transactions"]["layer"] == "silver" and by_table["gold_daily_activity"]["layer"] == "gold"
    for f in manifest["files"]:
        assert f["rows"] == warehouse.execute(f"SELECT count(*) FROM {f['table']}").fetchone()[0]
        assert len(f["sha256"]) == 64 and f["columns"][0]["name"]
    assert manifest["silver_runs"]["transactions"] and manifest["gold_runs"]["gold_daily_activity"]
    assert lake.verify(out) == [] and lake.verify(out, warehouse) == []


def test_a_file_reads_back_as_exactly_the_table_it_came_from(warehouse, tmp_path):
    out = tmp_path / "lake"
    lake.export(warehouse, out)
    uri = (out / "gold" / "gold_customer_summary.parquet").as_posix()
    missing = warehouse.execute(f"SELECT * FROM gold_customer_summary EXCEPT SELECT * FROM read_parquet('{uri}')").fetchall()
    extra = warehouse.execute(f"SELECT * FROM read_parquet('{uri}') EXCEPT SELECT * FROM gold_customer_summary").fetchall()
    assert missing == [] and extra == []


def test_an_edited_truncated_or_missing_file_fails_the_verification(warehouse, tmp_path):
    out = tmp_path / "lake"
    lake.export(warehouse, out)
    target = out / "silver" / "customers.parquet"
    original = target.read_bytes()
    target.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    assert any("customers.parquet" in p and "SHA-256" in p for p in lake.verify(out))
    target.write_bytes(original[: len(original) // 2])
    assert any("customers.parquet" in p for p in lake.verify(out))
    target.unlink()
    assert any("missing" in p for p in lake.verify(out))


def test_a_manifest_edited_to_match_a_swapped_file_still_shows_in_the_row_count(warehouse, tmp_path):
    out = tmp_path / "lake"
    lake.export(warehouse, out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    entry = next(f for f in manifest["files"] if f["table"] == "customers")
    entry["rows"] += 1
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert any("rows read back" in p for p in lake.verify(out))


def test_the_warehouse_changing_after_the_export_is_reported(warehouse, tmp_path):
    out = tmp_path / "lake"
    lake.export(warehouse, out)
    warehouse.execute("DELETE FROM branches WHERE branch_id = (SELECT min(branch_id) FROM branches)")
    assert any("branches" in p and "warehouse table now has" in p for p in lake.verify(out, warehouse))


def test_there_is_nothing_to_verify_without_a_manifest(tmp_path):
    assert "does not exist" in lake.verify(tmp_path)[0]
