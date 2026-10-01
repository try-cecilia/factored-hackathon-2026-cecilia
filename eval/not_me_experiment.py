"""Experiment: scope the lexicon's "no fui yo" pattern to a disavowed movement (docs/preregistration.md, section 1c).

The rule, the sentences (`eval/test_cases/not_me_lexicon_set.csv`, hashed in the preregistration) and the criteria were written
before this module ran. The model, tau and every other lexicon pattern stay as they are; only the two "not me" entries change.

    python -m eval.not_me_experiment          # writes eval/reports/not_me_experiment.{json,md}; exit 1 if a criterion fails

The existing labeled sets (training, dev, test, trace requests, MInDS-14) are read only as counts of how many messages
change: no sentence from them is written to the report.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path

from agent.policy import intent_guard, signals
from eval.stats import fmt, rate

SET = Path("eval/test_cases/not_me_lexicon_set.csv")
SET_SHA256 = "ed36fe26db31242421ee4de8106ac0498346832ecdf362c88416dd1a6e27bdeb"
OUT_JSON, OUT_MD = Path("eval/reports/not_me_experiment.json"), Path("eval/reports/not_me_experiment.md")
ESC = "requires_escalation"

CURRENT = [r"\b(yo no fui|no fui yo)\b", r"\b(eu nao fui|nao fui eu)\b"]  # the two entries of the lexicon today
FAMILY = r"(?:yo no fui|no fui yo|eu nao fui|nao fui eu)"
MOVEMENT = "|".join([
    r"cargos?", r"compras?", r"movimientos?", r"transferencias?", r"pagos?", r"transaccion(?:es)?", r"retiros?", r"debitos?",
    r"consumos?", r"operacion(?:es)?", r"cobros?", r"descuentos?", r"depositos?", r"gastos?", r"extraccion(?:es)?", r"giros?",
    "autorizo|autorizaron|compro|compraron|retiro|retiraron|transfirio|transfirieron|cobro|cobraron|gasto|gastaron|firmo|deposito"
    "|depositaron|pago|pagaron",
    r"cobranc(?:a|as)", r"transac(?:ao|oes)", r"movimentac(?:ao|oes)", r"lancamentos?", r"pagamentos?", r"saques?",
    r"operac(?:ao|oes)", r"descontos?", "pix",
    "autorizou|autorizaram|comprou|compraram|sacou|sacaram|transferiu|transferiram|cobrou|cobraram|gastou|gastaram|pagou|pagaram"
    "|depositou|depositaram|debitou|debitaram",
])
CANDIDATE = [
    rf"\b{FAMILY}\b\s*(?:[,.;:!?]|$)",                                            # stands alone: the clause ends with it
    rf"^(?=.*\b(?:{MOVEMENT})\b).*?\b{FAMILY}\b(?! (?:a|al|ao|para|pra|pro)\b)",   # names a movement, and is not "I did not go to"
]

KNOWN_INNOCENT = [  # the four sentences reported on PR #16 (reproduction, not a result)
    "No fui yo al banco ayer, quiero saber mi saldo", "Yo no fui al banco ayer, quiero saber mi saldo",
    "Eu não fui ao banco ontem, qual é meu saldo?", "No fui yo quien pidió consultar el saldo; fue mi esposa",
]
KNOWN_POSITIVE = [  # tests/test_signals_not_me.py
    "Ese cargo no fui yo", "yo no fui, revisen mi cuenta", "Essa compra não fui eu", "eu não fui, bloqueiem o cartão",
]


@contextmanager
def lexicon(not_me: list[str]):
    """The lexicon with its two "not me" entries replaced by `not_me`; nothing else changes."""
    kept = [p for p in signals.ESCALATION_PATTERNS["fraud"] if p not in CURRENT]
    original = signals._COMPILED["fraud"]
    signals._COMPILED["fraud"] = [re.compile(p) for p in [*kept, *not_me]]
    try:
        yield
    finally:
        signals._COMPILED["fraud"] = original


def fires(text: str, not_me: list[str]) -> bool:
    with lexicon(not_me):
        return signals.contains_escalation_signal(text)


def sha256_lf(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_set() -> list[dict]:
    with SET.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        reading = intent_guard.read(r["utterance"])
        r["p_escalation"], r["tau"] = reading.p_escalation, reading.threshold
        r["current"], r["candidate"] = fires(r["utterance"], CURRENT), fires(r["utterance"], CANDIDATE)
        r["classifier"] = reading.escalate
    return rows


def score_set(rows: list[dict]) -> dict:
    pos, neg = [r for r in rows if r["label"] == "disavows"], [r for r in rows if r["label"] == "innocent"]
    out: dict = {"n_positive": len(pos), "n_innocent": len(neg)}
    for name, flag in (("current", lambda r: r["current"]), ("candidate", lambda r: r["candidate"])):
        out[name] = {"lexicon_recall": rate(sum(flag(r) for r in pos), len(pos)),
                     "lexicon_false_escalation": rate(sum(flag(r) for r in neg), len(neg)),
                     "guard_recall": rate(sum(flag(r) or r["classifier"] for r in pos), len(pos)),
                     "guard_false_escalation": rate(sum(flag(r) or r["classifier"] for r in neg), len(neg))}
    out["lost_positives"] = [{"id": r["id"], "utterance": r["utterance"], "p_escalation": round(r["p_escalation"], 4), "kept_by_classifier": r["classifier"]}
                             for r in pos if r["current"] and not r["candidate"]]
    out["remaining_innocent"] = [{"id": r["id"], "utterance": r["utterance"], "p_escalation": round(r["p_escalation"], 4), "kept_by_classifier": r["classifier"]}
                                 for r in neg if r["candidate"]]
    out["classifier_alone_on_innocent"] = sum(r["classifier"] for r in neg)
    out["flagged_by_candidate_but_not_current"] = [r["id"] for r in rows if r["candidate"] and not r["current"]]
    return out


def existing_sets() -> dict:
    """How many messages of each existing set change: counts only, and by label where the set has one."""
    from eval.evaluate_intent_classifier import HELDOUT, TRACE_HELDOUT, TRAIN, dev_test_split
    from eval.real_speech import load as load_minds

    def read(path):
        return list(csv.DictReader(open(path, encoding="utf-8")))

    held = read(HELDOUT)
    dev, test = dev_test_split(held)
    sets = {"training templates": [(r["utterance"], r["intent"]) for r in read(TRAIN)],
            "held-out dev": [(r["utterance"], r["intent"]) for r in dev], "held-out test": [(r["utterance"], r["intent"]) for r in test],
            "trace requests": [(r["utterance"], None) for r in read(TRACE_HELDOUT)],
            "MInDS-14 transcripts": [(r["transcription"], None) for r in load_minds()]}
    out = {}
    for name, items in sets.items():
        cur = [fires(t, CURRENT) for t, _ in items]
        cand = [fires(t, CANDIDATE) for t, _ in items]
        out[name] = {"n": len(items), "current_flagged": sum(cur), "candidate_flagged": sum(cand),
                     "lost_required_escalations": sum(c and not d and lab == ESC for c, d, (_, lab) in zip(cur, cand, items)),
                     "lost_other": sum(c and not d and lab != ESC for c, d, (_, lab) in zip(cur, cand, items)),
                     "gained": sum(d and not c for c, d in zip(cur, cand))}
    return out


def criteria(scored: dict, existing: dict, known: dict) -> dict:
    lost_at_guard = [p for p in scored["lost_positives"] if not p["kept_by_classifier"]]
    cur, cand = scored["current"], scored["candidate"]
    return {
        "C1a no positive lost at the guard": {"pass": not lost_at_guard, "detail": f"{len(lost_at_guard)} lost"},
        "C1b no required escalation lost in the existing sets": {"pass": all(v["lost_required_escalations"] == 0 for v in existing.values()),
                                                                 "detail": {k: v["lost_required_escalations"] for k, v in existing.items()}},
        "C1c the four known positives still escalate": {"pass": known["positives_kept"] == len(KNOWN_POSITIVE), "detail": f"{known['positives_kept']}/{len(KNOWN_POSITIVE)}"},
        "C2 fewer false positives": {"pass": cand["lexicon_false_escalation"]["successes"] < cur["lexicon_false_escalation"]["successes"]
                                     and cand["guard_false_escalation"]["successes"] < cur["guard_false_escalation"]["successes"],
                                     "detail": f"lexicon {cur['lexicon_false_escalation']['successes']} -> {cand['lexicon_false_escalation']['successes']}, "
                                               f"guard {cur['guard_false_escalation']['successes']} -> {cand['guard_false_escalation']['successes']} of {scored['n_innocent']}"},
        "C2 the four known innocents no longer escalate": {"pass": known["innocents_cleared"] == len(KNOWN_INNOCENT), "detail": f"{known['innocents_cleared']}/{len(KNOWN_INNOCENT)}"},
        "C3 nothing is flagged that was not": {"pass": not scored["flagged_by_candidate_but_not_current"] and all(v["gained"] == 0 for v in existing.values()),
                                               "detail": "candidate is a subset of the current entries"},
    }


def run() -> dict:
    assert sha256_lf(SET) == SET_SHA256, "the preregistered set changed"
    rows = load_set()
    scored = score_set(rows)
    existing = existing_sets()
    known = {"innocents_cleared": sum(not fires(t, CANDIDATE) for t in KNOWN_INNOCENT),
             "innocents_current": sum(fires(t, CURRENT) for t in KNOWN_INNOCENT),
             "positives_kept": sum(fires(t, CANDIDATE) for t in KNOWN_POSITIVE),
             "p_escalation_of_known_innocents": [round(intent_guard.read(t).p_escalation, 4) for t in KNOWN_INNOCENT],
             "threshold": intent_guard.read("hola").threshold}
    verdict = criteria(scored, existing, known)
    return {"set": str(SET), "set_sha256": SET_SHA256, "candidate_patterns": CANDIDATE, "scored": scored, "existing_sets": existing,
            "known": known, "criteria": verdict, "all_criteria_met": all(c["pass"] for c in verdict.values())}


def render(report: dict) -> str:
    s, cur, cand = report["scored"], report["scored"]["current"], report["scored"]["candidate"]
    lines = ["# Scoping the \"no fui yo\" pattern: result", "",
             "Generated by `python -m eval.not_me_experiment`. The rule, the sentences and the criteria are in "
             "`docs/preregistration.md`, section 1c, and were committed before this was computed. The model, tau "
             f"({report['known']['threshold']}) and every other lexicon pattern are unchanged.", "",
             f"Set `{report['set']}` (sha256 `{report['set_sha256'][:16]}...`): {s['n_positive']} sentences that disavow a movement, "
             f"{s['n_innocent']} innocent ones, ES and PT, scored once.", "",
             "| | Lexicon today | Candidate |", "|---|---|---|",
             f"| Recall on disavowals, lexicon | {fmt(cur['lexicon_recall'])} | {fmt(cand['lexicon_recall'])} |",
             f"| Recall on disavowals, guard (lexicon or classifier) | {fmt(cur['guard_recall'])} | {fmt(cand['guard_recall'])} |",
             f"| False escalations on innocent, lexicon | {fmt(cur['lexicon_false_escalation'])} | {fmt(cand['lexicon_false_escalation'])} |",
             f"| False escalations on innocent, guard | {fmt(cur['guard_false_escalation'])} | {fmt(cand['guard_false_escalation'])} |", "",
             f"The classifier alone escalates {s['classifier_alone_on_innocent']} of the {s['n_innocent']} innocent sentences "
             f"(tau {report['known']['threshold']}).", "",
             f"The four innocent sentences of PR #16: the lexicon escalates {report['known']['innocents_current']} today "
             f"(classifier P(escalation) {report['known']['p_escalation_of_known_innocents']}); the candidate clears "
             f"{report['known']['innocents_cleared']}. The four known positives still escalate: {report['known']['positives_kept']}/4.", "",
             "## Disavowals the candidate stops matching", ""]
    lines += [f"- `{p['id']}` P={p['p_escalation']}, {'still flagged by the classifier' if p['kept_by_classifier'] else '**no longer flagged**'}: {p['utterance']}"
              for p in s["lost_positives"]] or ["None."]
    lines += ["", "A positive kept only by the classifier reaches a person as `classifier_escalation` (priority Medium) and no longer as fraud (Critical).",
              "", "## Innocent sentences still escalated by the candidate", ""]
    lines += [f"- `{p['id']}` P={p['p_escalation']}: {p['utterance']}" for p in s["remaining_innocent"]] or ["None."]
    lines += ["", "## Existing sets (counts only)", "", "| Set | n | Flagged today | Flagged by candidate | Required escalations lost | Other lost | Gained |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {k} | {v['n']} | {v['current_flagged']} | {v['candidate_flagged']} | {v['lost_required_escalations']} | {v['lost_other']} | {v['gained']} |"
              for k, v in report["existing_sets"].items()]
    lines += ["", "## Criteria", "", "| Criterion | Result | Detail |", "|---|---|---|"]
    lines += [f"| {k} | {'PASS' if v['pass'] else 'FAIL'} | {v['detail']} |" for k, v in report["criteria"].items()]
    lines += ["", "C1c also needs the system evaluation (`make eval eval-adversarial eval-failures`): 0 unsafe and the same outcome on "
              "every required escalation. It is checked when the rule is applied.", "",
              f"**All measured criteria met: {report['all_criteria_met']}.**", ""]
    return "\n".join(lines)


def main() -> int:
    report = run()
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_MD.write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0 if report["all_criteria_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
