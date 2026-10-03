# Architecture

One turn = Understand → Decide → Act → Verify → Escalate, orchestrated by
`agent/core/orchestrator.py`, the only module that talks to both the LLM and
the deterministic layers.

**The model interprets; the code speaks** ([ADR-001](docs/decisions/ADR-001-model-interprets-code-speaks.md)):
one primary model response per turn chooses tools (the client may retry it
or fall back to another provider). The system never gives the model a
customer record (no balance, transaction, internal id, account number, name
or segment). Identifiers the customer types are masked before they leave,
and the model never writes to the customer. Every reply is rendered from
verified tool results or fixed templates; the one text a person writes is an
operator's message when they resolve a case, shown as the agent's.

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
   - A product id written in the message that exists but belongs to another
     customer → security escalation with the denied reference as evidence
     (`reference_to_foreign_product`), before any model call.
3. **Understand** (`agent/llm/`). One primary model response per turn,
   requested through `LLMClient.chat`: up to 2 attempts per provider (only
   transient errors are retried), and on an error or an open circuit the next
   provider in `LLM_PROVIDERS` (Groq `openai/gpt-oss-120b`, Together, or Claude)
   takes it. The model sees only:
   - the customer's words, masked by `agent/llm/privacy.py` after normalizing
     Unicode dashes, fullwidth and invisible characters:
     - the customer's own product ids become their alias;
     - other internal ids, CURP/RFC → `[id]`;
     - runs of 8+ digits → `[···1234]`;
     - emails → `[email]`;
     - dates are kept;
   - a catalog of per-session aliases (`P1`, `P2`...) with product type,
     currency and status;
   - a history: the customer's masked words as they typed them, amounts
     included, and our replies as figure-free summaries (no warehouse figures).

   It declares the reads asked for as tool calls and the code runs at most two of them (measured on the deployed model, a documented limit on the fallback: LIMITATIONS.md). Tool schemas have **no customer_id**.
   Any prose it writes is discarded.
4. **Act** (`agent/tools/account_tools.py`). This is plain SQL over DuckDB.
   Every tool does four things:
   - checks ownership against the session's customer, raising `PermissionDenied` on a mismatch;
   - returns account numbers as last-4 only;
   - stamps results with the data's as-of date;
   - can enforce a freshness SLO.
   The orchestrator sanitizes arguments before any tool runs: unknown keys are
   dropped, enums and limits clamped, and product references resolved against
   the catalog ("P2", "0002", "Cuenta Ahorro" → an id, or a clarification if
   it is ambiguous). It allows at most 2 tool calls per turn. Payment commissions,
   deadlines and thresholds use a versioned country-rule catalog: country and
   product currency come from verified records, and matching is exact by
   operation, kind and date. Their figures come from the catalog, not from SQL,
   so the customer is not told them: the question goes to an agent, with the
   rule and its source on the ticket when one applies. The production catalog
   stays empty until an official source is reviewed.
   **The one action: tracing a pending movement** ([ADR-002](docs/decisions/ADR-002-one-action-confirmed-in-code.md)).
   When the customer says a transfer, payment or deposit did not arrive, the
   model picks `request_trace`. The tool only finds the customer's pending
   movements that match; it never opens anything.
   - One match: the code shows it (kind, amount, date, product) and asks for
     a plain yes or no. The proposal is kept server side and lives one turn.
   - The next message is judged in code, never by the model
     (`router.confirmation`): a plain yes opens the trace in the tracing
     service (`agent/tools/traces.py`, a sandbox mock), **reads it back**, and
     only then gives its number (and a deadline only from the country rule it
     snapshotted). A trace that does not read back
     is never announced: a person opens it. A plain no opens nothing. Any
     other message lets the proposal lapse and goes through every check above.
   - Asking again returns the same trace (idempotent per customer and
     movement, checked field by field, never by id alone). Several matches are
     listed: the customer answers with the number, resolved in code from the
     list kept server side, or with the amount or the date. Nothing pending
     goes to a person in payments operations.
