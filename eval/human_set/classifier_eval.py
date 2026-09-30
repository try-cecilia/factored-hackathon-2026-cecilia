"""El clasificador congelado, puntuado sobre mensajes escritos por personas ajenas al equipo.

Tres pasos (docs/human_set.md define el esquema de etiquetas y la regla de que estos resultados no se usan para ajustar):

    python -m eval.human_set.classifier_eval sheet                 # hoja para etiquetar, sin salidas del sistema
    python -m eval.human_set.classifier_eval page --labeler NOMBRE [--labeler ...] [--only-disagreements]   # una página por persona (labeling.py)
    python -m eval.human_set.classifier_eval agreement A.csv B.csv [--third C.csv]   # kappa y etiquetas finales
    python -m eval.human_set.classifier_eval score                 # el clasificador y la línea base sobre lo etiquetado

Reglas que la herramienta hace cumplir, no solo documenta:

- **Congelado.** Se niega a puntuar si el entrenamiento cambió respecto del modelo guardado (los hashes del metadato no
  coinciden): un resultado sobre un modelo que ya vio estos mensajes no vale nada. El reporte deja los hashes.
- **Sin ajuste.** Los fallos de la guarda se listan y no se corrigen aquí. Un hueco del léxico se prueba en mensajes
  nuevos, no en estos.
- **Piso.** Con menos de 60 mensajes o de 8 personas el reporte dice "NOT A RESULT" y no presenta cifras como resultado.
- **Etiquetas.** Solo cuentan los mensajes que dos personas etiquetaron `matches`. El kappa se calcula antes de resolver
  desacuerdos, y un desacuerdo sin tercera opinión queda fuera y contado.
- **Fuga.** Se mide cuántos mensajes son casi idénticos a frases de entrenamiento o del held-out. No se excluyen (son
  coincidencias legítimas de quien escribe), pero se declaran.

Con pocos mensajes, cualquier tasa por clase tiene un intervalo ancho: es una pista con su incertidumbre, no una cifra firme.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import joblib

from agent.llm import baseline_classifier
from agent.llm.intent_classifier import load_rows
from agent.policy import intent_guard
from agent.policy.signals import contains_escalation_signal, escalation_categories
from eval import leakage
from eval.human_set import labeling
from eval.stats import fmt, rate

RAW = Path("eval/workload/human_raw.jsonl")
SHEET = Path("eval/workload/human_labeling_sheet.csv")
FINAL = Path("eval/workload/human_labels_final.csv")
AGREEMENT = Path("eval/reports/human_set_agreement.json")
REPORT_JSON = Path("eval/reports/human_set_classifier.json")
REPORT_MD = Path("eval/reports/human_set_classifier.md")
MODEL = Path("eval/models/intent_clf.joblib")
META = Path("eval/models/intent_clf_meta.json")
TRAIN = "eval/test_cases/intent_dataset.csv"
HELDOUT = "eval/test_cases/heldout_utterances.csv"

LABELS = ("matches", "ambiguous", "something_else")
FLOOR_MESSAGES, FLOOR_PEOPLE = 60, 8
ESC = "requires_escalation"
# What each situation of the form asks for, as an intent of the classifier. `trace` is not a class (ADR-002): what is
# measured for it is whether the pre-LLM guard hands it to a person. `ambiguous_type` and `family_account` are balance
# questions whose right *outcome* is not a plain answer; that is judged by the system evaluation, not here.
SITUATION_INTENT = {
    "balance_all": "balance_inquiry", "balance_specific": "balance_inquiry", "ambiguous_type": "balance_inquiry",
    "family_account": "balance_inquiry", "transactions": "transaction_lookup", "payment_ok": "payment_status",
    "fx": "exchange_rate_inquiry", "fraud": ESC, "out_of_scope": "out_of_scope", "trace": None,
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# --- 1. the sheet ------------------------------------------------------------------------------------------------

def read_messages(raw: Path) -> tuple[list[dict], dict]:
    """One row per message written by someone who had not seen the system, and how many people were left out."""
    messages, left_out, people = [], 0, set()
    for line in raw.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sub = json.loads(line)
        if sub.get("saw_system"):
            left_out += 1
            continue
        people.add(sub["id"])
        for situation, text in sub["answers"].items():
            if not str(text).strip():  # the form stores only what was written; a blank answer is not a message
                continue
            messages.append({"message_id": f"{sub['id']}:{situation}", "situation": situation, "language": sub["lang"],
                             "country": sub.get("country"), "message": text, "person": sub["id"]})
    return messages, {"submissions": len(people), "left_out_saw_system": left_out}


def write_sheet(messages: list[dict], out: Path, seed: int = 7) -> None:
    """The order is shuffled with a fixed seed, and nothing the system said is on the sheet."""
    rows = list(messages)
    random.Random(seed).shuffle(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["message_id", "situation", "language", "message", "label"])
        w.writerows([[m["message_id"], m["situation"], m["language"], m["message"], ""] for m in rows])


# --- 2. agreement -----------------------------------------------------------------------------------------------

def read_labels(path: Path) -> dict[str, str]:
    labels = {}
    for row in csv.DictReader(open(path, newline="", encoding="utf-8")):
        label = (row.get("label") or "").strip()
        if label not in LABELS:
            raise ValueError(f"{path}: label {label!r} for {row.get('message_id')} is not one of {LABELS}")
        labels[row["message_id"]] = label
    return labels


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Agreement beyond chance. None when it is undefined because both people used one single label."""
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(k) / n) * (b.count(k) / n) for k in set(a) | set(b))
    return None if pe == 1 else round((po - pe) / (1 - pe), 4)


