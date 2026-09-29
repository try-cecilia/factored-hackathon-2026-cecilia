"""Drift del tráfico: el PSI mide lo que cambió, no opina con pocos datos y el endpoint sigue la foto de referencia."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api import main
from ops import drift


def turn(language="es", disposition="AUTO_RESOLVE", category="resolved", intent="balance_inquiry", p=0.95):
    return {"language": language, "disposition": disposition, "category": category,
            "intent_reading": {"intent": intent, "p_intent": p}}


def traffic(n, **kw):
    return [turn(**kw) for _ in range(n)]


def test_identical_traffic_has_no_drift_and_a_shifted_mix_is_flagged():
    base = drift.snapshot(traffic(80) + traffic(20, language="pt"))
    same = drift.compare(base, traffic(80) + traffic(20, language="pt"))
    assert same["status"] == "stable" and same["signals"]["language"]["psi"] == 0
    shifted = drift.compare(base, traffic(30) + traffic(70, language="pt"))
    assert shifted["signals"]["language"]["status"] == "significant" and shifted["status"] == "significant"


def test_the_classifier_getting_less_sure_shows_up_in_confidence_even_if_language_is_the_same():
    base = drift.snapshot(traffic(100))
    now = drift.compare(base, traffic(40) + traffic(60, p=0.4))
    assert now["signals"]["language"]["status"] == "stable"
    assert now["signals"]["confidence"]["status"] == "significant"


def test_a_value_seen_on_one_side_only_is_finite():
    value = drift.psi({"a": 100}, {"b": 100})
    assert 0 < value < 100


def test_with_too_little_traffic_it_does_not_give_an_opinion():
    base = drift.snapshot(traffic(100))
    assert drift.compare(base, traffic(drift.MIN_N - 1))["status"] == "insufficient_data"
    assert drift.compare(drift.snapshot(traffic(5)), traffic(100))["status"] == "insufficient_data"


def test_rows_without_a_signal_are_left_out_of_that_signal_not_counted_as_a_category():
    rows = [{"language": "es"}, {"language": "es", "intent_reading": {"intent": "x", "p_intent": None}}]
    c = drift.counts(rows)
    assert c["language"] == {"es": 2} and c["intent"] == {"x": 1} and c["confidence"] == {}


def test_the_endpoints_need_the_admin_key_and_follow_the_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "k")
    monkeypatch.setenv("TRACE_LOG_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.setenv("DRIFT_BASELINE_PATH", str(tmp_path / "baseline.json"))
    client, hdr = TestClient(main.app), {"X-Admin-Key": "k"}
    assert client.get("/admin/drift").status_code == 401
    assert client.get("/admin/drift", headers=hdr).json()["status"] == "no_baseline"

    (tmp_path / "traces.jsonl").write_text("".join(json.dumps(r) + "\n" for r in traffic(80) + traffic(20, language="pt")), encoding="utf-8")
    assert client.post("/admin/drift/snapshot", headers=hdr).json()["n"] == 100
    assert client.get("/admin/drift", headers=hdr).json()["status"] == "stable"

    (tmp_path / "traces.jsonl").write_text("".join(json.dumps(r) + "\n" for r in traffic(20) + traffic(80, language="pt")), encoding="utf-8")
    assert client.get("/admin/drift", headers=hdr).json()["status"] == "significant"
    stored = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
    assert set(stored) == {"created_at", "n", "signals"}  # counts only: no traces, no customer data
