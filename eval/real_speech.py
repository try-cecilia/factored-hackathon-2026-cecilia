"""Does the intent classifier survive real customer speech? A zero-shot test on MInDS-14 (es-ES, pt-PT).

    python -m eval.real_speech        # writes docs/evidence/real_speech.{md,json}

Every text our classifier was trained or scored on was written by the team. MInDS-14 (PolyAI, CC BY 4.0) is 1,090 calls to
an e-banking line, transcribed by ASR: rambling, mis-heard words, no punctuation. The shipped model has never seen it.

Protocol, fixed before the model was run on a single message (the git history orders this file and its results):

1. **The model is not touched, trained or tuned on this data, and nothing changes whatever it shows**: not the model, the
   lexicon, the threshold nor this mapping. The classifier read is the runtime one (`agent.policy.intent_guard.read`).
2. **The mapping from MInDS-14's intents to ours is fixed below, from our own class definitions, without having read the
   predictions.** `PRIMARY` is the clear cases: two intents that are exactly one of ours (`balance`, `latest_transactions`)
   and three that are a request to change or open something, which our templates call `out_of_scope` ("change my phone
   number", "I need a new loan"). `SECONDARY` is `out_of_scope` by the same rule, applied to requests for an action or a
   procedure our assistant does not perform; it is reported apart because the fit is looser. `EXCLUDED` could be a security
   matter or not depending on what the caller says, so it is not scored.
3. **Reported:** per-class recall and overall accuracy of the classifier and of the keyword baseline on the same messages
   (paired), by language; the escalation guard's false escalations on every scored message (none of them is a required
   escalation under the mapping); and the classifier's confidence against its accuracy.
4. **Section "Reading it" is post-hoc.** It was added after the results were seen, to put them in proportion (the keyword
   baseline answers `out_of_scope` whenever no keyword matches, and most scored calls are `out_of_scope`), and is labeled as
   such in the report. The protocol's own tables are unchanged by it.
5. **Limits stated in advance:** these are European Spanish and Portuguese, our training text is Latin American; ASR text
   differs from typed chat; the dataset has no "check a payment" or "exchange rate" intent, so those classes cannot be scored;
   the labels are the dataset's, mapped by us, not re-annotated by a second person.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from agent.llm.baseline_classifier import classify as keyword_classify
from agent.policy import intent_guard
from agent.policy.signals import contains_escalation_signal
from eval.stats import fmt, paired_accuracy, rate

TSV = Path("eval/external/minds14-es-pt.tsv")
TSV_SHA256 = "4f7009ab14d157d1b595c7f2f4e26ef0974769d46633dfd5732aaf618f744e5a"  # of the file with LF line endings
OUT_JSON, OUT_MD = Path("docs/evidence/real_speech.json"), Path("docs/evidence/real_speech.md")

PRIMARY = {"balance": "balance_inquiry", "latest_transactions": "transaction_lookup",
           "address": "out_of_scope", "business_loan": "out_of_scope", "joint_account": "out_of_scope"}
SECONDARY = {"atm_limit": "out_of_scope", "direct_debit": "out_of_scope", "cash_deposit": "out_of_scope", "pay_bill": "out_of_scope",
             "high_value_payment": "out_of_scope", "abroad": "out_of_scope", "app_error": "out_of_scope"}
EXCLUDED = ("freeze", "card_issues")
CONFIDENCE_CUTS = (0.5, 0.6, 0.8)


def sha256_lf(path: Path) -> str:
    """The hash of the file with LF line endings, so a Windows checkout that converts them still matches."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load(path: Path = TSV) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    for r in rows:
        r["tier"] = "primary" if r["intent"] in PRIMARY else "secondary" if r["intent"] in SECONDARY else "excluded"
        r["truth"] = PRIMARY.get(r["intent"]) or SECONDARY.get(r["intent"])
    return rows


