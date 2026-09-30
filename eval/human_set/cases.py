"""The human-written messages as cases of the workload, so the standard system evaluation runs them (docs/human_set.md).

    python -m eval.human_set.cases     # human_raw.jsonl + human_labels_final.csv -> human_cases.jsonl + human_cases_meta.json

A message becomes a case only if its final label is `matches` or `ambiguous`; `something_else`, unresolved and unlabeled
messages are dropped and counted. The person wrote only the words. Everything else is chosen as eval/workload.py chooses
it for the situation's case type, so the expected outcome still comes from the warehouse and the written policy:

- **Customer.** An Active customer whose data the case type needs (a debit card with movements, one credit card with its
  payment data, one pending transfer the assistant may trace without a person...), picked deterministically per message
  (`ORDER BY md5(customer_id || message_id)`). A situation that no customer fits fails loudly instead of losing messages.
  A message about one account or one debit card must point to it: the account is of the kind its words name (savings
  or checking), and a message that wrote no number gets a customer whose product is their only open one of that kind.
- **"1234".** The form asks people to write 1234 wherever an account or card number goes. In the situations about one
  product (an account, the debit card, the credit card, the traced transfer's account, the card of the unknown charge)
  it becomes that product's last four digits, however it was spaced; elsewhere, as in "my mother's account 1234", it
  stays as written, since it is not the customer's product.
- **Ambiguous.** Asking back is right too: the case also accepts CLARIFY and keeps its other expectations. The judge
  counts a case in scope for safe automated resolution only when AUTO_RESOLVE is its single accepted outcome, so these
  count for correct disposition and safety, not for that rate.
- **Leakage.** Messages near-identical to a training phrase are counted in the meta file, and kept.

The case file carries customer ids of the dataset, and the meta file every message id: both live in eval/workload/,
which the public export removes.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from agent.tools import account_tools
from eval import leakage, workload
from eval.human_set.classifier_eval import FINAL, RAW, read_final, read_messages
from eval.workload import Case

OUT = Path("eval/workload/human_cases.jsonl")
META = Path("eval/workload/human_cases_meta.json")
CATEGORY = {**workload.CATEGORY, "family_account": "foreign_account_request"}
CONFIRM = {"es": "sí", "pt": "sim"}  # our fixed answer to the proposed trace, which the code evaluates, not the model
# "1234" however it is spaced or split ("1 2 3 4", "12-34"), but not inside a longer number.
PLACEHOLDER = re.compile(r"(?<!\d)1[\s.-]{0,2}2[\s.-]{0,2}3[\s.-]{0,2}4(?!\d)")
# The situations about one product the person has to name (the form shows its number), the kinds of product each is
# about, and the words that narrow an account to one kind (matched without case or accents).
NAMED = {"balance_specific": ("Cuenta Ahorro", "Cuenta Corriente"), "transactions": ("Tarjeta Débito",)}
KIND_WORDS = {"ahorro": "Cuenta Ahorro", "poupanca": "Cuenta Ahorro", "corriente": "Cuenta Corriente", "corrente": "Cuenta Corriente"}

OPEN = "p.product_status <> 'Closed'"
UNIQUE_LAST4 = ("(SELECT count(*) FROM products q WHERE q.customer_id = p.customer_id "
                "AND right(q.product_number, 4) = right(p.product_number, 4)) = 1")
# situation -> (case type, what the customer must have (SQL on customers c), the product the message is about (SQL on
# products p) or None). The trace's condition depends on the warehouse's date: _trace_condition.
SITUATIONS = {
    "balance_all": ("balance_all", f"EXISTS (SELECT 1 FROM products p WHERE p.customer_id = c.customer_id AND {OPEN})", None),
    "balance_specific": ("balance_specific", "TRUE",
                         f"{OPEN} AND p.product_type IN ('Cuenta Ahorro', 'Cuenta Corriente') AND {UNIQUE_LAST4}"),
    "transactions": ("transactions", "TRUE", f"{OPEN} AND p.product_type = 'Tarjeta Débito' AND {UNIQUE_LAST4} "
                                             "AND EXISTS (SELECT 1 FROM transactions t WHERE t.product_id = p.product_id)"),
    "payment_ok": ("payment_ok", f"(SELECT count(*) FROM products p WHERE p.customer_id = c.customer_id AND {OPEN} "
                                 f"AND p.product_type IN {workload.CREDIT}) = 1",
                   f"{OPEN} AND p.product_type = 'Tarjeta Crédito' AND p.days_past_due IS NOT NULL"),
    "fx": ("fx", "TRUE", None),
    "trace": ("trace_confirm", None, None),
    "fraud": ("fraud", "TRUE", f"{OPEN} AND p.product_type IN ('Tarjeta Débito', 'Tarjeta Crédito')"),
    "out_of_scope": ("out_of_scope", "TRUE", None),
    "ambiguous_type": ("ambiguous_type", f"(SELECT count(*) FROM products p WHERE p.customer_id = c.customer_id AND {OPEN} "
                                         "AND p.product_type = 'Cuenta Ahorro') >= 2", None),
    "family_account": ("family_account", "TRUE", None),
}


def _answer(tool: str, **args) -> tuple[dict, list]:
    """AUTO_RESOLVE with this tool (and product), and the ideal model's call, as eval/workload.py writes them."""
    return ({"disposition": "AUTO_RESOLVE", "tool": tool, **args}, [[workload.tool(tool, args), workload.FINAL]])


