"""The real-speech validation: the data is the file the protocol was fixed on, the mapping is complete and disjoint, nothing trains on it, and the arithmetic is right."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from eval import real_speech as rs

SIX = {"balance_inquiry", "transaction_lookup", "payment_status", "exchange_rate_inquiry", "out_of_scope", "requires_escalation"}
INTENTS = {"abroad", "address", "app_error", "atm_limit", "balance", "business_loan", "card_issues", "cash_deposit", "direct_debit",
           "freeze", "high_value_payment", "joint_account", "latest_transactions", "pay_bill"}


def test_the_data_is_the_file_the_protocol_was_fixed_on():
    assert rs.sha256_lf(rs.TSV) == rs.TSV_SHA256
    rows = rs.load()
    assert len(rows) == 1090 and Counter(r["lang"] for r in rows) == {"es-ES": 486, "pt-PT": 604}
    assert {r["intent"] for r in rows} == INTENTS and all(r["transcription"].strip() for r in rows)


def test_the_mapping_covers_every_dataset_intent_exactly_once_and_only_to_our_classes():
    groups = [set(rs.PRIMARY), set(rs.SECONDARY), set(rs.EXCLUDED)]
    assert set().union(*groups) == INTENTS and sum(len(g) for g in groups) == len(INTENTS)
    assert set(rs.PRIMARY.values()) | set(rs.SECONDARY.values()) <= SIX
    assert set(rs.SECONDARY.values()) == {"out_of_scope"}  # the looser tier only ever says "not something we do"
    assert "requires_escalation" not in set(rs.PRIMARY.values()) | set(rs.SECONDARY.values())  # no scored call is a required escalation


def test_excluded_calls_carry_no_truth_and_are_not_scored():
    rows = rs.load()
    assert all(r["truth"] is None for r in rows if r["tier"] == "excluded")
    assert {r["intent"] for r in rows if r["tier"] == "excluded"} == set(rs.EXCLUDED)


def test_nothing_that_trains_selects_or_tunes_the_classifier_names_this_data():
    for path in ("eval/evaluate_intent_classifier.py", "eval/test_cases/build_intent_dataset.py", "eval/model_study.py",
                 "agent/llm/intent_classifier.py", "agent/policy/intent_guard.py", "agent/policy/signals.py"):
        p = Path(path)
        if p.exists():
            text = p.read_text(encoding="utf-8").lower()
            assert "minds14" not in text and "minds-14" not in text, path


def _read(lang, intent, pred, baseline, p=0.9, p_esc=0.0, lexicon=False):
    truth = rs.PRIMARY.get(intent) or rs.SECONDARY.get(intent)
    tier = "primary" if intent in rs.PRIMARY else "secondary" if intent in rs.SECONDARY else "excluded"
    return {"lang": lang, "intent": intent, "transcription": "x", "tier": tier, "truth": truth, "pred": pred, "baseline": baseline,
            "p_pred": p, "p_escalation": p_esc, "threshold": 0.55, "lexicon": lexicon}


def test_the_summary_counts_what_it_says_and_leaves_the_excluded_out():
    read = [_read("es-ES", "balance", "balance_inquiry", "out_of_scope"), _read("es-ES", "balance", "out_of_scope", "out_of_scope"),
            _read("pt-PT", "address", "out_of_scope", "out_of_scope"), _read("pt-PT", "pay_bill", "payment_status", "out_of_scope", p=0.4),
            _read("es-ES", "freeze", "requires_escalation", "requires_escalation", p_esc=0.9, lexicon=True)]
    s = rs.summarize(read)
    assert (s["n_total"], s["n_primary"], s["n_secondary"], s["n_excluded"]) == (5, 3, 1, 1)
    assert s["primary"]["learned"]["k"] == 2 and s["primary"]["keyword"]["k"] == 1 and s["primary"]["learned"]["n"] == 3
    assert s["secondary"]["learned"]["k"] == 0 and s["by_dataset_intent"]["pay_bill"]["tier"] == "secondary"
    assert s["confusion_primary"]["balance_inquiry"] == {"balance_inquiry": 1, "out_of_scope": 1}


def test_the_guard_counts_a_firing_on_a_scored_call_as_a_false_escalation_and_ignores_the_excluded():
    read = [_read("es-ES", "balance", "balance_inquiry", "out_of_scope", p_esc=0.7), _read("pt-PT", "address", "out_of_scope", "out_of_scope", lexicon=True),
            _read("pt-PT", "balance", "balance_inquiry", "balance_inquiry"), _read("es-ES", "freeze", "requires_escalation", "requires_escalation", p_esc=0.9, lexicon=True)]
    g = rs.summarize(read)["guard"]
    assert g["classifier_only"]["false_escalation"]["k"] == 1 and g["lexicon_only"]["false_escalation"]["k"] == 1
    assert g["lexicon_or_classifier (runtime)"]["false_escalation"] == {"k": 2, "n": 3, "rate": 0.6667, "ci95": g["lexicon_or_classifier (runtime)"]["false_escalation"]["ci95"]}


def test_confidence_cuts_report_accuracy_only_among_the_calls_that_are_that_sure():
    read = [_read("es-ES", "balance", "balance_inquiry", "x", p=0.9), _read("es-ES", "balance", "out_of_scope", "x", p=0.55), _read("es-ES", "address", "out_of_scope", "x", p=0.7)]
    cuts = {c["p_at_least"]: c for c in rs.summarize(read)["confidence"]}
    assert cuts[0.5]["accepted"]["k"] == 3 and cuts[0.8]["accepted"]["k"] == 1 and cuts[0.8]["accuracy_when_accepted"]["rate"] == 1.0


def test_the_post_hoc_cuts_split_the_primary_calls_into_in_scope_and_out_of_scope_fates():
    read = [_read("es-ES", "balance", "balance_inquiry", "out_of_scope"), _read("es-ES", "latest_transactions", "balance_inquiry", "transaction_lookup"),
            _read("es-ES", "address", "out_of_scope", "out_of_scope"), _read("es-ES", "address", "requires_escalation", "out_of_scope"),
            _read("pt-PT", "business_loan", "payment_status", "out_of_scope"), _read("pt-PT", "joint_account", "out_of_scope", "out_of_scope")]
    ph = rs.summarize(read)["post_hoc"]
    assert ph["out_of_scope_share_of_primary"]["k"] == 4 and ph["in_scope_only"]["learned"]["k"] == 1 and ph["in_scope_only"]["keyword"]["k"] == 1
    fate = ph["out_of_scope_fate"]
    assert (fate["correct"]["k"], fate["escalated_to_a_person"]["k"], fate["read_as_an_in_scope_request"]["k"], fate["correct"]["n"]) == (2, 1, 1, 4)