def agreement(a: dict[str, str], b: dict[str, str], third: dict[str, str] | None = None, texts: dict[str, str] | None = None) -> dict:
    """The kappa of the first two people, before any disagreement is resolved, and the final labels."""
    if set(a) != set(b):
        raise ValueError(f"the two sheets do not label the same messages ({len(set(a) ^ set(b))} ids differ)")
    ids = sorted(a)
    kappa = cohen_kappa([a[i] for i in ids], [b[i] for i in ids])
    final, disagreements = {}, []
    for i in ids:
        if a[i] == b[i]:
            final[i] = (a[i], "agreed")
            continue
        disagreements.append({"message_id": i, "message": (texts or {}).get(i), "a": a[i], "b": b[i], "third": (third or {}).get(i)})
        final[i] = ((third[i], "resolved") if third and i in third else (None, "unresolved"))
    matrix = Counter((a[i], b[i]) for i in ids)
    return {"n": len(ids), "kappa": kappa, "percent_agreement": round(sum(a[i] == b[i] for i in ids) / len(ids), 4),
            "confusion": {f"{x}|{y}": matrix.get((x, y), 0) for x in LABELS for y in LABELS},
            "disagreements": disagreements, "resolved_by_third": sum(s == "resolved" for _, s in final.values()),
            "unresolved": sum(s == "unresolved" for _, s in final.values()), "final": final,
            "note": "kappa is computed on the first two people before any disagreement is settled"}


def read_final(path: Path) -> dict[str, tuple[str | None, str]]:
    """message_id -> (final label, or None when unresolved; status), as write_final wrote them."""
    with open(path, newline="", encoding="utf-8") as f:
        return {r["message_id"]: (r["label_final"] or None, r["status"]) for r in csv.DictReader(f)}


def write_final(rep: dict, out: Path, report_path: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["message_id", "label_final", "status"])
        w.writerows([[i, label or "", status] for i, (label, status) in sorted(rep["final"].items())])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({k: v for k, v in rep.items() if k != "final"}, indent=2, ensure_ascii=False), encoding="utf-8")


# --- 3. score the frozen classifier -----------------------------------------------------------------------------

def frozen_evidence(model_path: Path = MODEL, meta_path: Path = META, train: str = TRAIN, heldout: str = HELDOUT) -> dict:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    train_sha = _sha(Path(train).read_text(encoding="utf-8"))
    if meta.get("train_sha256") != train_sha:
        raise RuntimeError("the training data changed after this model was trained: retrain and re-evaluate before "
                           "scoring on the human set (a model that saw these messages proves nothing)")
    return {"train_sha256": train_sha, "heldout_sha256": _sha(Path(heldout).read_text(encoding="utf-8")),
            "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(), "variant": meta["variant"],
            "escalation_threshold": meta["escalation_threshold"]}


