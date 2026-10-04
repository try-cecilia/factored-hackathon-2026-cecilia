# Evidence and contracts

One page for a reader who wants to check us. For each stage of a turn it says who decides (the model or the code), what
goes in and out, which control guards it, and where the code and the test are. Then three turns followed end to end, the
key evaluation results with their denominators, and what we do not claim.

How each figure is measured is in [`EVALUATION.md`](../EVALUATION.md). What is missing is in
[`LIMITATIONS.md`](../LIMITATIONS.md). The two decisions behind the design are
[ADR-001](decisions/ADR-001-model-interprets-code-speaks.md) (the model interprets, the code speaks) and
[ADR-002](decisions/ADR-002-one-action-confirmed-in-code.md) (one action, confirmed in code).

This page is checked by `tests/test_evidence_table.py`. The evidence table is generated from the JSON reports, and every
code link below names a function, class or constant that must be defined, in that scope, on the linked line. A
regenerated report, or code that moved, fails the test until `make evidence-table` is run.

## Contract map

Status: **Implemented** means the code and a test exist. **Measured** means an evaluation report also counts it; the
figure is in the [evidence table](#evidence-table). **Pending** is listed after the map, with the exact limits of these
contracts.

| Stage | Who decides | In → out | Control | Status | Code | Tests |
|---|---|---|---|---|---|---|
| Session | Code | Token and message → the session's customer, or `REAUTH_REQUIRED` with nothing read | The token is stored hashed and lives 15 minutes from issue. The customer id comes only from the session. Rate limits run before the turn | Measured: `expired_session` in [`FAILURE_EVAL.md`](../eval/reports/FAILURE_EVAL.md) | [`chat`](../api/main.py#L351), [`_admit`](../api/main.py#L400), [`SessionStore.validate`](../agent/session/auth.py#L77), [`Orchestrator._handle`](../agent/core/orchestrator.py#L797) | [`test_invalid_or_expired_session_requires_reauth_in_the_right_language`](../tests/test_orchestrator.py#L277), [`test_a_session_ends_at_its_ttl_from_issue_however_often_it_is_used`](../tests/test_api.py#L198), [`test_data_shown_while_the_session_is_not_valid_is_unsafe_whatever_disposition_came_back`](../tests/test_failure_handling.py#L169) |
| Guards before the model | Code, with the learned classifier as one input | Raw text and customer status → `ESCALATE` with its rule, or no decision | Compliance hold, safety lexicon, classifier at P(requires_escalation) ≥ τ, and a recognized product id of another customer. All run before the model, which has no escalate tool | Measured: escalation recall in the offline rows, guard recall in the classifier row | [`router.pre_llm`](../agent/policy/router.py#L48), [`escalation_categories`](../agent/policy/signals.py#L62), [`intent_guard.read`](../agent/policy/intent_guard.py#L57), [`foreign_product_refs`](../agent/tools/account_tools.py#L153) | [`test_suspended_customer_is_held_before_any_llm_call`](../tests/test_orchestrator.py#L160), [`test_fraud_report_escalates_pre_llm_with_flagged_evidence_in_the_customers_language`](../tests/test_orchestrator.py#L168), [`test_another_customers_id_however_written_escalates_before_any_model_call`](../tests/test_privacy.py#L133) |
| Model call | Model: it interprets and picks tools | Masked words, a catalog of aliases, a history, the tool schemas → tool calls. Its prose is discarded | Recognized identifier patterns are masked. No tool result, and no record or figure from the warehouse, is sent. One primary response per turn decides the tools. Spending is capped, and without the model a degraded mode answers the simplest requests | Measured: records sent to the model in the system, failure and live rows | [`redact`](../agent/llm/privacy.py#L141), [`with_aliases`](../agent/core/orchestrator.py#L387), [`context_block`](../agent/llm/prompts.py#L46), [`fit_prompt`](../agent/core/orchestrator.py#L376), [`LLMClient.chat`](../agent/llm/client.py#L483), [`Experiments.chat`](../agent/core/experiments.py#L94), [`Orchestrator._degraded`](../agent/core/orchestrator.py#L766) | [`test_the_system_never_gives_the_model_a_customer_record_across_a_whole_conversation`](../tests/test_privacy.py#L72), [`test_one_model_call_per_turn_and_the_models_own_prose_never_reaches_the_customer`](../tests/test_privacy.py#L157), [`test_llm_outage_degrades_to_deterministic_answers_only_where_safe`](../tests/test_orchestrator.py#L257), [`test_past_the_daily_model_budget_the_assistant_runs_as_if_the_model_were_down`](../tests/test_orchestrator.py#L106) |
| Tools | Code | Tool and arguments, customer from the session → verified results or a typed error | Arguments are sanitized and a product resolves only in this customer's catalog. Every tool checks ownership in SQL and writes an audit record. At most two reads run per turn | Measured: adversarial rows; the identity-and-ownership ablation step | [`sanitize_args`](../agent/core/orchestrator.py#L328), [`resolve_product_ref`](../agent/core/orchestrator.py#L303), [`MAX_TOOL_CALLS_PER_TURN`](../agent/core/orchestrator.py#L88), [`run_tool`](../agent/core/orchestrator.py#L369), [`_owned_product`](../agent/tools/account_tools.py#L102), [`_audited`](../agent/tools/account_tools.py#L45) | [`test_ownership_is_enforced_on_every_tool`](../tests/test_tools.py#L18), [`test_numbers_leave_the_tool_layer_masked`](../tests/test_tools.py#L11), [`test_a_model_that_obeys_an_injection_is_stopped_by_the_tool_layer_and_nothing_leaks`](../tests/test_orchestrator.py#L234), [`test_unknown_args_dropped_and_bad_date_clarifies_instead_of_escalating`](../tests/test_orchestrator.py#L244) |
| Verification and disposition | Code | Each result or error → `AUTO_RESOLVE`, `CLARIFY`, `ABSTAIN` or `ESCALATE`, with a stable rule | A fixed mapping in the router. A turn with no tool called never resolves. A failure while processing the request or in a lookup ends in a handoff. One trace record is attempted per turn | Measured: offline rows, against expected outcomes taken from the warehouse and the written policy | [`router.after_tool`](../agent/policy/router.py#L84), [`router.no_tool_answer`](../agent/policy/router.py#L119), [`Orchestrator._unexpected_failure`](../agent/core/orchestrator.py#L516), [`TraceLog.write`](../agent/tools/audit.py#L116) | [`test_single_credit_product_slot_is_filled_then_missing_dpd_escalates_with_ticket`](../tests/test_orchestrator.py#L145), [`test_a_lookup_that_breaks_before_the_model_is_a_handoff_not_a_crash`](../tests/test_failure_handling.py#L40), [`test_trace_record_explains_the_decision`](../tests/test_orchestrator.py#L327) |
| Reply template | Code | Verified facts, catalog labels and language → the reply | Fixed ES/PT templates or facts rendered by code. The evaluation judge rebuilds every reply and counts any other text as unsafe (`text_outside_the_templates`) | Measured: unsafe outcomes in the system, failure and live rows | [`MSG`](../agent/core/render.py#L15), [`render_answer`](../agent/core/render.py#L322), [`render.clarify`](../agent/core/render.py#L187), [`reply_template`](../eval/run_system_eval.py#L685) | [`test_balance_resolves_with_the_verified_figure_and_the_as_of_date`](../tests/test_orchestrator.py#L35), [`test_every_product_specific_answer_names_its_product`](../tests/test_orchestrator.py#L206), [`test_a_reply_that_is_none_of_the_templates_is_unsafe_where_a_handoff_was_refused`](../tests/test_failure_handling.py#L344), [`test_a_judge_that_accepts_only_one_template_fails_these_tests`](../tests/test_failure_handling.py#L682) |
| The one action: tracing a pending movement | The customer's plain yes, judged by code. The model only picks `request_trace` | Matching pending movements, then the next message → a trace opened and read back, nothing opened, or a handoff | Only a plain yes or no counts. Eligibility is checked again at the yes, and old or self-contradicting movements go to a person. The trace is announced only after it reads back, and asking twice opens one | Measured: the trace case types in the offline rows, judged against the tracing service's records. The ablation does not measure the confirmation | [`Orchestrator._trace_step`](../agent/core/orchestrator.py#L677), [`router.confirmation`](../agent/policy/router.py#L157), [`Orchestrator._open_trace`](../agent/core/orchestrator.py#L709), [`request_trace`](../agent/tools/account_tools.py#L328), [`_review_reason`](../agent/tools/account_tools.py#L311), [`TraceService.open_verified`](../agent/tools/traces.py#L60), [`TraceService.trace_id`](../agent/tools/traces.py#L48) | [`test_a_pending_transfer_is_proposed_and_traced_only_after_the_customer_says_yes`](../tests/test_trace.py#L175), [`test_anything_but_a_plain_answer_drops_the_proposal_and_goes_through_the_usual_checks`](../tests/test_trace.py#L213), [`test_a_trace_that_does_not_read_back_is_never_announced`](../tests/test_trace.py#L256), [`test_a_movement_that_settled_after_the_proposal_is_not_traced`](../tests/test_trace.py#L401), [`test_the_judge_flags_a_trace_opened_after_the_customer_said_no`](../tests/test_eval.py#L419) |
| Handoff with a ticket | Code | Decision, masked request, facts and actions → a ticket with reason, rule, evidence and open questions | A time-bounded, idempotent write. The customer hears of it only after it reads back, and otherwise gets a code to quote. Fraud fields are shown to the person and decide nothing | Measured: handoff completeness and escalation recall in the offline rows | [`Orchestrator._escalate`](../agent/core/orchestrator.py#L629), [`escalation.escalate`](../agent/policy/escalation.py#L223), [`_evidence_for`](../agent/policy/escalation.py#L202), [`HumanQueue.enqueue`](../agent/policy/escalation.py#L98), [`HumanQueue.get`](../agent/policy/escalation.py#L156) | [`test_a_handoff_is_announced_only_after_the_ticket_reads_back`](../tests/test_orchestrator.py#L179), [`test_a_ticket_read_back_after_the_budget_is_not_claimed_as_filed_or_named`](../tests/test_handoff_budget.py#L163), [`test_a_handoff_that_cannot_be_filed_says_so_and_does_not_crash_either`](../tests/test_failure_handling.py#L80), [`test_an_unfiled_handoff_does_not_count_as_an_escalation`](../tests/test_eval.py#L196) |
| Operator | A person. Code enforces the order of the steps | Named key, ticket, action and the version seen → an event on the desk. The customer hears it once, by template | Claim before deciding. A stale version or another operator gets a 409. Approving checks the movement again and reads the trace back. The message to the customer is masked and bounded | Implemented. Not measured: no operator acts in the evaluation's scenarios | [`ticket_action`](../api/main.py#L528), [`require_operator`](../api/main.py#L253), [`TicketDesk.act`](../agent/policy/desk.py#L114), [`TicketDesk._execute`](../agent/policy/desk.py#L179), [`_customer_message`](../agent/policy/desk.py#L191), [`Orchestrator._with_case_news`](../agent/core/orchestrator.py#L548) | [`test_a_movement_that_needs_a_person_is_not_traced_until_one_approves`](../tests/test_desk.py#L51), [`test_approving_twice_or_retrying_never_opens_a_second_trace`](../tests/test_desk.py#L63), [`test_a_decision_needs_the_claim_and_is_refused_from_a_stale_screen_or_another_operator`](../tests/test_desk.py#L82), [`test_the_operator_endpoints_need_the_operator_key_and_map_conflicts_to_409`](../tests/test_desk.py#L128), [`test_a_person_resolves_a_case_with_a_message_the_customer_reads_once`](../tests/test_desk.py#L310) |

**The exact limits of these contracts.**
- **Masking is by pattern.** Own product ids become aliases, other recognized ids become `[id]`, runs of 8 or more digits
  and emails are masked. A pattern the masker does not recognize, such as the lowercase, split id "prd fix 0006", reaches
  the model as written; the tool layer still refuses that product.
- **The history is not free of figures.** The assistant's history entries contain no warehouse records or financial
  figures: our answers are kept as figure-free summaries, and a clarifying question without data (dates, currency,
  "which one?") as written. The customer's masked words remain in history, including amounts the customer typed.
- **One primary response per turn decides the tools.** The client may retry that response or fall back to another
  provider ([`LLMClient.chat`](../agent/llm/client.py#L483)). An optional canary model can serve a share of sessions, and
  an optional shadow model can receive the same input in the background, logged only
  ([`Experiments.chat`](../agent/core/experiments.py#L94), [`Experiments.shadow`](../agent/core/experiments.py#L107)). Both
  are off unless configured.
- **The prompt's size limit trims only history.** [`fit_prompt`](../agent/core/orchestrator.py#L376) drops the oldest
  history; it never cuts the two fixed system blocks or the current message (at most 1,000 characters), so those can
  carry a prompt past the limit.
- **Not every failure is a handoff.** A failure while processing the request or in a lookup ends in one. A failure in
  what comes after the answer (the case notices, saving the conversation, writing the trace record) is counted and
  logged, and the answer still goes out ([`Orchestrator.handle_message`](../agent/core/orchestrator.py#L427)).

**Pending.** Each is described in [`LIMITATIONS.md`](../LIMITATIONS.md) or [`SECURITY.md`](../SECURITY.md).
- The orchestrator does not expose which template it used, so the judge rebuilds replies from the outside and leaves some
  gaps open (LIMITATIONS, "Not yet measured", item 5).
- The reserved failure set has not run with a live model, beyond one small sample on Groq that cannot be rebuilt from
  artifacts ([`LIVE_SAMPLE_GROQ.md`](../eval/reports/LIVE_SAMPLE_GROQ.md)). The Groq fallback has not run on the 138-case
  live sample.
- Operators have no MFA, and nobody has run a penetration test of the deployment.

## Three turns, end to end

### A simple question: "cuál es mi saldo"

1. [`chat`](../api/main.py#L351) receives the message; [`_admit`](../api/main.py#L400) applies the rate limits before anything runs.
2. [`Orchestrator.handle_message`](../agent/core/orchestrator.py#L427) gives the turn its trace id and its time budget.
3. [`Orchestrator._handle`](../agent/core/orchestrator.py#L797) validates the session with
   [`SessionStore.validate`](../agent/session/auth.py#L77): a token whose hash is stored and that was issued less than 15
   minutes ago. A `customer_id` among the model's arguments is dropped later; identity comes only from here. No trace
   proposal is waiting.
4. [`router.pre_llm`](../agent/policy/router.py#L48) finds no hold, no lexicon match and a classifier reading under τ.
   [`foreign_product_refs`](../agent/tools/account_tools.py#L153) finds no foreign id.
5. [`get_customer_profile`](../agent/tools/account_tools.py#L172) loads the catalog, [`with_aliases`](../agent/core/orchestrator.py#L387)
   names its products P1, P2…, [`redact`](../agent/llm/privacy.py#L141) masks the text and
   [`context_block`](../agent/llm/prompts.py#L46) writes the catalog the model sees: aliases, type, currency, status.
6. One primary model response, through [`Experiments.chat`](../agent/core/experiments.py#L94) and
   [`LLMClient.chat`](../agent/llm/client.py#L483), declares a `get_account_summary` call. Nothing else in it is used.
7. [`sanitize_args`](../agent/core/orchestrator.py#L328) drops unknown arguments, checks enums and limits, and resolves
   a product only within this customer's catalog. [`run_tool`](../agent/core/orchestrator.py#L369) calls
   [`get_account_summary`](../agent/tools/account_tools.py#L193) for the session's customer, which checks ownership in SQL
   and writes the audit record. Up to two reads run per turn; a trace request takes the turn alone.
8. [`router.after_tool`](../agent/policy/router.py#L84) sees no error, so the disposition is `AUTO_RESOLVE`.
9. [`render_answer`](../agent/core/render.py#L322) writes the balances and their as-of date. The model's history keeps
   only `[Se respondió al cliente con datos verificados de: …]`, with no figures.
10. [`TraceLog.write`](../agent/tools/audit.py#L116) records the turn with the rule `verified_tool_results`. If that
    write fails, the failure is counted and logged and the answer still goes out.

Test: [`test_balance_resolves_with_the_verified_figure_and_the_as_of_date`](../tests/test_orchestrator.py#L35).

### A "sí" that opens a trace

Turn 1, "hice una transferencia que todavía no llega":

1. Steps 1 to 6 above, and the model picks `request_trace`.
2. [`request_trace`](../agent/tools/account_tools.py#L328) returns the customer's pending transfers, payments and deposits,
   each with its [`_review_reason`](../agent/tools/account_tools.py#L311). It opens nothing.
3. [`Orchestrator._trace_step`](../agent/core/orchestrator.py#L677) asks [`router.trace_step`](../agent/policy/router.py#L176).
   With one match it stores the proposal on the server and replies with the `trace_propose` template: the movement and
   a yes-or-no question. The model's history gets only that a trace was proposed.

Turn 2, "sí":

4. [`Orchestrator._handle`](../agent/core/orchestrator.py#L797) finds the proposal and asks
   [`router.confirmation`](../agent/policy/router.py#L157), which accepts only a whole message that is a yes or a no.
   No model call happens on this turn.
5. [`Orchestrator._open_trace`](../agent/core/orchestrator.py#L709) runs [`request_trace`](../agent/tools/account_tools.py#L328)
   again for that one movement. If it settled, a person takes over. If it needs review, [`router.trace_review`](../agent/policy/router.py#L205)
   hands it to a person with the customer's yes on the ticket.
6. [`TraceService.open_verified`](../agent/tools/traces.py#L60) opens the request and reads it back for this customer and
   this movement, with bounded retries. Without a read-back, [`router.trace_unverified`](../agent/policy/router.py#L199)
   sends it to a person and the customer is not told a trace exists.
7. [`router.trace_opened`](../agent/policy/router.py#L194): the `trace_opened` template gives the trace number; a deadline
   only from the country rule the trace snapshotted, and none is loaded today.

Tests: [`test_a_pending_transfer_is_proposed_and_traced_only_after_the_customer_says_yes`](../tests/test_trace.py#L175) and
[`test_a_movement_that_settled_after_the_proposal_is_not_traced`](../tests/test_trace.py#L401).

### A handoff that ends in a ticket and an operator's answer

1. "Hay un movimiento en mi cuenta que yo no hice" reaches [`router.pre_llm`](../agent/policy/router.py#L48);
   [`escalation_categories`](../agent/policy/signals.py#L62) matches fraud, so the rule is `lexicon:fraud` and the model is
   never called.
2. [`Orchestrator._escalate`](../agent/core/orchestrator.py#L629) opens the handoff budget and calls
   [`escalation.escalate`](../agent/policy/escalation.py#L223). [`_evidence_for`](../agent/policy/escalation.py#L202) lists the
   ten most recent movements with the flagged ones first, within half the budget.
3. [`HumanQueue.enqueue`](../agent/policy/escalation.py#L98) writes the ticket. [`HumanQueue.get`](../agent/policy/escalation.py#L156)
   reads it back. Only then does the customer get the `escalate` template; otherwise `escalate_unverified` with a code.
4. An operator calls [`ticket_action`](../api/main.py#L528) with their key, checked by
   [`require_operator`](../api/main.py#L253). [`TicketDesk.act`](../agent/policy/desk.py#L114) records the claim, then the
   resolution, whose message [`_customer_message`](../agent/policy/desk.py#L191) puts on one line with card numbers masked.
5. On the customer's next turn, [`Orchestrator._with_case_news`](../agent/core/orchestrator.py#L548) puts the
   [`case_update`](../agent/core/render.py#L107) line ahead of the reply, once.

Tests: [`test_fraud_report_escalates_pre_llm_with_flagged_evidence_in_the_customers_language`](../tests/test_orchestrator.py#L168),
[`test_a_handoff_is_announced_only_after_the_ticket_reads_back`](../tests/test_orchestrator.py#L179) and
[`test_a_person_resolves_a_case_with_a_message_the_customer_reads_once`](../tests/test_desk.py#L310).

## Evidence table

Generated by `python -m eval.evidence_table --write` from the reports in [`eval/reports/`](../eval/reports/); do not edit it
by hand. "Fingerprint" is the `policy_sha256` field of the report, a hash of the code, the judge, the simulated models
and the cases the evaluation runs ([`eval/fingerprint.py`](../eval/fingerprint.py)). "Same code as now" compares it with
the fingerprint of this checkout. A **no** means the report measured an earlier version of that code. The CI gate holds
the offline, adversarial, failure and ablation reports to the current fingerprint. It does not hold the live report to it
(measuring it again costs money and a key the CI does not have): it requires the rows of every run, and a live report
measured on other code must be declared as such in README.md and EVALUATION.md, so a **no** there is shown, not hidden.

<!-- evidence-table:start -->
Fingerprint of the code in this checkout: `79eb5f217aa2` (first 12 of 64 hex digits; `eval/fingerprint.py`).

| Result | Model | Date (UTC) | Fingerprint | Same code as now | n | Figures (k / denominator) | Report | Caveats |
|---|---|---|---|---|---|---|---|---|
| Offline, ideal model | scripted ideal, prompt 3.3.0 | 2026-10-04 | `79eb5f217aa2` | yes | 548 cases (test split) | unsafe 0/548 · records to the model 0/548 · safe automated resolution 236/238 · escalation recall 168/168 · handoff completeness 172/172 | [`SYSTEM_EVAL.md`](../eval/reports/SYSTEM_EVAL.md), [`system_eval.json`](../eval/reports/system_eval.json) | Scripted ideal model: an upper bound on the model's understanding, with no model latency or cost. 0 observed bounds the true rate below about 3/n, not at 0. |
| Offline, adversarial model | scripted adversarial, prompt 3.3.0 | 2026-10-04 | `79eb5f217aa2` | yes | 548 cases (test split) | unsafe 0/548 · records to the model 0/548 · safe automated resolution 144/238 · escalation recall 168/168 · handoff completeness 293/293 | [`SYSTEM_EVAL_ADVERSARIAL.md`](../eval/reports/SYSTEM_EVAL_ADVERSARIAL.md), [`system_eval_adversarial.json`](../eval/reports/system_eval_adversarial.json) | Scripted bad model written by the team (obeys injections, asks for other customers' products, invents figures): it shows that safety does not depend on the model, not what a real bad model would do. |
| Baseline: keyword bot | keyword rules, no model | 2026-10-04 | `79eb5f217aa2` | yes | 548 cases (test split) | unsafe 0/548 · records to the model n/a · safe automated resolution 167/238 · escalation recall 96/168 · handoff completeness 48/96 | [`SYSTEM_EVAL.md`](../eval/reports/SYSTEM_EVAL.md), [`system_eval.json`](../eval/reports/system_eval.json) | Deterministic keyword bot that shares session, policy, tools, ownership checks, tickets and renderer: the gap isolates understanding. It sends nothing to a model. |
| Reserved failure set, ideal model | scripted ideal, prompt 3.3.0 | 2026-10-04 | `79eb5f217aa2` | yes | 234 cases, 3 batches | unsafe 0/234 · crashes 0/234 · records to the model 2/234 · handled 232/234 · safe 232/234 | [`FAILURE_EVAL.md`](../eval/reports/FAILURE_EVAL.md), [`failure_eval.json`](../eval/reports/failure_eval.json) | Team-written cases on 5 fixture customers. Batch 2 was written after seeing batch 1's failures and batch 3 after the judge was fixed; the fixes came after seeing them, so post-fix figures are regression evidence, not held out. The records sent to the model are the lowercase, split product id ("prd fix 0006"), a documented masking limit. |
| Reserved failure set, adversarial model | scripted adversarial, prompt 3.3.0 | 2026-10-04 | `79eb5f217aa2` | yes | 234 cases, 3 batches | unsafe 0/234 · crashes 0/234 · records to the model 2/234 · handled 199/234 · safe 232/234 | [`FAILURE_EVAL.md`](../eval/reports/FAILURE_EVAL.md), [`failure_eval.json`](../eval/reports/failure_eval.json) | Team-written cases on 5 fixture customers. Batch 2 was written after seeing batch 1's failures and batch 3 after the judge was fixed; the fixes came after seeing them, so post-fix figures are regression evidence, not held out. The records sent to the model are the lowercase, split product id ("prd fix 0006"), a documented masking limit. |
| Live, claude-sonnet-5 | anthropic/claude-sonnet-5, prompt 3.2.1 | 2026-10-03 | `ad2212c4c416` | **no** | 138 cases × 3 runs (test split) | unsafe, run 1 0/138 · unsafe, worst of 3 runs 0/138 · records to the model, worst run 0/138 · safe automated resolution, run 1 57/60 · escalation recall, run 1 41/42 | [`SYSTEM_EVAL_LIVE.md`](../eval/reports/SYSTEM_EVAL_LIVE.md), [`system_eval_live.json`](../eval/reports/system_eval_live.json) | Stratified sample of the test split (3 cases per case type and language), not all of it. The headline is run 1. The report keeps the per-case rows of all 3 runs. No unsafe outcome in any run. |
| Live, claude-haiku-4-5-20251001 | anthropic/claude-haiku-4-5-20251001, prompt 3.2.1 | 2026-10-03 | `ad2212c4c416` | **no** | 138 cases × 3 runs (test split) | unsafe, run 1 0/138 · unsafe, worst of 3 runs 1/138 · records to the model, worst run 0/138 · safe automated resolution, run 1 46/60 · escalation recall, run 1 33/42 | [`SYSTEM_EVAL_LIVE.md`](../eval/reports/SYSTEM_EVAL_LIVE.md), [`system_eval_live.json`](../eval/reports/system_eval_live.json) | Stratified sample of the test split (3 cases per case type and language), not all of it. The headline is run 1. The report keeps the per-case rows of all 3 runs. Unsafe outcome: run 2, case `f53f65d75771` (transactions, pt), `wrong_account_or_figure`. |
| Ablation: groups of controls removed | scripted ideal and bad | 2026-10-04 | `79eb5f217aa2` | yes | 548 cases × 8 variants (test split) | unsafe with no control, ideal 96/548 · bad 410/548 · unsafe with every control, ideal 0/548 · bad 0/548 | [`ABLATION.md`](../eval/reports/ABLATION.md), [`ablation.json`](../eval/reports/ablation.json) | Offline, scripted models. Cumulative ladder by groups of controls: no effect is attributed to one control. The naive variants were built by the team and never open a trace, so the confirmation of the action is not measured. |
| Intent classifier (learned component) | TF-IDF char+word + logistic regression, scikit-learn 1.9.1 | 2026-10-01 | not recorded | n/a | 85 test utterances | accuracy, learned 72/85 · keywords 54/85 · runtime guard recall 14/15 · false escalations 0/70 | [`intent_classifier.md`](../eval/reports/intent_classifier.md), [`intent_classifier.json`](../eval/reports/intent_classifier.json) | Test utterances written by the team (same-author bias). The keyword baseline and the lexicon-only guard are an upper bound: two lexicon patterns were added after the split was scored. Not a policy_sha256 report. |
| Red team of the deployed demo | deployed demo, not recorded in the report | 2026-09-30 | not recorded | n/a | 224 turns in 42 sessions | findings in the records 0 on 4 checks · turns on a dead session 3 · tickets 39 · traces opened 1 | [`RED_TEAM.md`](../eval/reports/RED_TEAM.md), [`red_team.json`](../eval/reports/red_team.json) | One session on the deployed demo by people who did not build the assistant (a teammate and friends of the team); 74 turns came in pasted bursts; participants' notes still to come. The report records neither the model nor a fingerprint. |
<!-- evidence-table:end -->

## What we do not claim

- **0 observed is not 0 guaranteed.** By the rule of three, 0 unsafe in 548 cases bounds the true rate below about 0.55%,
  in 234 below about 1.3%, and in 138 below about 2.2%. It is a statement about these cases.
- **The data is synthetic.** Every customer record is the organizer's synthetic dataset or a hand-made fixture. The
  Portuguese text, the classifier's training and test utterances and the evaluation phrasings were written by the team.
  A set written by people outside the team has not yet reached the 60 messages from 8 people
  it needs ([`docs/human_set.md`](human_set.md)).
- **The action runs in a sandbox.** The tracing service is a JSONL file with the same `open` and `get` calls a bank's
  API would have. Its deadline comes only from a reviewed country rule, and the catalog ships empty, so no deadline is
  promised. The demo's identity provider and PINs are for testing.
- **The live evaluation is a sample.** 138 of the 548 test cases, 3 runs per model; the report keeps the rows of every run.
  Groq's `gpt-oss-120b` has not run on it.
- **The scripted models are not a language model.** The ideal model is an upper bound on understanding; the adversarial
  one is a bad model the team wrote. They measure the deterministic layers, and that safety does not depend on the model.
- **Nothing here is a production measurement.** The monthly figures in EVALUATION.md are projections, labeled as such.
- **The judge is code, not a model, and it has known gaps.** It rebuilds replies from the templates; what that leaves open
  is listed in LIMITATIONS.md, "Not yet measured", item 5.
- **The red team was one session, not a penetration test.** It attacked the assistant, not the hosting, TLS or headers.
- **There is no fraud model.** `is_fraud` could not be learned from the transaction
  ([ADR-005](decisions/ADR-005-no-fraud-or-risk-model.md)); the fraud fields only order the evidence a person reads.
- **Masking is pattern-based.** A name or an amount the customer types reaches the model as written, and a lowercase,
  split id ("prd fix 0006") is not masked; the tool layer still refuses the product.
