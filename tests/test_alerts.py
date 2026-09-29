from ops.alerts import evaluate

QUIET_OPS = {"turns": 100, "handoff_unverified": 0, "llm_unavailable": 0, "latency_ms_p95": 3000, "escalations_by_category": {}}
OK_BUDGET = {"exhausted": False}
OK_DQ = {"summary": {"status": "success", "errors_failed": 0}}


def test_quiet_system_raises_nothing():
    assert evaluate(QUIET_OPS, OK_BUDGET, OK_DQ) == []


def test_each_signal_fires_on_its_own():
    cases = [
        ({**QUIET_OPS, "handoff_unverified": 1}, OK_BUDGET, OK_DQ, "handoff_unverified"),
        ({**QUIET_OPS, "llm_unavailable": 2}, OK_BUDGET, OK_DQ, "llm_unavailable"),
        ({**QUIET_OPS, "latency_ms_p95": 9000}, OK_BUDGET, OK_DQ, "p95"),
        ({**QUIET_OPS, "escalations_by_category": {"security": 6}}, OK_BUDGET, OK_DQ, "security"),
        (QUIET_OPS, {"exhausted": True}, OK_DQ, "budget"),
        (QUIET_OPS, OK_BUDGET, {"summary": {"status": "success", "errors_failed": 1}}, "data quality"),
        (QUIET_OPS, OK_BUDGET, None, "data quality"),
    ]
    for ops, budget, dq, word in cases:
        found = evaluate(ops, budget, dq)
        assert len(found) == 1 and word in found[0], (word, found)


def test_security_at_threshold_does_not_fire():
    assert evaluate({**QUIET_OPS, "escalations_by_category": {"security": 5}}, OK_BUDGET, OK_DQ) == []