def score(messages: list[dict], final: dict[str, tuple[str | None, str]], counts: dict, agreement_report: dict,
          model_path: Path = MODEL, meta_path: Path = META, train: str = TRAIN, heldout: str = HELDOUT) -> dict:
    evidence = frozen_evidence(model_path, meta_path, train, heldout)
    # joblib deserializes with pickle: safe here because this is our own committed model, which frozen_evidence has just
    # matched by hash against the training data it was built from. Never point model_path at a file from anywhere else.
    model, tau = joblib.load(model_path), evidence["escalation_threshold"]
    kept = [m for m in messages if final.get(m["message_id"], (None, ""))[0] == "matches"]
    dropped = Counter(final.get(m["message_id"], (None, "unlabeled"))[0] or final.get(m["message_id"], (None, "unlabeled"))[1]
                      for m in messages if m not in kept)
    people = len({m["person"] for m in kept})
    below = len(kept) < FLOOR_MESSAGES or people < FLOOR_PEOPLE

    scored = [m for m in kept if SITUATION_INTENT.get(m["situation"])]
    gold = [SITUATION_INTENT[m["situation"]] for m in scored]
    texts = [m["message"] for m in scored]
    base = [baseline_classifier.classify(t) for t in texts]
    learned = list(model.predict(texts)) if texts else []
    esc_idx = list(model.classes_).index(ESC)
    probs = model.predict_proba(texts) if texts else []
    flags = [contains_escalation_signal(t) or p[esc_idx] >= tau for t, p in zip(texts, probs)]

    per_class = {}
    for intent in sorted(set(gold)):
        idx = [i for i, g in enumerate(gold) if g == intent]
        per_class[intent] = {"n": len(idx), "baseline_recall": rate(sum(base[i] == intent for i in idx), len(idx)),
                             "learned_recall": rate(sum(learned[i] == intent for i in idx), len(idx))}
    by_language = {}
    for lang in sorted({m["language"] for m in scored}):
        idx = [i for i, m in enumerate(scored) if m["language"] == lang]
        by_language[lang] = {"baseline": rate(sum(base[i] == gold[i] for i in idx), len(idx)),
                             "learned": rate(sum(learned[i] == gold[i] for i in idx), len(idx))}
    pos = [i for i, g in enumerate(gold) if g == ESC]
    neg = [i for i, g in enumerate(gold) if g != ESC]
    trace_texts = [m["message"] for m in kept if m["situation"] == "trace"]
    handed = [t for t in trace_texts if escalation_categories(t) or intent_guard.read(t).escalate]
    lk = leakage.report([r["utterance"] for r in load_rows(train)] + [r["utterance"] for r in load_rows(heldout)],
                        [m["message"] for m in kept]) if kept else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "NOT A RESULT: below the floor" if below else "reported",
        "floor": {"messages": FLOOR_MESSAGES, "people": FLOOR_PEOPLE, "have_messages": len(kept), "have_people": people, "below_floor": below},
        "counts": {**counts, "messages_written": len(messages), "labeled_matches": len(kept), "dropped": dict(dropped)},
        "frozen": evidence,
        "agreement": {k: agreement_report[k] for k in ("n", "kappa", "percent_agreement", "resolved_by_third", "unresolved")},
        "overall": {"baseline_accuracy": rate(sum(b == g for b, g in zip(base, gold)), len(gold)),
                    "learned_accuracy": rate(sum(l == g for l, g in zip(learned, gold)), len(gold))},
        "per_class": per_class, "by_language": by_language,
        "guard": {"fraud_recall": rate(sum(flags[i] for i in pos), len(pos)), "false_escalation": rate(sum(flags[i] for i in neg), len(neg)),
                  "missed": [texts[i] for i in pos if not flags[i]]},
        "trace_requests": {"n": len(trace_texts), "handed_to_a_person": rate(len(handed), len(trace_texts)), "utterances": handed},
        "leakage": None if lk is None else {"n": lk["n"], "max_similarity": lk["max"],
                                            "near_identical_to_training": len(lk["excluded"]), "similar_60_or_more": len(lk["review"])},
        "not_used_for_tuning": "these results never change the classifier, the lexicon, the prompt or the rules; a gap is tried on new messages",
    }


def dump(rep: dict) -> str:
    """The report as JSON. The model returns NumPy integers, which the json module does not know."""
    return json.dumps(rep, indent=2, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))