5. **Decide after each tool** (`router.after_tool`). Each outcome maps to a disposition:
   - `MissingSlot`/`InvalidArgument`/`ResourceNotFound` → CLARIFY (listing the customer's own products).
   - `NotApplicable` → answered (e.g. "payment status doesn't apply to a savings account").
   - `PermissionDenied` → security escalation.
   - `PaymentRuleUnavailable` → a payment-condition handoff (a rule that applies is handed off too).
   - `DataUnavailable` → data escalation.
   - Anything else → tool-failure escalation.
6. **Verify and reply** (`agent/core/render.py`). The reply is rendered in
   ES or PT from the verified tool results, with the data's as-of date. Each
   transaction list is headed by its product. A turn with nothing to look up
   gets a fixed abstain or clarify template. No figure and no claimed action
   can come from model prose, because none is ever shown.
7. **Escalate** (`agent/policy/escalation.py`). The ticket carries:
   - the request and up to 3 prior requests (not a transcript);
   - the reason and the **policy rule that fired**;
   - verified facts, and an evidence pack gathered deterministically per
     category (for fraud: the last 10 transactions with `fraud_score`/`is_fraud`,
     flagged ones first);
   - actions taken, open questions, a suggested next step, and the target queue.

   The ticket is read back from the queue before the customer is told they
   were transferred. If the write was lost or failed, they are told the case
   was not filed and get a code to quote.
8. **Trace** (`agent/tools/audit.py`). Two record types are written:
   - one trace record per turn: rule fired, LLM attempts and token usage
     (including cached tokens), tool calls, latency, cost;
   - one audit record per tool call, keyed by the same trace id.

   These execution records are the explanation artifact. They replace any
   hidden model reasoning.

## Why deterministic where it is

| Concern | Where it lives | Why not the LLM |
|---|---|---|
| Whose data | session + tool ownership check + pre-LLM foreign-reference check | a prompt can be injected; a SQL `WHERE` can't |
| What the model may see | orchestrator: masked text, aliases, history (customer amounts included; no warehouse figures) | the brief forbids customer records in external model requests |
| What to disclose | tool layer (masking) | minimization can't depend on model compliance |
| When to transfer | policy router, lexicon, classifier | must be auditable and testable per rule |
| What the customer reads | renderer, from verified results and templates | a model can state a wrong figure or an action that never happened |
| Whether a handoff happened | ticket read-back | "report only actions whose outcomes the system has verified" |
| Whether to act, and whether it happened | the customer's plain yes, judged in code; trace read-back | an action must not hinge on how a model reads "sí, pero..." |
| Eligibility/credit | out of scope, abstain | brief forbids model-made credit decisions |

The LLM does what only a language model can: paraphrase and slang
understanding in ES/PT, code-switching, product disambiguation, relative
dates ("ayer", "ontem"), and multi-turn context.

## Reliability

- **LLM client** (`agent/llm/client.py`): per-request timeout; a 25 s budget
  per turn; retries only on transient errors (timeouts, 429, 5xx) with
  jittered backoff and no trailing sleep; a per-provider circuit breaker.
  In the browser test an outage cost 1.2 s once, then 13 ms per turn.
- **Claude specifics**:
  - effort `low`, or none on Haiku, which rejects it;
  - no sampling parameters;
  - the tools and the fixed rules prompt-cached (about 1.7K of about 2.1K
    input tokens on Opus 5 and Sonnet 5);
  - on `claude-opus-5`, the server-side refusal fallback;
  - a refusal is a permanent error: the next provider, or an escalation,
    takes the turn.
- **Degraded mode**: if both providers are down, a plain balance question is
  answered deterministically, a confident out-of-scope request is abstained,
  and everything else escalates.
- **Bounded state**: conversation LRU (10k sessions × 8 messages); in-memory
  audit windows; rate limits of 20 msgs/min per session and 10 logins/min per IP;
  1,000-character messages.
- **Turn clock and safe fallback** (`agent/resilience.py`): one time budget per
  turn shared by the model, the lookups and the handoff; bounded retries with
  jittered backoff, only for transient errors, and a write is repeated only when
  it carries an idempotency key. Any failure, including our own exception,
  ends in a fixed reply or a handoff, never an invented answer.
- **One id per turn** (`api/middleware.py`, `agent/observability.py`): the API's
  trace id is in the response headers, the trace record, the tool audit, the
  ticket and the logs, with the time and outcome of each stage.
- **Capacity** (`api/middleware.py`): body-size cap, a concurrency gate on
  `/chat` with a bounded queue and 503 + `Retry-After`, rate limits per
  session, customer and address with 429 + `Retry-After`.
  Details and measurements: docs/operations.md.

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