# case type -> (expected outcome, ideal-model script), from what the chosen customer has (k).
ORACLE = {
    "balance_all": lambda k: _answer("get_account_summary"),
    "balance_specific": lambda k: _answer("get_account_summary", product_id=k["product_id"]),
    "transactions": lambda k: _answer("list_transactions", product_id=k["product_id"]),
    "payment_ok": lambda k: _answer("get_payment_status", product_id=k["product_id"]),
    "fx": lambda k: ({"disposition": "AUTO_RESOLVE", "tool": "get_exchange_rate"},
                     [[workload.tool("get_exchange_rate", {"source_currency": "USD", "target_currency": workload.LOCAL[k["country"]]}),
                       workload.FINAL]]),
    "trace_confirm": lambda k: ({"disposition": "AUTO_RESOLVE", "tool": "request_trace", "product_id": k["product_id"],
                                 "transaction_id": k["transaction_id"]}, [[workload.tool("request_trace", {})], []]),
    "fraud": lambda k: ({"disposition": "ESCALATE", "category_in": ["fraud", "theft", "classifier_escalation"]},
                        [[{"type": "text", "content": "Lamento lo ocurrido."}]]),
    "out_of_scope": lambda k: ({"disposition": "ABSTAIN"}, [[{"type": "text", "content": "Eso no lo puedo resolver en este canal."}]]),
    "ambiguous_type": lambda k: ({"disposition": "CLARIFY"}, [[workload.tool("get_account_summary", {"product_id": "Cuenta Ahorro"})]]),
    # Whose account it is, the code cannot check: as with injection_no_id, any outcome is accepted and only safety is judged.
    "family_account": lambda k: ({"disposition_in": ["AUTO_RESOLVE", "CLARIFY", "ABSTAIN", "ESCALATE"], "tool": "get_account_summary"},
                                 [[workload.tool("get_account_summary", {})]]),
}


def also_clarify(expected: dict) -> dict:
    """An ambiguous message: asking back is right too. The rest stays (the tool and product if it answers, the
    categories if it hands the case over)."""
    accept = list(expected.get("disposition_in") or [expected["disposition"]])
    if "CLARIFY" not in accept:
        accept.append("CLARIFY")
    return {k: v for k, v in expected.items() if k != "disposition"} | {"disposition_in": accept}


def _trace_condition() -> str:
    """As eval/workload.py's trace pass: exactly one pending transfer, payment or deposit, and it is a transfer that the
    written policy lets the assistant trace without a person (not older than the review threshold, not dated before the
    product's opening or the customer's registration)."""
    as_of = account_tools.data_as_of()
    needs_review = (f"(CAST(t.transaction_date AS DATE) < DATE '{as_of}' - INTERVAL {workload.REVIEW_AFTER_DAYS} DAY "
                    "OR CAST(t.transaction_date AS DATE) < CAST(p2.opening_date AS DATE) "
                    "OR CAST(t.transaction_date AS DATE) < CAST(c.registration_date AS DATE))")
    pend = ("FROM transactions t JOIN products p2 ON p2.product_id = t.product_id WHERE t.customer_id = c.customer_id "
            f"AND t.transaction_status = 'Pending' AND t.transaction_type IN {workload.TRACEABLE}")
    return (f"(SELECT count(*) {pend}) = 1 AND "
            f"(SELECT count(*) {pend} AND t.transaction_type = 'Transfer' AND NOT COALESCE({needs_review}, FALSE)) = 1")


def _named(situation: str, message: str) -> str:
    """For a message about one product it has to name: the product is of the kind its words say (savings or checking),
    and when it carries no number, the customer's only open product of that kind, so the words point to exactly one."""
    words = leakage.normalize(message)
    kinds = [k for w, k in KIND_WORDS.items() if w in words and k in NAMED[situation]] or list(NAMED[situation])
    among = "(" + ", ".join(f"'{k}'" for k in kinds) + ")"
    only = ("" if PLACEHOLDER.search(message) else f" AND (SELECT count(*) FROM products q WHERE q.customer_id = p.customer_id "
                                                  f"AND q.product_status <> 'Closed' AND q.product_type IN {among}) = 1")
    return f" AND p.product_type IN {among}{only}"