def to_markdown(r: dict) -> str:
    f, c, a = r["floor"], r["counts"], r["agreement"]
    head = (f"# Human-written messages: the frozen intent classifier ({r['verdict']})\n\n"
            f"Generated by `python -m eval.human_set.classifier_eval score` at {r['generated_at']}. Intervals are Wilson 95%.\n\n")
    if f["below_floor"]:
        head += (f"> **NOT A RESULT.** {f['have_messages']} labeled messages from {f['have_people']} people; the floor is "
                 f"{f['messages']} from {f['people']}. The figures below are shown only so the pipeline can be checked, and must not be quoted.\n\n")
    classes = "\n".join(f"| {k} | {v['n']} | {fmt(v['baseline_recall'])} | {fmt(v['learned_recall'])} |" for k, v in r["per_class"].items())
    langs = "\n".join(f"| {k} | {fmt(v['baseline'])} | {fmt(v['learned'])} |" for k, v in r["by_language"].items())
    lk = r["leakage"]
    return head + f"""- Messages written: {c['messages_written']} ({c['submissions']} people; {c['left_out_saw_system']} left out for having seen the system). Labeled `matches` by two people: {c['labeled_matches']}. Dropped: {c['dropped'] or 'none'}.
- Label agreement of the first two people, before settling any disagreement: kappa **{a['kappa']}**, {100 * a['percent_agreement']:.1f}% agreement over {a['n']} messages; {a['resolved_by_third']} settled by a third person, {a['unresolved']} unresolved (left out).
- Frozen before scoring: variant `{r['frozen']['variant']}`, τ = {r['frozen']['escalation_threshold']}, train `{r['frozen']['train_sha256'][:12]}`, held-out `{r['frozen']['heldout_sha256'][:12]}`, model `{r['frozen']['model_sha256'][:12]}`.

## Accuracy
| | Keyword baseline | Learned |
|---|---|---|
| Overall | {fmt(r['overall']['baseline_accuracy'])} | {fmt(r['overall']['learned_accuracy'])} |

| Class | n | Baseline recall | Learned recall |
|---|---|---|---|
{classes}

| Language | Baseline | Learned |
|---|---|---|
{langs}

## Escalation guard (lexicon or classifier, what runs before the LLM)
Fraud recall {fmt(r['guard']['fraud_recall'])}; false escalations on the other situations {fmt(r['guard']['false_escalation'])}. Missed, reported and **not** added to the lexicon: {', '.join(repr(u) for u in r['guard']['missed']) or 'none'}.

## Trace requests (not a class of the classifier)
{fmt(r['trace_requests']['handed_to_a_person'])} handed to a person by the guard: {', '.join(repr(u) for u in r['trace_requests']['utterances']) or 'none'}. Handing one over is safe but not self-served.

## Leakage
{'No labeled messages.' if lk is None else f"{lk['near_identical_to_training']} of {lk['n']} messages are near-identical to a training or held-out phrase (kept: it is what people write); {lk['similar_60_or_more']} more are 0.6 or more similar. Highest similarity {lk['max_similarity']}."}

{r['not_used_for_tuning']}.
"""


# --- command line -------------------------------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sheet")
    pg = sub.add_parser("page", help=f"one labeling page per person, from the sheet -> {SHEET.parent}/human_labeling_<name>.html")
    pg.add_argument("--labeler", action="append", required=True, help="once per person")
    pg.add_argument("--only-disagreements", action="store_true", help=f"the third person's page: the disagreements in {AGREEMENT}")
    ag = sub.add_parser("agreement")
    ag.add_argument("a")
    ag.add_argument("b")
    ag.add_argument("--third")
    sub.add_parser("score")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.cmd == "page":  # needs the sheet only, not the answers
        only = ({d["message_id"] for d in json.loads(AGREEMENT.read_text(encoding="utf-8"))["disagreements"]}
                if args.only_disagreements else None)
        for path in labeling.write_pages(args.labeler, SHEET, only):
            print(f"{path}: send it to that person only")
        return
    messages, counts = read_messages(RAW)
    if args.cmd == "sheet":
        write_sheet(messages, SHEET)
        print(f"{len(messages)} messages from {counts['submissions']} people -> {SHEET} ({counts['left_out_saw_system']} people left out)")
    elif args.cmd == "agreement":
        rep = agreement(read_labels(Path(args.a)), read_labels(Path(args.b)), read_labels(Path(args.third)) if args.third else None,
                        {m["message_id"]: m["message"] for m in messages})
        write_final(rep, FINAL, AGREEMENT)
        print(f"kappa {rep['kappa']} | agreement {100 * rep['percent_agreement']:.1f}% of {rep['n']} | {len(rep['disagreements'])} disagreements "
              f"({rep['resolved_by_third']} settled, {rep['unresolved']} unresolved) -> {FINAL}")
    else:
        rep = score(messages, read_final(FINAL), counts, json.loads(AGREEMENT.read_text(encoding="utf-8")))
        REPORT_JSON.write_text(dump(rep), encoding="utf-8")
        REPORT_MD.write_text(to_markdown(rep), encoding="utf-8")
        print(REPORT_MD.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
