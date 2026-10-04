"""The by-language view counts every language and run on its own, and only joins reports of the same cases and code."""
from __future__ import annotations

import pytest

from eval.live_by_language import systems, table


def _row(language: str, repeat: int, **changes) -> dict:
    return {"case_id": f"{language}{repeat}", "template": "balance_all", "language": language, "repeat": repeat,
            "actual": "AUTO_RESOLVE", "in_scope": True, "safe_resolution": True, "disposition_scored": True,
            "disposition_ok": True, "should_escalate": False, "escalated": False, "escalation_acceptable": False,
            "transfer_attempted": False, "ticket_complete": None, "unsafe": [], "incorrect_not_unsafe": [],
            "records_sent_to_model": [], "latency_ms": 1.0, "cost_usd": 0.0, "tokens": 0, "llm_calls": 0} | changes


def test_each_language_and_run_is_counted_alone():
    rows = [_row("es", 1), _row("es", 2, template="trace_review", in_scope=False, should_escalate=True, escalation_acceptable=True),
            _row("pt", 1, safe_resolution=False, disposition_ok=False, unsafe=["wrong_account_or_figure"])]
    es1, es2, pt1 = table({"proposed (live: m)": rows})[2:]
    assert es1.startswith("| proposed (live: m) | es | 1 | 1 | 100.0%") and "| 0 of 1 |" in es1
    assert "| es | 2 | 1 | n/a (n=0) |" in es2 and "| 1 of 1 (trace_review) |" in es2
    assert "| pt | 1 | 1 | 0.0%" in pt1 and "| 1 of 1 (wrong_account_or_figure) |" in pt1


def test_the_baseline_joins_only_the_same_cases_measured_on_the_same_code():
    live = {"policy_sha256": "a", "cases": {"proposed (live: m)": [_row("es", 1), _row("es", 1)]}}
    offline = {"policy_sha256": "a", "cases": {"baseline": [_row("es", 1)]}}
    assert list(systems(live, offline)) == ["baseline (keyword bot)", "proposed (live: m)"]
    with pytest.raises(SystemExit, match="different code"):
        systems(live, offline | {"policy_sha256": "b"})
    with pytest.raises(SystemExit, match="not the cases"):
        systems(live, {"policy_sha256": "a", "cases": {"baseline": [_row("pt", 1)]}})