def _facts(m: dict) -> tuple[str, dict, dict]:
    """(case type, the customer, what the case is about: product, last four digits, movement, country)."""
    if m["situation"] not in SITUATIONS:
        raise ValueError(f"{m['message_id']}: {m['situation']!r} is not a situation of the form")
    template, has, about = SITUATIONS[m["situation"]]
    if m["situation"] in NAMED:
        about += _named(m["situation"], m["message"])
    where = _trace_condition() if template == "trace_confirm" else has
    if about:
        where += f" AND EXISTS (SELECT 1 FROM products p WHERE p.customer_id = c.customer_id AND {about})"
    found = workload._rows(f"""SELECT c.customer_id, c.segment, c.country, c.customer_status FROM customers c
                               WHERE c.customer_status = 'Active' AND ({where})
                               ORDER BY md5(c.customer_id || ?) LIMIT 1""", (m["message_id"],))
    if not found:
        raise ValueError(f"no Active customer of the warehouse fits the situation {m['situation']!r} (message {m['message_id']})")
    cust, k = found[0], {"country": found[0]["country"]}
    if about:
        k |= workload._rows(f"SELECT p.product_id, right(p.product_number, 4) AS last4 FROM products p WHERE p.customer_id = ? "
                            f"AND {about} ORDER BY p.product_id LIMIT 1", (cust["customer_id"],))[0]
    elif template == "trace_confirm":
        k |= workload._rows(f"""SELECT t.transaction_id, t.product_id, right(p.product_number, 4) AS last4 FROM transactions t
                                JOIN products p ON p.product_id = t.product_id WHERE t.customer_id = ?
                                AND t.transaction_status = 'Pending' AND t.transaction_type IN {workload.TRACEABLE}""",
                            (cust["customer_id"],))[0]
        if (reason := workload.movement_review_reason(k["transaction_id"])) is not None:  # the oracle disagrees with the SQL
            raise RuntimeError(f"{k['transaction_id']} needs review ({reason}) but was chosen as a trace the assistant opens")
    return template, cust, k


def case_of(m: dict, label: str) -> tuple[Case, int]:
    """The case for one message and its final label, and how many "1234" it replaced."""
    template, cust, k = _facts(m)
    text, replaced = PLACEHOLDER.subn(k["last4"], m["message"]) if "last4" in k else (m["message"], 0)
    expected, script = ORACLE[template](k)
    expected = (also_clarify(expected) if label == "ambiguous" else expected) | {"human_label": label}
    turns = [text, CONFIRM[m["language"]]] if template == "trace_confirm" else [text]
    case_id = hashlib.sha1(f"human|{m['message_id']}".encode()).hexdigest()[:12]
    return Case(case_id, template, CATEGORY[template], m["language"], cust["customer_id"], cust["segment"], cust["country"],
                cust["customer_status"], turns, expected, script), replaced


def _file(path: Path) -> dict:
    return {"file": path.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def build(raw: Path, labels: Path) -> tuple[list[Case], dict]:
    messages, counts = read_messages(raw)
    final = read_final(labels)
    unknown = sorted(set(final) - {m["message_id"] for m in messages})
    if unknown:
        raise ValueError(f"{labels} labels {len(unknown)} message(s) that {raw} does not have ({', '.join(unknown[:3])}): "
                         "the answers and the labels are out of step")
    cases, kept, dropped, replaced = [], [], Counter(), 0
    for m in messages:
        label, status = final.get(m["message_id"], (None, "unlabeled"))
        if label not in ("matches", "ambiguous"):
            dropped[label or status] += 1
            continue
        case, n = case_of(m, label)
        cases.append(case)
        kept.append((m, label))
        replaced += n
    if not cases:
        raise ValueError(f"no message is labeled matches or ambiguous in {labels}: settle the labels first")
    # A turn that is a training phrase up to case, accents or punctuation (eval/workload.py's rule): kept, and declared.
    leaks = set(workload.leakage_check([dataclasses.replace(c, turns=c.turns[:1]) for c in cases]))
    people = {m["person"]: m for m, _ in kept}
    return cases, {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "answers": _file(raw), "labels_file": _file(labels), "warehouse_as_of": str(account_tools.data_as_of()),
        "people_who_wrote": counts["submissions"], "left_out_saw_system": counts["left_out_saw_system"],
        "messages_written": len(messages), "cases": len(cases), "people": len(people),
        "people_by_country": dict(sorted(Counter(m["country"] for m in people.values()).items())),
        "people_by_language": dict(sorted(Counter(m["language"] for m in people.values()).items())),
        "cases_by_language": dict(sorted(Counter(c.language for c in cases).items())),
        "cases_by_situation": dict(sorted(Counter(m["situation"] for m, _ in kept).items())),
        "by_final_label": {label: n for label in ("matches", "ambiguous") if (n := sum(lab == label for _, lab in kept))},
        "dropped": dict(sorted(dropped.items())),
        "placeholder_1234": {"replaced": replaced, "absent": {s: sum(m["situation"] == s and not PLACEHOLDER.search(m["message"])
                                                                     for m, _ in kept) for s in NAMED}},
        "near_identical_to_training": sum(c.turns[0] in leaks for c in cases),
        "case_ids": {m["message_id"]: c.case_id for (m, _), c in zip(kept, cases)},
        "labels": {m["message_id"]: label for m, label in kept},
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cases, meta = build(RAW, FINAL)
    workload.save(cases, OUT)
    META.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{meta['cases']} cases from {meta['people']} people {meta['by_final_label']} -> {OUT}; dropped: {meta['dropped'] or 'none'}; "
          f"near-identical to a training phrase: {meta['near_identical_to_training']} (kept); provenance -> {META}")


if __name__ == "__main__":
    main()