def read_all(rows: list[dict]) -> list[dict]:
    """The runtime reading of every message, and the keyword baseline's and the lexicon's, kept beside the row."""
    out = []
    for r in rows:
        reading = intent_guard.read(r["transcription"])
        out.append(r | {"pred": reading.intent, "p_pred": reading.p_intent, "p_escalation": reading.p_escalation, "threshold": reading.threshold,
                        "baseline": keyword_classify(r["transcription"]), "lexicon": contains_escalation_signal(r["transcription"])})
    return out


def _acc(rows: list[dict], key: str) -> dict:
    return rate(sum(r[key] == r["truth"] for r in rows), len(rows))


def summarize(read: list[dict]) -> dict:
    scored = [r for r in read if r["truth"]]
    primary = [r for r in scored if r["tier"] == "primary"]
    secondary = [r for r in scored if r["tier"] == "secondary"]
    out = {"n_total": len(read), "n_excluded": sum(r["tier"] == "excluded" for r in read), "n_primary": len(primary), "n_secondary": len(secondary),
           "by_intent": dict(Counter(r["intent"] for r in read))}
    for name, rows in (("primary", primary), ("secondary", secondary), ("all_scored", scored)):
        block = {"learned": _acc(rows, "pred"), "keyword": _acc(rows, "baseline"),
                 "paired": paired_accuracy([r["truth"] for r in rows], [r["baseline"] for r in rows], [r["pred"] for r in rows]) if rows else None,
                 "by_language": {lang: {"n": len(sub), "learned": _acc(sub, "pred"), "keyword": _acc(sub, "baseline")}
                                 for lang in sorted({r["lang"] for r in rows}) for sub in [[r for r in rows if r["lang"] == lang]]},
                 "by_true_class": {c: {"n": len(sub), "learned": _acc(sub, "pred"), "keyword": _acc(sub, "baseline")}
                                   for c in sorted({r["truth"] for r in rows}) for sub in [[r for r in rows if r["truth"] == c]]}}
        out[name] = block
    out["by_dataset_intent"] = {i: {"n": len(sub), "tier": sub[0]["tier"], "truth": sub[0]["truth"], "learned": _acc(sub, "pred"), "keyword": _acc(sub, "baseline")}
                                for i in sorted({r["intent"] for r in scored}) for sub in [[r for r in scored if r["intent"] == i]]}
    inscope, oos = [r for r in primary if r["truth"] != "out_of_scope"], [r for r in primary if r["truth"] == "out_of_scope"]
    out["post_hoc"] = {
        "out_of_scope_share_of_primary": rate(len(oos), len(primary)),
        "in_scope_only": {"learned": _acc(inscope, "pred"), "keyword": _acc(inscope, "baseline"),
                          "paired": paired_accuracy([r["truth"] for r in inscope], [r["baseline"] for r in inscope], [r["pred"] for r in inscope]) if inscope else None},
        "out_of_scope_fate": {"correct": rate(sum(r["pred"] == "out_of_scope" for r in oos), len(oos)),
                              "escalated_to_a_person": rate(sum(r["pred"] == "requires_escalation" for r in oos), len(oos)),
                              "read_as_an_in_scope_request": rate(sum(r["pred"] not in ("out_of_scope", "requires_escalation") for r in oos), len(oos))}}
    out["confusion_primary"] = {t: dict(Counter(r["pred"] for r in primary if r["truth"] == t)) for t in sorted({r["truth"] for r in primary})}
    # The guard: no scored message is a required escalation, so every firing is a false escalation.
    guard = {}
    for label, fires in (("lexicon_only", lambda r: r["lexicon"]), ("classifier_only", lambda r: (r["p_escalation"] or 0) >= r["threshold"]),
                         ("lexicon_or_classifier (runtime)", lambda r: r["lexicon"] or (r["p_escalation"] or 0) >= r["threshold"])):
        fired = [r for r in scored if fires(r)]
        guard[label] = {"false_escalation": rate(len(fired), len(scored)),
                        "by_language": {lang: rate(sum(1 for r in fired if r["lang"] == lang), sum(1 for r in scored if r["lang"] == lang)) for lang in sorted({r["lang"] for r in scored})},
                        "examples": [{"lang": r["lang"], "intent": r["intent"], "text": r["transcription"]} for r in fired[:12]]}
    out["guard"] = guard
    out["confidence"] = [{"p_at_least": c, "accepted": rate(sum(1 for r in scored if (r["p_pred"] or 0) >= c), len(scored)),
                          "accuracy_when_accepted": _acc([r for r in scored if (r["p_pred"] or 0) >= c], "pred")} for c in CONFIDENCE_CUTS]
    out["errors_primary"] = [{"lang": r["lang"], "intent": r["intent"], "truth": r["truth"], "pred": r["pred"], "p": round(r["p_pred"] or 0, 2), "text": r["transcription"]}
                             for r in primary if r["pred"] != r["truth"]]
    return out


