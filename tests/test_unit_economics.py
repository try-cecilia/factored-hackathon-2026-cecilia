"""The unit-economics report: its arithmetic, that it agrees with the projection we already publish, and that the committed copy is current."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis import unit_economics as ue


def test_hours_are_contacts_times_handle_time_and_the_shares_add_to_a_hundred():
    rows = ue.where_the_time_goes({"operations_by_reason": [
        {"reason_category": "A", "contacts": 100, "aht_s": 360.0, "fcr_pct": 90.0},
        {"reason_category": "B", "contacts": 50, "aht_s": 1440.0, "fcr_pct": 40.0}]})
    assert [r["reason"] for r in rows] == ["B", "A"]  # 20 hours against 10: sorted by hours, not by contacts
    assert [r["handle_hours"] for r in rows] == [20, 10]
    assert [r["contact_share_pct"] for r in rows] == [33.3, 66.7] and [r["hours_share_pct"] for r in rows] == [66.7, 33.3]


def test_a_scenario_is_the_text_share_plus_the_assumed_shift_of_the_phone_share():
    rows = ue.scenarios(monthly=1000, text_share=0.2, aht_s=360, sar=0.5, model_usd_per_case=0.01)
    assert [r["phone_to_text_shift_pct"] for r in rows] == [0, 10, 25, 50]
    none, tenth, quarter, half = rows
    assert none["in_scope_contacts"] == 200 and none["automated_contacts"] == 100 and none["agent_hours_saved"] == 10.0
    assert tenth["in_scope_contacts"] == 280 and quarter["in_scope_contacts"] == 400 and half["in_scope_contacts"] == 600
    assert none["share_of_transactional_hours_pct"] == 10.0  # 10 hours saved of the 100 the month's contacts take
    assert none["usd_avoided"] == {"5": 50, "10": 100, "20": 200} and none["model_cost_usd"] == 2.0


def test_automating_more_never_saves_less_and_a_perfect_rate_cannot_exceed_the_hours_there_are():
    rows = ue.scenarios(monthly=6701, text_share=0.15, aht_s=221, sar=1.0, model_usd_per_case=0.0014)
    saved = [r["agent_hours_saved"] for r in rows]
    assert saved == sorted(saved) and all(r["share_of_transactional_hours_pct"] <= 100 for r in rows)


def test_the_no_shift_scenario_is_the_projection_the_evaluation_already_publishes():
    live = json.loads(ue.LIVE.read_text(encoding="utf-8"))
    published = live["projection"]
    today = ue.compute()["scenarios_at_live_sar"][0]
    assert today["automated_contacts"] == published["projected_monthly_automated_contacts"]
    assert today["agent_hours_saved"] == published["projected_monthly_agent_hours_saved"]
    assert today["model_cost_usd"] == published["roi"]["rows"][0]["monthly_model_cost_usd"]
    for row in published["roi"]["rows"]:
        assert today["usd_avoided"][str(row["agent_cost_per_hour_usd"])] == pytest.approx(row["monthly_human_cost_avoided_usd"], abs=1)


def test_the_committed_report_is_what_the_inputs_give_today():
    committed = json.loads(Path("docs/evidence/unit_economics.json").read_text(encoding="utf-8"))
    fresh = ue.compute()
    committed.pop("generated_at"), fresh.pop("generated_at")
    assert fresh == committed, "docs/evidence/unit_economics.json is stale: run `python -m analysis.unit_economics`"
