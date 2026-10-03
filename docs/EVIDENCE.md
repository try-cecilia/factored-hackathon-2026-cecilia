# Evidence and contracts

One page for a reader who wants to check us. For each stage of a turn it says who decides (the model or the code), what
goes in and out, which control guards it, and where the code and the test are. Then three turns followed end to end, every
published figure with its denominator, and what we do not claim.

How each figure is measured is in [`EVALUATION.md`](../EVALUATION.md). What is missing is in
[`LIMITATIONS.md`](../LIMITATIONS.md). The two decisions behind the design are
[ADR-001](decisions/ADR-001-model-interprets-code-speaks.md) (the model interprets, the code speaks) and
[ADR-002](decisions/ADR-002-one-action-confirmed-in-code.md) (one action, confirmed in code).

This page is checked by `tests/test_evidence_table.py`. The evidence table is generated from the JSON reports, and every
code link below names a function, class or constant whose definition must be on the linked line. A regenerated report, or
code that moved, fails the test until `python -m eval.evidence_table --write` is run.

## Contract map

Status: **Implemented** means the code and a test exist. **Measured** means an evaluation report also counts it; the
figure is in the [evidence table](#evidence-table). **Pending** is listed at the end of the map.

| Stage | Who decides | In → out | Control | Status | Code | Tests |
|---|---|---|---|---|---|---|
| Session | Code | The session token and the message → the session's customer and attributes, or `REAUTH_REQUIRED` with nothing read | Only a hash of the token is stored. A customer session ends 15 minutes after it is issued, and using it does not extend it. The customer id comes from the session, never from the model: a `customer_id` in the model's arguments is dropped. Rate limits per address, session and customer run before the turn | Measured: the `expired_session` category of [`FAILURE_EVAL.md`](../eval/reports/FAILURE_EVAL.md) | [`chat`](../api/main.py#L416), [`_admit`](../api/main.py#L465), [`SessionStore.validate`](../agent/session/auth.py#L77), [`Orchestrator._handle`](../agent/core/orchestrator.py#L705) | [`test_invalid_or_expired_session_requires_reauth_in_the_right_language`](../tests/test_orchestrator.py#L242), [`test_a_session_ends_at_its_ttl_from_issue_however_often_it_is_used`](../tests/test_api.py#L198), [`test_data_shown_while_the_session_is_not_valid_is_unsafe_whatever_disposition_came_back`](../tests/test_failure_handling.py#L169) |
| Guards before the model | Code. The intent classifier is a learned input; its threshold and the rule around it are code | The raw text and the customer's status → an `ESCALATE` decision with its rule, or no decision and the classifier's reading | A suspended customer is held. The safety lexicon fires on fraud, theft, takeover and similar words. The classifier escalates at P(requires_escalation) ≥ τ, chosen on dev; it is skipped only when the customer answers our own clarifying question, and the lexicon still runs. A product id of another customer written in the message goes to security review. All of this runs before any model call, and the model has no escalate tool | Measured: escalation recall in the offline rows, guard recall in the classifier row | [`router.pre_llm`](../agent/policy/router.py#L47), [`escalation_categories`](../agent/policy/signals.py#L62), [`intent_guard.read`](../agent/policy/intent_guard.py#L57), [`foreign_product_refs`](../agent/tools/account_tools.py#L116) | [`test_suspended_customer_is_held_before_any_llm_call`](../tests/test_orchestrator.py#L125), [`test_fraud_report_escalates_pre_llm_with_flagged_evidence_in_the_customers_language`](../tests/test_orchestrator.py#L133), [`test_another_customers_id_however_written_escalates_before_any_model_call`](../tests/test_privacy.py#L133) |
| Model call | Model: it interprets and picks tools | The customer's words with identifiers masked (own product ids become aliases P1, P2…; other ids, runs of 8+ digits and emails are masked), a catalog of aliases with type, currency and status, a history without figures, the tool schemas → tool calls with arguments. Its prose is discarded | One call per turn. No record, tool result or reply is ever sent to it. The prompt has a size cap, and spending has a daily and a per-session cap. With the model down or over budget, the degraded mode answers only a plain balance or a clear out-of-scope request, and the rest goes to a person | Measured: records sent to the model, every row; live rows | [`redact`](../agent/llm/privacy.py#L141), [`with_aliases`](../agent/core/orchestrator.py#L345), [`context_block`](../agent/llm/prompts.py#L46), [`fit_prompt`](../agent/core/orchestrator.py#L334), [`LLMClient.chat`](../agent/llm/client.py#L478), [`Orchestrator._degraded`](../agent/core/orchestrator.py#L674) | [`test_the_system_never_gives_the_model_a_customer_record_across_a_whole_conversation`](../tests/test_privacy.py#L72), [`test_one_model_call_per_turn_and_the_models_own_prose_never_reaches_the_customer`](../tests/test_privacy.py#L157), [`test_llm_outage_degrades_to_deterministic_answers_only_where_safe`](../tests/test_orchestrator.py#L222), [`test_past_the_daily_model_budget_the_assistant_runs_as_if_the_model_were_down`](../tests/test_orchestrator.py#L71) |
| Tools | Code | The tool the model named and its arguments, with the customer from the session → verified results, with their as-of date and numbers as last 4 digits, or a typed error | Unknown arguments are dropped, enums and limits checked, and a product reference resolves only onto this customer's catalog. Every tool checks ownership in SQL and writes an audit record. At most two reads run per turn, and a trace request takes the turn alone. Retries are bounded by the turn's deadline | Measured: adversarial rows, where the model asks for other customers' products; the identity rung of the ablation | [`sanitize_args`](../agent/core/orchestrator.py#L287), [`resolve_product_ref`](../agent/core/orchestrator.py#L262), [`MAX_TOOL_CALLS_PER_TURN`](../agent/core/orchestrator.py#L82), [`run_tool`](../agent/core/orchestrator.py#L327), [`_owned_product`](../agent/tools/account_tools.py#L96), [`_audited`](../agent/tools/account_tools.py#L41) | [`test_ownership_is_enforced_on_every_tool`](../tests/test_tools.py#L17), [`test_numbers_leave_the_tool_layer_masked`](../tests/test_tools.py#L10), [`test_a_model_that_obeys_an_injection_is_stopped_by_the_tool_layer_and_nothing_leaks`](../tests/test_orchestrator.py#L199), [`test_unknown_args_dropped_and_bad_date_clarifies_instead_of_escalating`](../tests/test_orchestrator.py#L209) |
| Verification and disposition | Code | Each tool result or error → `AUTO_RESOLVE`, `CLARIFY`, `ABSTAIN` or `ESCALATE`, with a stable rule | The router maps errors in a fixed order. A missing argument or an unknown product asks the customer. Another customer's product goes to security. Missing data and failed tools go to a person. A turn with no tool called abstains or asks and never resolves. An exception anywhere in the turn ends in a handoff. Every turn writes one trace record with the rule that decided | Measured: offline rows. The judge reads the expected outcome from the warehouse and the written policy, not from the system | [`router.after_tool`](../agent/policy/router.py#L83), [`router.no_tool_answer`](../agent/policy/router.py#L106), [`Orchestrator._unexpected_failure`](../agent/core/orchestrator.py#L474), [`TraceLog.write`](../agent/tools/audit.py#L116) | [`test_single_credit_product_slot_is_filled_then_missing_dpd_escalates_with_ticket`](../tests/test_orchestrator.py#L110), [`test_a_lookup_that_breaks_before_the_model_is_a_handoff_not_a_crash`](../tests/test_failure_handling.py#L40), [`test_trace_record_explains_the_decision`](../tests/test_orchestrator.py#L264) |
| Reply template | Code | Verified facts, the catalog's labels and the language → the reply | Every reply is a fixed ES/PT template or verified facts rendered by code. The one text the code does not write is an operator's resolution message, shown inside a frame that says a person wrote it. The judge rebuilds every reply from the templates and the turn's data; any other text is `text_outside_the_templates`, unsafe by itself | Measured: unsafe in every row | [`MSG`](../agent/core/render.py#L13), [`render_answer`](../agent/core/render.py#L242), [`render.clarify`](../agent/core/render.py#L107), [`reply_template`](../eval/run_system_eval.py#L647) | [`test_balance_resolves_with_the_verified_figure_and_the_as_of_date`](../tests/test_orchestrator.py#L34), [`test_every_product_specific_answer_names_its_product`](../tests/test_orchestrator.py#L171), [`test_a_reply_that_is_none_of_the_templates_is_unsafe_where_a_handoff_was_refused`](../tests/test_failure_handling.py#L344), [`test_a_judge_that_accepts_only_one_template_fails_these_tests`](../tests/test_failure_handling.py#L652) |
| The one action: tracing a pending movement | The customer's plain yes, judged by code. The model only picks `request_trace` | The customer's pending movements that match, owned per SQL, then the customer's next message → a trace opened and read back, nothing opened, or a handoff | The proposal stays on the server for one turn. Only a message that is a plain yes or no counts, and the model never judges it. Eligibility is checked again at the yes. A movement older than 90 days, or dated before its product or its customer existed, goes to a person. The trace is announced only after it reads back, and its id comes from customer and movement, so asking twice opens one | Measured: `trace_confirm`, `trace_review` and `trace_cancel` in the offline rows, judged against the tracing service's own records. The ablation does not measure the confirmation | [`Orchestrator._trace_step`](../agent/core/orchestrator.py#L594), [`router.confirmation`](../agent/policy/router.py#L144), [`Orchestrator._open_trace`](../agent/core/orchestrator.py#L620), [`request_trace`](../agent/tools/account_tools.py#L291), [`_review_reason`](../agent/tools/account_tools.py#L274), [`TraceService.open_verified`](../agent/tools/traces.py#L58), [`TraceService.trace_id`](../agent/tools/traces.py#L46) | [`test_a_pending_transfer_is_proposed_and_traced_only_after_the_customer_says_yes`](../tests/test_trace.py#L40), [`test_anything_but_a_plain_answer_drops_the_proposal_and_goes_through_the_usual_checks`](../tests/test_trace.py#L64), [`test_a_trace_that_does_not_read_back_is_never_announced`](../tests/test_trace.py#L81), [`test_a_movement_that_settled_after_the_proposal_is_not_traced`](../tests/test_trace.py#L202), [`test_the_judge_flags_a_trace_opened_after_the_customer_said_no`](../tests/test_eval.py#L404) |
| Handoff with a ticket | Code | The decision, the request with card numbers masked, verified facts, actions and earlier requests → a ticket with reason, rule, evidence and open questions. The customer hears of it only after it reads back | The write has a time budget and is idempotent by ticket id. If the ticket does not read back, the customer gets `escalate_unverified` and a code to quote. For a fraud report the evidence lists recent movements with the flagged ones first; the fraud fields are shown to the person and decide nothing | Measured: handoff completeness and escalation recall in the offline rows. An unfiled handoff counts as a missed escalation | [`Orchestrator._escalate`](../agent/core/orchestrator.py#L569), [`escalation.escalate`](../agent/policy/escalation.py#L222), [`_evidence_for`](../agent/policy/escalation.py#L201), [`HumanQueue.enqueue`](../agent/policy/escalation.py#L98), [`HumanQueue.get`](../agent/policy/escalation.py#L156) | [`test_a_handoff_is_announced_only_after_the_ticket_reads_back`](../tests/test_orchestrator.py#L144), [`test_a_ticket_read_back_after_the_budget_is_not_claimed_as_filed_or_named`](../tests/test_handoff_budget.py#L163), [`test_a_handoff_that_cannot_be_filed_says_so_and_does_not_crash_either`](../tests/test_failure_handling.py#L80), [`test_an_unfiled_handoff_does_not_count_as_an_escalation`](../tests/test_eval.py#L181) |
| Operator | A person. Code enforces the order of the steps | The operator's named key, the ticket, the action (claim, approve, reject, release, resolve) and the version they saw → an event on the desk. The customer hears it once, by template | The name of the key that acted is recorded, never a field of the request. Deciding needs the claim first. A stale version or a second operator gets a 409. Approving checks again that the movement is still pending and reads the trace back. A ticket that carries an action cannot be resolved around it. The resolution message is one line of at most 500 characters, with card numbers masked | Implemented. Not measured: no operator acts in the evaluation's scenarios | [`ticket_action`](../api/main.py#L591), [`require_operator`](../api/main.py#L319), [`TicketDesk.act`](../agent/policy/desk.py#L82), [`TicketDesk._execute`](../agent/policy/desk.py#L141), [`_customer_message`](../agent/policy/desk.py#L151), [`Orchestrator._with_case_news`](../agent/core/orchestrator.py#L498) | [`test_a_movement_that_needs_a_person_is_not_traced_until_one_approves`](../tests/test_desk.py#L51), [`test_approving_twice_or_retrying_never_opens_a_second_trace`](../tests/test_desk.py#L63), [`test_a_decision_needs_the_claim_and_is_refused_from_a_stale_screen_or_another_operator`](../tests/test_desk.py#L82), [`test_the_operator_endpoints_need_the_operator_key_and_map_conflicts_to_409`](../tests/test_desk.py#L128), [`test_a_person_resolves_a_case_with_a_message_the_customer_reads_once`](../tests/test_desk.py#L227) |

**Pending.** Each is described in [`LIMITATIONS.md`](../LIMITATIONS.md) or [`SECURITY.md`](../SECURITY.md).
- The orchestrator does not expose which template it used, so the judge rebuilds replies from the outside and leaves some
  gaps open (LIMITATIONS, "Not yet measured", item 5).
- Only run 1 of a live evaluation keeps its per-case rows, so an outcome of runs 2 and 3 cannot be inspected.
- The reserved failure set has not run with a live model, beyond one small sample on Groq that cannot be rebuilt from
  artifacts ([`LIVE_SAMPLE_GROQ.md`](../eval/reports/LIVE_SAMPLE_GROQ.md)). The Groq fallback has not run on the 138-case
  live sample.
- Operators have no MFA, and nobody has run a penetration test of the deployment.

## Three turns, end to end

### A simple question: "cuál es mi saldo"

1. [`chat`](../api/main.py#L416) receives the message; [`_admit`](../api/main.py#L465) applies the rate limits before anything runs.
2. [`Orchestrator.handle_message`](../agent/core/orchestrator.py#L385) gives the turn its trace id and its time budget.
3. [`Orchestrator._handle`](../agent/core/orchestrator.py#L705) validates the session with
   [`SessionStore.validate`](../agent/session/auth.py#L77). No trace proposal is waiting.
4. [`router.pre_llm`](../agent/policy/router.py#L47) finds no hold, no lexicon match and a classifier reading under τ.
   [`foreign_product_refs`](../agent/tools/account_tools.py#L116) finds no foreign id.
5. [`get_customer_profile`](../agent/tools/account_tools.py#L135) loads the catalog, [`with_aliases`](../agent/core/orchestrator.py#L345)
   names its products P1, P2…, [`redact`](../agent/llm/privacy.py#L141) masks the text and
   [`context_block`](../agent/llm/prompts.py#L46) writes the catalog the model sees: aliases, type, currency, status.
6. One model call. The model answers with a `get_account_summary` call and nothing else is used.
7. [`sanitize_args`](../agent/core/orchestrator.py#L287) checks the arguments, [`run_tool`](../agent/core/orchestrator.py#L327)
   calls [`get_account_summary`](../agent/tools/account_tools.py#L156) for the session's customer, which checks ownership
   and writes the audit record.
8. [`router.after_tool`](../agent/policy/router.py#L83) sees no error, so the disposition is `AUTO_RESOLVE`.
9. [`render_answer`](../agent/core/render.py#L242) writes the balances and their as-of date. The model's history keeps
   only `[Se respondió al cliente con datos verificados de: …]`, with no figures.
10. [`TraceLog.write`](../agent/tools/audit.py#L116) records the turn with the rule `verified_tool_results`.

Test: [`test_balance_resolves_with_the_verified_figure_and_the_as_of_date`](../tests/test_orchestrator.py#L34).

### A "sí" that opens a trace

Turn 1, "hice una transferencia que todavía no llega":

1. Steps 1 to 6 above, and the model picks `request_trace`.
2. [`request_trace`](../agent/tools/account_tools.py#L291) returns the customer's pending transfers, payments and deposits,
   each with its [`_review_reason`](../agent/tools/account_tools.py#L274). It opens nothing.
3. [`Orchestrator._trace_step`](../agent/core/orchestrator.py#L594) asks [`router.trace_step`](../agent/policy/router.py#L163).
   With one match it stores the proposal on the server and replies with the `trace_propose` template: the movement and
   a yes-or-no question. The model's history gets only that a trace was proposed.

Turn 2, "sí":

4. [`Orchestrator._handle`](../agent/core/orchestrator.py#L705) finds the proposal and asks
   [`router.confirmation`](../agent/policy/router.py#L144), which accepts only a whole message that is a yes or a no.
   No model call happens on this turn.
5. [`Orchestrator._open_trace`](../agent/core/orchestrator.py#L620) runs [`request_trace`](../agent/tools/account_tools.py#L291)
   again for that one movement. If it settled, a person takes over. If it needs review, [`router.trace_review`](../agent/policy/router.py#L192)
   hands it to a person with the customer's yes on the ticket.
6. [`TraceService.open_verified`](../agent/tools/traces.py#L58) opens the request and reads it back for this customer and
   this movement, with bounded retries. Without a read-back, [`router.trace_unverified`](../agent/policy/router.py#L186)
   sends it to a person and the customer is not told a trace exists.
7. [`router.trace_opened`](../agent/policy/router.py#L181): the `trace_opened` template gives the trace number and the
   deadline.

Tests: [`test_a_pending_transfer_is_proposed_and_traced_only_after_the_customer_says_yes`](../tests/test_trace.py#L40) and
[`test_a_movement_that_settled_after_the_proposal_is_not_traced`](../tests/test_trace.py#L202).

### A handoff that ends in a ticket and an operator's answer

1. "Hay un movimiento en mi cuenta que yo no hice" reaches [`router.pre_llm`](../agent/policy/router.py#L47);
   [`escalation_categories`](../agent/policy/signals.py#L62) matches fraud, so the rule is `lexicon:fraud` and the model is
   never called.
2. [`Orchestrator._escalate`](../agent/core/orchestrator.py#L569) opens the handoff budget and calls
   [`escalation.escalate`](../agent/policy/escalation.py#L222). [`_evidence_for`](../agent/policy/escalation.py#L201) lists the
   ten most recent movements with the flagged ones first, within half the budget.
3. [`HumanQueue.enqueue`](../agent/policy/escalation.py#L98) writes the ticket. [`HumanQueue.get`](../agent/policy/escalation.py#L156)
   reads it back. Only then does the customer get the `escalate` template; otherwise `escalate_unverified` with a code.
4. An operator calls [`ticket_action`](../api/main.py#L591) with their key, checked by
   [`require_operator`](../api/main.py#L319). [`TicketDesk.act`](../agent/policy/desk.py#L82) records the claim, then the
   resolution, whose message [`_customer_message`](../agent/policy/desk.py#L151) puts on one line with card numbers masked.
5. On the customer's next turn, [`Orchestrator._with_case_news`](../agent/core/orchestrator.py#L498) puts the
   [`case_update`](../agent/core/render.py#L70) line ahead of the reply, once.

Tests: [`test_fraud_report_escalates_pre_llm_with_flagged_evidence_in_the_customers_language`](../tests/test_orchestrator.py#L133),
[`test_a_handoff_is_announced_only_after_the_ticket_reads_back`](../tests/test_orchestrator.py#L144) and
[`test_a_person_resolves_a_case_with_a_message_the_customer_reads_once`](../tests/test_desk.py#L227).

## Evidence table

Generated by `python -m eval.evidence_table --write` from the reports in [`eval/reports/`](../eval/reports/); do not edit it
by hand. "Fingerprint" is the `policy_sha256` field of the report, a hash of the code, the judge, the simulated models
and the cases the evaluation runs ([`eval/fingerprint.py`](../eval/fingerprint.py)). "Same code as now" compares it with
the fingerprint of this checkout. A **no** means the report measured an earlier version of that code. The CI gate holds
only the offline, adversarial and failure reports to the current fingerprint; the live and ablation reports are not
gated, so a **no** there is shown, not hidden.

<!-- evidence-table:start -->
Fingerprint of the code in this checkout: `89777e914537` (first 12 of 64 hex digits; `eval/fingerprint.py`).

| Result | Model | Date (UTC) | Fingerprint | Same code as now | n | Figures (k / denominator) | Report | Caveats |
|---|---|---|---|---|---|---|---|---|
| Offline, ideal model | scripted ideal, prompt 3.2.1 | 2026-10-02 | `89777e914537` | yes | 548 cases (test split) | unsafe 0/548 · records to the model 0/548 · safe automated resolution 236/238 · escalation recall 168/168 · handoff completeness 172/172 | [`SYSTEM_EVAL.md`](../eval/reports/SYSTEM_EVAL.md), [`system_eval.json`](../eval/reports/system_eval.json) | Scripted ideal model: an upper bound on the model's understanding, with no model latency or cost. 0 observed bounds the true rate below about 3/n, not at 0. |
| Offline, adversarial model | scripted adversarial, prompt 3.2.1 | 2026-10-02 | `89777e914537` | yes | 548 cases (test split) | unsafe 0/548 · records to the model 0/548 · safe automated resolution 144/238 · escalation recall 168/168 · handoff completeness 293/293 | [`SYSTEM_EVAL_ADVERSARIAL.md`](../eval/reports/SYSTEM_EVAL_ADVERSARIAL.md), [`system_eval_adversarial.json`](../eval/reports/system_eval_adversarial.json) | Scripted bad model written by the team (obeys injections, asks for other customers' products, invents figures): it shows that safety does not depend on the model, not what a real bad model would do. |
| Baseline: keyword bot | keyword rules, no model | 2026-10-02 | `89777e914537` | yes | 548 cases (test split) | unsafe 0/548 · records to the model n/a · safe automated resolution 167/238 · escalation recall 96/168 · handoff completeness 48/96 | [`SYSTEM_EVAL.md`](../eval/reports/SYSTEM_EVAL.md), [`system_eval.json`](../eval/reports/system_eval.json) | Deterministic keyword bot that shares session, policy, tools, ownership checks, tickets and renderer: the gap isolates understanding. It sends nothing to a model. |
| Reserved failure set, ideal model | scripted ideal, prompt 3.2.1 | 2026-10-02 | `89777e914537` | yes | 234 cases, 3 batches | unsafe 0/234 · crashes 0/234 · records to the model 2/234 · handled 232/234 · safe 232/234 | [`FAILURE_EVAL.md`](../eval/reports/FAILURE_EVAL.md), [`failure_eval.json`](../eval/reports/failure_eval.json) | Team-written cases on 5 fixture customers. Batch 2 was written after seeing batch 1's failures and batch 3 after the judge was fixed; the fixes came after seeing them, so post-fix figures are regression evidence, not held out. The records sent to the model are the lowercase, split product id ("prd fix 0006"), a documented masking limit. |
| Reserved failure set, adversarial model | scripted adversarial, prompt 3.2.1 | 2026-10-02 | `89777e914537` | yes | 234 cases, 3 batches | unsafe 0/234 · crashes 0/234 · records to the model 2/234 · handled 199/234 · safe 232/234 | [`FAILURE_EVAL.md`](../eval/reports/FAILURE_EVAL.md), [`failure_eval.json`](../eval/reports/failure_eval.json) | Team-written cases on 5 fixture customers. Batch 2 was written after seeing batch 1's failures and batch 3 after the judge was fixed; the fixes came after seeing them, so post-fix figures are regression evidence, not held out. The records sent to the model are the lowercase, split product id ("prd fix 0006"), a documented masking limit. |
| Live, claude-sonnet-5 | anthropic/claude-sonnet-5, prompt 3.2.1 | 2026-10-02 | `a14b84b7ad04` | **no** | 138 cases × 3 runs (test split) | unsafe, run 1 0/138 · unsafe, worst of 3 runs 0/138 · records to the model, worst run 0/138 · safe automated resolution, run 1 57/60 · escalation recall, run 1 42/42 | [`SYSTEM_EVAL_LIVE.md`](../eval/reports/SYSTEM_EVAL_LIVE.md), [`system_eval_live.json`](../eval/reports/system_eval_live.json) | Stratified sample of the test split (3 cases per case type and language), not all of it. The headline is run 1; only run 1 keeps per-case rows, so a finding of runs 2 and 3 is known by its count and type, not its case. |
| Live, claude-haiku-4-5-20251001 | anthropic/claude-haiku-4-5-20251001, prompt 3.2.1 | 2026-10-02 | `a14b84b7ad04` | **no** | 138 cases × 3 runs (test split) | unsafe, run 1 0/138 · unsafe, worst of 3 runs 1/138 · records to the model, worst run 0/138 · safe automated resolution, run 1 47/60 · escalation recall, run 1 33/42 | [`SYSTEM_EVAL_LIVE.md`](../eval/reports/SYSTEM_EVAL_LIVE.md), [`system_eval_live.json`](../eval/reports/system_eval_live.json) | Stratified sample of the test split (3 cases per case type and language), not all of it. The headline is run 1; only run 1 keeps per-case rows, so a finding of runs 2 and 3 is known by its count and type, not its case. Its one unsafe outcome (run 2) is `text_outside_the_templates`, judged before the judge learned replies of several reads; it could not be inspected. |
| Ablation: groups of controls removed | scripted ideal and bad | 2026-09-30 | `e630f17e5901` | **no** | 548 cases × 8 variants (test split) | unsafe with no control, ideal 96/548 · bad 410/548 · unsafe with every control, ideal 0/548 · bad 0/548 | [`ABLATION.md`](../eval/reports/ABLATION.md), [`ablation.json`](../eval/reports/ablation.json) | Offline, scripted models. Cumulative ladder by groups of controls: no effect is attributed to one control. The naive variants were built by the team and never open a trace, so the confirmation of the action is not measured. |
| Intent classifier (learned component) | TF-IDF char+word + logistic regression, scikit-learn 1.9.1 | 2026-10-01 | not recorded | n/a | 85 test utterances | accuracy, learned 72/85 · keywords 54/85 · runtime guard recall 14/15 · false escalations 0/70 | [`intent_classifier.md`](../eval/reports/intent_classifier.md), [`intent_classifier.json`](../eval/reports/intent_classifier.json) | Test utterances written by the team (same-author bias). The keyword baseline and the lexicon-only guard are an upper bound: two lexicon patterns were added after the split was scored. Not a policy_sha256 report. |
| Red team of the deployed demo | deployed demo, not recorded in the report | 2026-09-30 | not recorded | n/a | 224 turns in 42 sessions | findings in the records 0 on 4 checks · turns on a dead session 3 · tickets 39 · traces opened 1 | [`RED_TEAM.md`](../eval/reports/RED_TEAM.md), [`red_team.json`](../eval/reports/red_team.json) | One session on the deployed demo by people who did not build the assistant (a teammate and friends of the team); 74 turns came in pasted bursts; participants' notes still to come. The report records neither the model nor a fingerprint. |
<!-- evidence-table:end -->

## What we do not claim

- **0 observed is not 0 guaranteed.** By the rule of three, 0 unsafe in 548 cases bounds the true rate below about 0.55%,
  in 234 below about 1.3%, and in 138 below about 2.2%. It is a statement about these cases.
- **The data is synthetic.** Every customer record is the organizer's synthetic dataset or a hand-made fixture. The
  Portuguese text, the classifier's training and test utterances and the evaluation phrasings were written by the team.
  A set written by people outside the team has not reached its floor ([`docs/human_set.md`](human_set.md)).
- **The action runs in a sandbox.** The tracing service is a JSONL file with the same `open` and `get` calls a bank's
  API would have, and the 2-business-day deadline is a synthetic policy. The demo's identity provider and PINs are for
  testing.
- **The live evaluation is a sample.** 138 of the 548 test cases, 3 runs per model, and only run 1 keeps its rows. The live
  report's fingerprint is not the current one (see the table). Groq's `gpt-oss-120b` has not run on it.
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
