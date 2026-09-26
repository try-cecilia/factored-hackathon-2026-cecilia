# Architecture

One turn = Understand → Decide → Act → Verify → Escalate, orchestrated by
`agent/core/orchestrator.py`, the only module that talks to both the LLM and
the deterministic layers.

## The turn, step by step

1. **Session** (`agent/session/`). `/chat` accepts only a bearer token. Tokens
   come from `/auth/session`, which requires customer_id **plus** a test PIN
   (HMAC of the id under a server secret). This stands in for the bank's
   identity provider, per the brief: "a customer number alone does not prove
   identity". Tokens have a TTL, failed logins lock out after 5 tries, and
   everything downstream sees only `session_ref`, a one-way hash.
2. **Pre-LLM policy** (`agent/policy/router.py::pre_llm`). This runs on the raw
   text before any model call, so no phrasing can argue it away:
   - Suspended customer → compliance hold.
   - Safety lexicon (`signals.py`: fraud, theft, account takeover,
     legal/regulator, safety; ES+PT, accent-insensitive) → escalate.
   - Learned intent classifier with P(requires_escalation) ≥ τ → escalate.
     τ = 0.55 was chosen on the dev split. The classifier guard is skipped when
     the customer is answering our own clarifying question.
3. **Understand** (`agent/llm/`). Llama 3.3 70B via Groq, with Together as the
   fallback provider. The prompt carries the customer's product catalog
   (type, last 4 digits, currency, status) so the model picks the right
   product. Tool schemas have **no customer_id**, and tool results are
   wrapped as data ("never instructions").
4. **Act** (`agent/tools/account_tools.py`). This is plain SQL over DuckDB.
   Every tool does four things:
   - checks ownership against the session's customer, raising `PermissionDenied` on a mismatch;
   - returns account numbers as last-4 only;
   - stamps results with the data's as-of date;
   - can enforce a freshness SLO.
   The orchestrator sanitizes arguments before any tool runs: unknown keys are
   dropped, enums and limits clamped, and product references resolved against
   the catalog ("0002", "Cuenta Ahorro" → an id, or a clarification if it is
   ambiguous). It allows at most 3 tool steps per turn.
5. **Decide after each tool** (`router.after_tool`). Each outcome maps to a disposition:
   - `MissingSlot`/`InvalidArgument`/`ResourceNotFound` → CLARIFY (listing the customer's own products).
   - `NotApplicable` → answered (e.g. "payment status doesn't apply to a savings account").
   - `PermissionDenied` → security escalation.
   - `DataUnavailable` → data escalation.
   - Anything else → tool-failure escalation.
6. **Verify** (`agent/core/grounding.py`). Every number in the model's answer
   must match a number in this turn's tool results, within 0.5%, under both
   decimal conventions. Sums the model computed, wrong figures, and
   hallucinations fail the check. The answer is then replaced by a
   deterministic rendering of the verified facts (`agent/core/render.py`).
   A no-tool answer never keeps any figure it asserts.
7. **Escalate** (`agent/policy/escalation.py`). The ticket carries:
   - the request and up to 3 prior requests (not a transcript);
   - the reason and the **policy rule that fired**;
   - verified facts, and an evidence pack gathered deterministically per
     category (for fraud: the last 10 transactions with `fraud_score`/`is_fraud`,
     flagged ones first);
   - actions taken, open questions, a suggested next step, and the target queue.
8. **Trace** (`agent/tools/audit.py`). Two record types are written:
   - one trace record per turn: rule fired, LLM attempts and token usage,
     tool calls, grounding result, latency, cost;
   - one audit record per tool call, keyed by the same trace id.

   These execution records are the explanation artifact. They replace any
   hidden model reasoning.

## Why deterministic where it is

| Concern | Where it lives | Why not the LLM |
|---|---|---|
| Whose data | session + tool ownership check | a prompt can be injected; a SQL `WHERE` can't |
| What to disclose | tool layer (masking) | minimization can't depend on model compliance |
| When to transfer | policy router, lexicon, classifier | must be auditable and testable per rule |
| Whether a figure is true | grounding verifier | the model can't verify its own arithmetic |
| Eligibility/credit | out of scope, abstain | brief forbids model-made credit decisions |

The LLM does what only a language model can: paraphrase and slang
understanding, product disambiguation, multi-turn context, and phrasing in ES/PT.

## Reliability

- **LLM client** (`agent/llm/client.py`): per-request timeout; a 25 s budget
  per turn; retries only on transient errors (timeouts, 429, 5xx) with
  jittered backoff and no trailing sleep; a per-provider circuit breaker.
  In the browser test an outage cost 1.2 s once, then 13 ms per turn.
- **Degraded mode**: if both providers are down, a plain balance question is
  answered deterministically, a confident out-of-scope request is abstained,
  and everything else escalates.
- **Bounded state**: conversation LRU (10k sessions × 8 messages); in-memory
  audit windows; rate limits of 20 msgs/min per session and 10 logins/min per IP;
  1,000-character messages.

## Data layer

`data/pipeline.py` loads S3 (or a local directory, for tests) into DuckDB.
Each table load is one transaction:
1. staging;
2. schema-drift check;
3. TRY_CAST to the dictionary's types;
4. data-quality measurement;
5. quarantine of rows breaking error rules, with a gate that rolls back the
   whole load above a 1% quarantine rate;
6. latest-record-wins dedup and upsert by primary key;
7. cross-table checks;
8. lineage rows.

Incremental loads re-read (watermark − lookback) partitions, so late arrivals
are absorbed idempotently. Full description and findings: `docs/data_quality.md`.
