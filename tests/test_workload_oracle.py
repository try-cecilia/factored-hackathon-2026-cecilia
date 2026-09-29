"""El oráculo de revisión de rastreos: decide con la política escrita, sin llamar al código del sistema."""
from __future__ import annotations

import datetime as dt

import pytest

from agent.tools import account_tools
from eval import workload


def test_the_oracle_names_each_reason_and_ages_first(monkeypatch):
    monkeypatch.setattr(account_tools, "data_as_of", lambda: dt.date(2026, 6, 18))

    def reason(day, opened=None, registered=None):
        monkeypatch.setattr(workload, "_rows", lambda sql, params=(): [{"day": day, "opened": opened, "registered": registered}])
        return workload.movement_review_reason("X")

    assert reason(dt.date(2026, 3, 10)) == "older_than_review_threshold"          # 100 days
    assert reason(dt.date(2026, 6, 8)) is None                                    # 10 days
    assert reason(dt.date(2026, 6, 8), opened=dt.date(2026, 6, 9)) == "before_product_opening"
    assert reason(dt.date(2026, 6, 8), registered=dt.date(2026, 6, 9)) == "before_customer_registration"
    assert reason(dt.date(2026, 3, 10), opened=dt.date(2026, 6, 9)) == "older_than_review_threshold"


def test_the_oracle_has_the_same_threshold_as_the_system_but_its_own_constant():
    assert workload.REVIEW_AFTER_DAYS == account_tools.TRACE_REVIEW_AFTER_DAYS == 90


@pytest.mark.parametrize("days", [90, 0])
def test_the_oracle_and_the_system_agree_on_every_pending_movement_of_the_fixture(monkeypatch, days):
    monkeypatch.setattr(workload, "REVIEW_AFTER_DAYS", days)
    monkeypatch.setattr(account_tools, "TRACE_REVIEW_AFTER_DAYS", days)
    customers = [r["customer_id"] for r in workload._rows(
        "SELECT DISTINCT customer_id FROM transactions WHERE transaction_status = 'Pending'")]
    reasons = []
    for cid in customers:
        for item in account_tools.request_trace(cid)["items"]:
            assert workload.movement_review_reason(item["transaction_id"]) == item["review_reason"], item["transaction_id"]
            reasons.append(item["review_reason"])
    assert reasons                       # the fixture has pending movements: the check is not vacuous
    if days == 0:
        assert "older_than_review_threshold" in reasons


def trace_templates(cases):
    return {c.template: c for c in cases if c.template.startswith("trace_")}


def test_a_recent_pending_movement_is_a_confirm_and_never_a_review():
    found = trace_templates(workload.generate(per_cell=1, seed=3))
    assert {"trace_confirm", "trace_cancel"} <= set(found) and "trace_review" not in found
    assert found["trace_confirm"].expected["transaction_id"] == "TXN-FIX0006"


def test_a_movement_that_needs_review_is_a_review_case_with_the_reason_and_nothing_opened(monkeypatch):
    monkeypatch.setattr(workload, "REVIEW_AFTER_DAYS", 0)          # the fixture's one pending movement is now "old"
    found = trace_templates(workload.generate(per_cell=1, seed=3))
    assert "trace_review" in found and "trace_confirm" not in found and "trace_cancel" not in found
    review = found["trace_review"]
    assert review.category == "human_required" and len(review.turns) == 2
    assert review.expected == {"disposition": "ESCALATE", "category_in": ["trace_review"], "product_id": "PRD-FIX0010",
                               "transaction_id": "TXN-FIX0006", "review_reason": "older_than_review_threshold"}


def test_the_other_templates_do_not_depend_on_what_the_trace_block_does(monkeypatch):
    """The trace pass has its own seed: changing which movements need review must not change any other case."""
    def others():
        return sorted((c.case_id, tuple(c.turns)) for c in workload.generate(per_cell=1, seed=3) if not c.template.startswith("trace_"))

    baseline = others()
    monkeypatch.setattr(workload, "REVIEW_AFTER_DAYS", 0)
    assert others() == baseline
