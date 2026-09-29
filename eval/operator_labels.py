"""Las decisiones del operador como etiquetas: cierran el bucle entre el humano y la política.

Cuando el asistente deriva un rastreo a una persona (agent/policy/desk.py), la decisión de esa persona es la mejor
etiqueta que tenemos sobre si la regla de revisión estaba bien puesta:

- **aprobó** -> la revisión no hacía falta; el asistente podría haber abierto la traza solo (revisión innecesaria).
- **rechazó** -> la regla acertó: era un movimiento que no había que rastrear.
- **stale / devolvió** -> no juzgan la regla (el movimiento se liquidó, o la persona lo pasó al asistente).

`python -m eval.operator_labels` exporta las decisiones a JSONL y muestra, para varios umbrales de antigüedad, cuántas
revisiones se habrían evitado y cuántos rechazos se habrían dejado pasar solos. No cambia ningún umbral por su cuenta:
un umbral se decide con estos números y una persona, y con pocas etiquetas el resultado es solo una pista.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.policy.desk import TERMINAL, default_desk
from agent.policy.escalation import default_queue

THRESHOLDS = (30, 60, 90, 180, 365)
JUDGED = ("approved", "rejected")  # the two outcomes that say whether the review was needed


def collect() -> list[dict]:
    """One row per ticket that carried an action and was decided by a person."""
    if not default_queue.path.exists():
        return []
    rows = []
    for line in default_queue.path.read_text(encoding="utf-8").splitlines():
        ticket = json.loads(line) if line.strip() else {}
        action = ticket.get("pending_action")
        if not action:
            continue
        state = default_desk.state(ticket["ticket_id"])
        if state["status"] not in TERMINAL:
            continue
        movement = action.get("movement") or {}
        last = state["history"][-1]
        rows.append({
            "ticket_id": ticket["ticket_id"], "review_reason": action.get("review_reason"), "age_days": action.get("age_days"),
            "transaction_type": movement.get("transaction_type"), "amount": movement.get("amount"),
            "currency": movement.get("currency"), "decision": state["status"],
            "operator_note": last["detail"].get("reason") or None,
            "seconds_to_decide": round(last["ts"] - ticket["created_at"], 1),
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    judged = [r for r in rows if r["decision"] in JUDGED]
    by_reason: dict[str, dict] = {}
    for r in judged:
        c = by_reason.setdefault(r["review_reason"] or "unknown", {"approved": 0, "rejected": 0})
        c[r["decision"]] += 1
    aged = [r for r in judged if r["review_reason"] == "older_than_review_threshold" and r["age_days"] is not None]
    sweep = []
    for t in THRESHOLDS:
        below, above = [r for r in aged if r["age_days"] <= t], [r for r in aged if r["age_days"] > t]
        sweep.append({"threshold_days": t,
                      "reviews_avoided": len(below),  # would open on the customer's yes, with no person
                      "rejects_that_would_slip_through": sum(r["decision"] == "rejected" for r in below),
                      "reviews_still_needed": len(above),
                      "of_which_operator_approved": sum(r["decision"] == "approved" for r in above)})
    approved = sum(r["decision"] == "approved" for r in judged)
    return {"decided": len(rows), "judged": len(judged), "unnecessary_review_rate": round(approved / len(judged), 3) if judged else None,
            "by_review_reason": by_reason, "age_threshold_sweep": sweep,
            "note": "with few labels this is a hint, not a result: report the count next to every rate"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="eval/reports/operator_labels.jsonl")
    args = ap.parse_args()
    rows = collect()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps(summarize(rows), indent=2, ensure_ascii=False))
    print(f"{len(rows)} decisiones exportadas a {args.out}")


if __name__ == "__main__":
    main()
