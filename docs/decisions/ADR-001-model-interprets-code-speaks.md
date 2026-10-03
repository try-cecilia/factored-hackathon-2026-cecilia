# ADR-001: The model interprets; the code speaks

Status: accepted, 2026-09-27 (prompt v3.0.0). Supersedes the v2 turn loop.

## Context

The brief sets a hard boundary: "Do not include private customer records, credentials, or restricted data in public submissions **or external model requests**." It also asks the system to "report only actions whose outcomes the system has verified" and to "enforce permissions and policy outside model-generated prose".

Design v2 used the LLM as a tool-calling agent that also wrote the reply. On every resolved turn the external provider (Groq, then Together) received:
- the customer's product catalog, with internal product ids, the last 4 digits and the customer's segment;
- the tool results: balances, movements, amounts, merchant names;
- the previous replies, figures included.

A numeric grounding check then compared the model's figures against the tool results. That check caught invented figures, but it could not catch invented actions ("ya bloqueé tu tarjeta"), and it did nothing about the data leaving for the provider.

## Decision

The model only understands the request and chooses tools. The system never gives it a customer record, and the model never writes to the customer.

1. **One primary model response per turn** (the client may retry it or fall back to another provider). It declares the reads the customer asked for as tool calls, and the code runs at most two of them, one after the other, naming in a template the ones it did not run (a trace request, wherever it is declared, takes the turn alone). "In parallel" means several calls in one model response, which not every provider offers; the code does not read what the model did not declare. Tool results never go back to the model.
2. **Every reply is rendered in code**, from verified tool results or fixed ES/PT templates (`agent/core/render.py`). The model's prose is discarded. No figure and no claimed action can come from it, so the grounding verifier had nothing left to check and was removed. The one text not written by the code is a person's: when an operator resolves a case, their message reaches the customer as written (on one line, card numbers masked), inside a fixed frame that says an agent wrote it ("Mensaje del agente: «...»").
3. **What the model sees:**
   - the customer's words, masked by `agent/llm/privacy.py` after normalizing Unicode dashes, fullwidth and invisible characters (so `PRD–FIX0006`, an id glued to a word, or `5000–000–004` are caught like their plain forms):
     - the customer's own product ids become their alias;
     - other internal ids and CURP/RFC codes become `[id]`;
     - any run of 8+ digits (card, account, CLABE, CBU, national ID, CUIL, phone) becomes `[···1234]`;
     - emails become `[email]`;
   - a catalog of per-session aliases (`P1`, `P2`...) with product type, currency and status only;
   - a history in which our replies are figure-free summaries.

   The system never gives it an internal id, an account number, a last-4, a balance, a transaction, a name or the customer's segment. What the customer chooses to type is a different matter: a name, an address or an amount goes out as written, because masking is pattern-based.

   Tickets for the bank's own agents keep more. Only card-length numbers are masked there, so an agent can still read "me cobraron 15.000.000".
4. **References resolve in code.** The model passes an alias, the digits the customer gave, or the product type. `resolve_product_ref` maps it onto one of the session customer's products, or asks which one. Every tool then checks ownership against the session.
5. **Two checks that don't depend on the model** run before it is called:
   - the safety lexicon and classifier guard (from v2);
   - a new check: a product id written in the message that belongs to another customer escalates to security review with evidence (`reference_to_foreign_product`). In the live smoke run a weaker model declined to call a tool on that request. Detection must not depend on that choice.
6. **A handoff is announced only after its ticket reads back.** If the write is lost or fails, the customer is told the case was not filed and gets a code to quote.

## Consequences

Gains:
- **Compliance by construction, and measured.**
  - `tests/test_privacy.py` runs a whole multi-turn conversation: balances, movements, payment status, a product clarification and its answer. It asserts that none of the customer's records reaches the model. Those records are the balances, amounts, merchants, internal ids, account numbers, name, document, email, phone and segment, all read straight from the warehouse.
  - The evaluation harness runs the same check on every case of every run (`records_sent_to_model`), including the adversarial model and live models.
- **No hallucinated figure or unverified action can reach a customer.** This is a property of the architecture, not the output of a check that could miss. It is about the model: an operator's resolution message is a person's word, marked as such, and what it says is the operator's responsibility.
- **Half the model calls.** v2 made about 2 calls per resolved turn: choose tools, then phrase. v3 makes 1. On Claude, the tools and the fixed rules are also prompt-cached: about 1.7K of about 2.1K input tokens per call, billed at a tenth of the input price (`tokens (cached)` in the live smoke report).
- **Injection handling no longer depends on the model**, as point 5 explains.

Costs:
- **Replies are templated.** They read more like a bank statement than a conversation. For a banking channel that is usually a feature, and the templates exist in Spanish and Portuguese.
- **No chained lookups.** The model cannot read one result to decide the next lookup. This workflow does not need it: every question maps to one or two independent lookups. Two in one message depend on the model declaring both: measured on Claude Sonnet 5 (80 of 80 two-request turns covered) and shown to be a limit on the fallback, GPT-OSS on Groq, which offers no parallel tool use (`docs/evidence/compound_probe_anthropic.md`, `compound_probe_groq.md`; LIMITATIONS.md).
- **The customer's own words still reach the provider**, masked. That is unavoidable for a language model; production would also pick a provider or deployment under the bank's data-processing terms.

## Alternatives considered

- **Keep v2 and send results to the model for phrasing.** Rejected: it violates the data boundary.
- **Let the model write figure-free wrapper sentences around the rendered data.** Rejected: it reintroduces unverified claims (actions, promises) for cosmetic gain.
- **Self-host an open model inside the bank's perimeter**, so records could be shown to it. This is the production option if a bank wants model-written replies. It is out of reach on the prototype's free-tier hosting.

## Evidence

- **Tests:** `tests/test_privacy.py`, and in `tests/test_orchestrator.py` the handoff read-back and the foreign-reference guard.
- **Live smoke runs:** `eval/reports/LIVE_SMOKE.md`, 13 turns on Claude Opus 5, Sonnet 5 and Haiku 4.5 over the synthetic fixtures, each graded against the outcome written for it before the run. Opus 5 and Sonnet 5 got 13/13. Haiku 4.5 got 12/13 in the committed run and 13/13 in another: on one ambiguous turn it asks a generic question instead of letting the system list the products, which is safe but less precise. Single runs vary, which is why the held-out live run repeats every case 3 times.
- **Held-out measurement:** `make eval-live` on the organizer's warehouse (`eval/reports/SYSTEM_EVAL_LIVE.md`), on 2026-10-03: on 138 test cases with Claude Sonnet 5 and Haiku 4.5, three runs per model, no case sent a customer record to the model in any run and no reply was text outside the templates. Sonnet 5, the deployed model, had no unsafe outcome in any run. Haiku 4.5 had one in its second run: asked for the savings account ending 3862, the model chose another of the customer's own products, and the reply listed that product's movements (`wrong_account_or_figure`): the reply was written by code from verified data, but nothing in the code caught that the product the model chose was not the one the customer named. In the earlier run of 2026-10-02, on older code, Haiku 4.5's one unsafe outcome was a reply the judge could not rebuild from the templates; only that run's first repeat kept its rows, so it could not be inspected (`LIMITATIONS.md`, item 5). Offline, the same held for all 548 test cases with the ideal and the adversarial model (`eval/reports/SYSTEM_EVAL.md`, `SYSTEM_EVAL_ADVERSARIAL.md`).
