"""Runs the guardrail scenario suite (eval/run_guardrail_eval.py) as an
automated test: the safety-critical assertions (zero unsafe outcomes, full
escalation recall) must never regress silently.
"""
from eval.run_guardrail_eval import _pick_fixtures, build_scenarios, compute_rubric_metrics, run_scenario


def test_guardrail_scenarios_pass_with_zero_unsafe_outcomes():
    fx = _pick_fixtures()
    scenarios = build_scenarios(fx)
    outcomes = [run_scenario(s, fx) for s in scenarios]
    metrics = compute_rubric_metrics(outcomes)

    mismatches = [o for o in outcomes if not o["correct"]]
    assert not mismatches, f"Scenario mismatches: {mismatches}"
    assert metrics["unsafe_outcomes_count"] == 0
    assert metrics["escalation_recall"] == 1.0
