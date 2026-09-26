# Architecture

## Loop: Understand → Decide → Act → Verify → Escalate

```
Customer utterance (ES/PT)
      │
      ▼
[Session/Auth]  agent/session/auth.py — deterministic, no LLM.
      │           Validates a trusted session token -> customer_id.
      │           Expired/invalid -> REAUTH_REQUIRED, no LLM call made.
      ▼
[Understand]    agent/llm/client.py + agent/llm/prompts.py — Llama 3.1/3.3
      │           via Groq (primary) / Together (fallback), tool-calling.
      │           The LLM NEVER receives or sets customer_id (see prompts.py
      │           docstring) — it only ever proposes a tool name + non-identity args.
      ▼
[Decide]        agent/policy/router.py — plain Python, no LLM.
      │           contains_escalation_signal() runs on raw text BEFORE any
      │           LLM/tool call — a keyword hit short-circuits straight to
      │           ESCALATE. Otherwise: AUTO_RESOLVE / CLARIFY / ABSTAIN /
      │           ESCALATE decided from tool outcome (see below).
      ▼
[Act]           agent/tools/account_tools.py — deterministic functions only.
      │           Every call: (1) enforces product ownership against the
      │           REAL session customer_id, never an LLM-supplied one; (2)
      │           logged via agent/tools/audit.py for full tracing.
      ▼
[Verify]        agent/policy/router.decide_after_tool_call() — re-checks the
      │           tool's outcome. A PermissionDenied/DataUnavailable/
      │           MissingSlot/unexpected-exception always overrides whatever
      │           the LLM intended; only a clean success reaches AUTO_RESOLVE.
      ▼
[Escalate]      agent/policy/escalation.py — builds a structured handoff
                  {request, verified_facts, actions_taken, evidence,
                  open_questions} and writes it to a mock human queue
                  (data/warehouse/human_queue.jsonl) — never a raw transcript.
```

All of this is orchestrated by `agent/core/orchestrator.py`, the only module
that talks to both the LLM and the deterministic layers.

## Why the LLM is never trusted with identity or policy

Two separate mechanisms, both enforced in code:

1. **Tool schemas never include `customer_id`** (`agent/llm/prompts.py`). Even
   if a prompt convinces the model to call a tool, it can only choose
   `product_id`/dates/currencies — never whose account to look up.
2. **Every tool call injects the real session's `customer_id`**
   (`agent/core/orchestrator.py`), and every tool independently re-checks
   ownership against the database (`agent/tools/account_tools.py::
   _assert_owns_product`). A "show me customer X's balance" injection
   attempt still resolves against the *authenticated* customer, and any
   product-id mismatch raises `PermissionDenied` — logged and escalated, not
   silently refused by the model's own judgment.

This is why `eval/run_guardrail_eval.py`'s prompt-injection and
unauthorized-access scenarios pass at 0 unsafe outcomes: the defense doesn't
depend on the model behaving well.

## Data pipeline

`data/pipeline.py` fetches CSVs from S3 (`data/raw/`, boto3 with path-style
addressing — see the module docstring for why: this sandbox's egress gateway
403s virtual-hosted-style S3 requests and DuckDB's httpfs extension download)
and loads them into a DuckDB warehouse file, deduplicated and upserted by
primary key (`data/contracts.py` defines the schema, PKs, NOT NULL columns,
and FK relationships used for the quality-check report). Idempotency is unit
tested by replaying a single day's transactions partition twice
(`tests/test_pipeline.py`).

Only the tables this workflow needs are ingested: `customers`, `products`,
`branches`, `transactions`, `daily_exchange_rates`.

## Learned component

`agent/llm/intent_classifier.py` (TF-IDF char n-grams + Logistic Regression)
vs. `agent/llm/baseline_classifier.py` (keyword rules), benchmarked in
`eval/evaluate_intent_classifier.py` on a template-generated ES/PT utterance
set (`eval/test_cases/build_intent_dataset.py`) split **by template**, not by
row, to prevent near-duplicate leakage between train and test. See
`LIMITATIONS.md` for the honest result (the baseline currently wins on
accuracy at this dataset size — both hit 100% recall on the safety-critical
`requires_escalation` class).

## Evaluation

`eval/run_guardrail_eval.py` runs 13 scenarios (normal, ambiguous/abstain,
human-required escalation, prompt injection, unauthorized access, missing
data, expired/invalid session, simulated tool failure, multilingual) through
the real orchestrator with a scripted LLM stand-in, and reports the rubric
metrics: Safe Automated Resolution rate, Containment, Escalation
recall/false-escalation, Unsafe outcomes (count/denominator), and latency
percentiles — all explicitly labeled as an **offline simulation** (see
README.md's LLM-provider note for why, and `eval/fake_llm.py`'s docstring for
the labeling rule this repo follows throughout).

## Observability

Every tool call is recorded in `data/warehouse/audit_log.jsonl`
(`agent/tools/audit.py`): call id, tool name, args, duration, success/error.
Every escalation is recorded in `data/warehouse/human_queue.jsonl`
(`agent/policy/escalation.py`). Both are exposed read-only via
`GET /admin/audit_log` and `GET /admin/human_queue` for demo/judge visibility.