def to_markdown(s: dict, generated_at: str) -> str:
    pr, se = s["primary"], s["secondary"]
    L = ["# Real customer speech: the intent classifier on MInDS-14 (es-ES, pt-PT)", "",
         f"Generated by `python -m eval.real_speech` at {generated_at}. Protocol, fixed before the model was run on any message, in the module's docstring: "
         "**the shipped model is not trained or tuned on this data and nothing changes whatever it shows.** Data: PolyAI MInDS-14 (CC BY 4.0), "
         "calls to an e-banking line transcribed by ASR (`eval/external/README.md`).", "",
         "## What was scored", "",
         f"{s['n_total']:,} calls: {s['n_primary']} in the primary mapping (`balance` and `latest_transactions` to their namesakes; `address`, `business_loan`, `joint_account` "
         f"to `out_of_scope`), {s['n_secondary']} in the secondary one (other requests for an action or a procedure, as `out_of_scope`), and {s['n_excluded']} excluded (`freeze`, `card_issues`: "
         "they may or may not be a security matter). Our `payment_status` and `exchange_rate_inquiry` have no counterpart in the dataset and cannot be scored.", "",
         "## 1. Primary mapping", "",
         "| | Learned classifier | Keyword baseline |", "|---|---|---|",
         f"| Accuracy | {fmt(pr['learned'])} | {fmt(pr['keyword'])} |", ""]
    p = pr["paired"]
    L += [f"On the same {p['n']} calls the learned classifier is right where the keywords are wrong on {p['only_b_right']} and the reverse on {p['only_a_right']}: "
          f"{p['diff'] * 100:+.1f} points (paired bootstrap 95% [{p['diff_ci95'][0] * 100:+.1f}, {p['diff_ci95'][1] * 100:+.1f}], exact McNemar p = {p['mcnemar_p']}).", "",
          "| True class | n | Learned recall | Keyword recall |", "|---|---|---|---|"]
    L += [f"| {c} | {v['n']} | {fmt(v['learned'])} | {fmt(v['keyword'])} |" for c, v in pr["by_true_class"].items()]
    L += ["", "| Language | n | Learned | Keyword |", "|---|---|---|---|"]
    L += [f"| {lang} | {v['n']} | {fmt(v['learned'])} | {fmt(v['keyword'])} |" for lang, v in pr["by_language"].items()]
    classes = sorted({c for row in s["confusion_primary"].values() for c in row} | set(s["confusion_primary"]))
    L += ["", "What the learned classifier answered, by true class:", "", "| True class | " + " | ".join(classes) + " |", "|---|" + "---|" * len(classes)]
    L += [f"| {t} | " + " | ".join(str(row.get(c, 0)) for c in classes) + " |" for t, row in s["confusion_primary"].items()]
    L += ["", "## 2. Secondary mapping (looser fit, `out_of_scope` only)", "",
          f"{se['learned']['n']} calls: learned recall {fmt(se['learned'])}, keyword {fmt(se['keyword'])}. ", "",
          "| Dataset intent | n | Learned recall | Keyword recall |", "|---|---|---|---|"]
    L += [f"| {i} ({v['tier']}) | {v['n']} | {fmt(v['learned'])} | {fmt(v['keyword'])} |" for i, v in sorted(s["by_dataset_intent"].items(), key=lambda kv: (kv[1]["tier"], kv[0]))]
    L += ["", "## 3. The escalation guard on real speech", "",
          f"None of the {pr['learned']['n'] + se['learned']['n']} scored calls is a required escalation under the mapping, so every time the guard fires it is a false escalation.", "",
          "| Guard | False escalations | es-ES | pt-PT |", "|---|---|---|---|"]
    for name, g in s["guard"].items():
        langs = g["by_language"]
        L.append(f"| {name} | {fmt(g['false_escalation'])} | {fmt(langs['es-ES'])} | {fmt(langs['pt-PT'])} |")
    shown = s["guard"]["lexicon_or_classifier (runtime)"]["examples"]
    if shown:
        L += ["", "Calls the runtime guard sent to a person (up to 12):", ""] + [f"- `{e['intent']}` ({e['lang']}): {e['text']}" for e in shown]
    L += ["", "## 4. Confidence against accuracy", "",
          "Over every scored call, how often the classifier is at least this sure of its answer, and how often that answer is right.", "",
          "| At least | Share of calls | Accuracy when that sure |", "|---|---|---|"]
    L += [f"| {c['p_at_least']} | {fmt(c['accepted'])} | {fmt(c['accuracy_when_accepted'])} |" for c in s["confidence"]]
    L += ["", "## 5. Where it is wrong on the primary mapping", ""]
    errs = s["errors_primary"]
    L += [f"{len(errs)} of {pr['learned']['n']} calls (up to 25 shown):", ""] + [f"- `{e['truth']}` read as `{e['pred']}` (p = {e['p']}, {e['lang']}, {e['intent']}): {e['text']}" for e in errs[:25]]
    ph = s["post_hoc"]
    ins, fate = ph["in_scope_only"], ph["out_of_scope_fate"]
    L += ["", "## 6. Reading it (written after the results were seen)", "",
          f"The keyword baseline answers `out_of_scope` whenever no keyword matches, and {fmt(ph['out_of_scope_share_of_primary'])} of the primary calls are `out_of_scope`, "
          "so most of its accuracy is that default, not skill. Two cuts put the result in proportion:", "",
          f"- **Only the in-scope calls** (`balance`, `latest_transactions`): learned {fmt(ins['learned'])}, keyword {fmt(ins['keyword'])}; "
          f"the learned classifier is right where the keywords are wrong on {ins['paired']['only_b_right']} and the reverse on {ins['paired']['only_a_right']} "
          f"(McNemar p = {ins['paired']['mcnemar_p']}). Where the assistant has a tool to run, the learned reading does at least as well on real speech.",
          f"- **What happens to an out-of-scope call** (the weak spot): read correctly {fmt(fate['correct'])}; sent to a person {fmt(fate['escalated_to_a_person'])}; "
          f"read as an in-scope request {fmt(fate['read_as_an_in_scope_request'])}. The first error is a wasted hand-off, the second a wrong tool the policy and the confirmation step still have to catch.",
          "", "Both numbers are about one model and one dataset, and the data is now spent as an external test: changing the classifier and re-scoring on the same calls would not be a test.", "",
          "## What this does not show", "",
          "- European Spanish and Portuguese, transcribed by ASR, against a model trained on Latin American text typed by the team: a real distribution shift, but not our customers.",
          "- The labels are the dataset's own, mapped to ours by a rule written beforehand. No second person re-annotated them.",
          "- The dataset has no `payment_status` or `exchange_rate_inquiry` calls, so two of our six classes are untested here.",
          "- Calls whose dataset intent is `freeze` or `card_issues` are excluded, so this says nothing about whether real fraud and theft calls are escalated.", ""]
    return "\n".join(L)


def main() -> None:
    if sha256_lf(TSV) != TSV_SHA256:
        raise SystemExit(f"{TSV} is not the file this protocol was fixed on (sha256 of its LF-normalized bytes differs)")
    s = summarize(read_all(load()))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT_JSON.write_text(json.dumps({"generated_at": stamp, **s}, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text(to_markdown(s, stamp), encoding="utf-8")
    print(OUT_MD.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
