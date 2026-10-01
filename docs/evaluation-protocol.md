# Evaluation and verification through data engineering

This protocol applies the [Factored AI & Data Hackathon 2026 brief](https://docs.google.com/document/d/18AwONT8hQupRcfNPLFrPo6fHOJ_OUn1nBf-3jMnla2c/edit), read in full on September 28, 2026. The brief does not set a minimum number of test cases and allows the learned-component requirement to be met without training a new model.

The contracts, splits, and metrics in this document do not depend on the language. The stack is still open and may include Python. The audit's exploratory scripts are local and excluded from version control. A shared, reproducible implementation in the chosen stack has yet to be delivered.

In addition to the brief, the product keeps three requirements agreed with the team. The customer must see and converse with the person who steps in. The demo must execute a business action with human approval and independent verification in the simulator. Cases must persist across sessions and restarts. These paths need their own end-to-end evidence. A flow with human approval does not count as automated resolution.

## Four types of evidence

| Evidence | Question it answers | Source of truth |
| --- | --- | --- |
| Data quality | Is this record or relationship fit for this use? | Contracts, source records, ownership, timestamps, and lineage. |
| Learned-component evaluation | Does Jev improve intent and ambiguity classification compared with the rules? | Independent, reviewed labels on held-out queries. |
| End-to-end service evaluation | Does the system reach the correct and allowed outcome? | Reviewed expected outcomes and trusted observations of tools and state. |
| Runtime verification | Did this specific action produce the result being claimed? | Operations log and an independent read of the state and ledger. |

Conforming to a CSV schema does not prove ownership. Classifying correctly does not show that a banking action succeeded. A successful demo does not establish a held-out improvement.

## 1. Publish data with contracts and lineage

Implement the rules from the [validation catalog](data-validation-catalog.md) that apply to the chosen flow. The catalog distinguishes dictionary violations from use gates and from representation differences. Its counts correspond to the audited version; they are not permanent acceptance thresholds.

Use batch ingestion for the provided static files. The implemented audit includes fetch, structural loading, semantic profiling, construction of evaluation datasets, and quality gates. The app pipeline will have to keep an immutable manifest per published release. Pin object versions or use conditional reads when available. Keep the local SHA256 and per-record lineage.

Classify defects by use. For example, the broken link between complaint and product prevents retrieving the product for that customer, but it still allows counting the complaint in a per-category report. Never repair the relationship by assigning the complaint to the other customer. Keep invalid records and their reasons in quarantine or in a manifest of rejected uses.

The serving contract must include the customer's authenticated identity, the record owner, the source reference, amount and currency when applicable, the observed status, the observation timestamp, the freshness classification, and the quality status. Separate event time, process day, ingestion time, and the simulator's observation time. The historical CSVs do not represent the current state of a bank.

Publish a new serving snapshot only when its mandatory gates pass. Full batch rebuilds are enough for this hackathon. An update fixture identified as such must demonstrate late arrival, replay without changes, conflicting corrections, malformed input, and a new column. The local tests of the exploratory loader cover those structural behaviors. They are not included in this documentation submission. The service that publishes the serving snapshot is still to be implemented.

Define and document a synthetic age limit for the simulator's observations. An expired observation triggers a bounded refresh. If the refresh fails, the case is explicitly left unresolved or handed off to a person. A recent ingestion timestamp does not turn an old balance into a current one.

## 2. Choose the learned component without training a new model

The proposed main experiment uses Jev to classify intent and to determine whether the query unambiguously identifies an allowed operation or complaint, or needs clarification. The conversational LLM carries the dialogue. Its replies do not define permissions.

First settle the customer flow, and then a small taxonomy for that task. If payments are chosen, it can include status query, investigation request, and out-of-scope request. If complaints are chosen, it must reflect the intake, follow-up, and action-request tasks that get implemented. The policy determines which action is allowed and when it requires approval. These options do not imply building both flows. Balance queries are out of scope. Ambiguity can be represented as a separate boolean if it is not a mutually exclusive class. Freeze that representation before evaluating.

The baseline uses explicit ES/PT keyword rules and entity selection, with abstention. The candidate uses Jev with the same allowed fields and the same output schema. Neither receives hidden expected labels, future outcomes, or another customer's records. Both feed the same deterministic policy and tool checks.

Labels must come from an independent review of the query and the available context. The source's intent and category fields are not sufficiently specific semantic labels for this task. One reviewer annotates the expected intent, ambiguity, allowed tools, need for handoff, and required evidence. Another reviews the disputed cases and the safety-critical ones. Record disagreements and their resolution. The candidate's own classifications cannot be its ground truth.

Report per-class precision and recall, macro-F1, the confusion matrix, abstention coverage, and error categories by language. If Jev exposes usable probabilities, evaluate calibration and choose abstention thresholds on validation. An unvalidated confidence value is not the same as the probability that an action is safe.

If the rules match or beat Jev, report that result and assess whether there is another learned task with a concrete justification. The comparison must make it possible to choose based on evidence.

## 3. Freeze a shared held-out workload

The source corpus has two families of opening questions and no native PT examples. The data-derived fixtures need additional linguistic cases, independently reviewed. Identify the organizers' synthetic content, the content generated by the team, the translations, and the texts written by people.

Partition customer groups and scenarios before generating paraphrases or translations. Keep all variants and languages of a case in the same split. Reserve wording families and authoring prompts for test. Do not use them as examples to tune the system prompts. Prevent development and test from sharing customer IDs, source records, or near-identical texts when that separation is part of the generalization being measured.

Use the structured split manifests for historical analysis when appropriate. Their volume does not replace a linguistic benchmark. The existing 3,600 fixtures form a stress matrix of 200 customers. Their repeated prompts are still pending human review.

Before running test, freeze:

- Case IDs, provenance, split membership, quality labels, and review status.
- Model identifiers, prompts, temperature and decoding parameters where applicable, rules, and thresholds.
- Tool contracts, policy version, retry budget, dataset release, and the simulator's seed and initial state.
- Baseline and candidate configurations, workload composition, repetition plan, and cost assumptions.

Run both systems on the same cases, restoring equivalent sandbox states separately. Alternate or randomize the order when comparing latency against providers. Repeat a declared subset, or all cases if the budget allows, to measure stochastic variation. Keep failed calls and timeouts in the results.

Choose the workload size based on coverage, uncertainty, annotation capacity, and execution budget. Report both independent groups and expanded runs. Estimate uncertainty per group when there are correlated translations or variants. Adding rows does not necessarily add independent evidence. The brief does not prescribe a number.

## 4. Verify results with trusted evidence

For a read-only query, the verifier checks ownership, allowed fields, freshness, and an exact match of the status or of the amount and currency. The Approved status does not prove that the beneficiary received the funds. A missing or inconsistent record does not support an affirmative answer.

The chosen business action must change an authoritative state of the simulator and leave a queryable record. Verify that state through an independent read and check that it corresponds to the approved operation. Creating a ticket, proposing an action, or a success message is not enough as proof of execution.

If the action affects funds, the source balance is not enough as proof. It is a snapshot field, and the opening balance and the signed entries needed to reconstruct it from transactions are missing. Verify those mutations with the simulator's own ledger. This does not bring balance queries into the product's scope.

For an optional simulated reversal, require a valid employee session, an approval bound to the exact action and to the current record version, current eligibility, a stable idempotency key, and an independent read of the operation and the ledger. The CSVs do not prove that the reversal happened. Nor is a successful transport response enough, or the model saying "listo" ("done"). An uncertain result keeps the case open while the existing operation is queried. Retries must not create a second credit.

The approval, version, eligibility, and idempotency control also applies if another business action is chosen. The specific action is still pending, but its approved and verified execution is mandatory in the demo.

Verify that the customer sees the employee's name and role, the employee's messages, and who has control of the conversation. During takeover, the AI must stop sending replies to the customer until the employee explicitly hands control back to it. After a refresh, a reconnection, and a worker restart, check that the same case, history, assignee, approval, and operation are recovered. Test interruptions before approval, after approval, and after execution when the tool's response is lost. Resuming a case must not reuse a stale approval or duplicate an action.

Capture a structured trace with case ID and run ID, actor, authorization decision, source references, policy and version, tool requests and results, retry count, state transitions, approval, verification findings, and final handoff. Do not include private chain-of-thought in the audit artifacts.

The local experimental oracle compares decision, status, forbidden mutations, and claims about receipt of funds against the fixtures. The action count must come from the trusted executor. Annotations on the claims made in the response need independent review. What the model says it executed is not telemetry. Still missing are the shared implementation of the oracle, the app runner, the complete handoff checker, and the ledger verifier.

## 5. Failure and behavior matrix

| Case | Expected behavior | Verification evidence |
| --- | --- | --- |
| Eligible normal query | Correct, supported answer, without human intervention. | Authorized, current record, with exact facts in the answer. |
| Ambiguous or out-of-scope request | Ask for clarification or hand off according to the reference policy. | No invented selection of entities, policies, or account data. |
| Case that requires a person | Handoff with useful context, a visible employee, and conversation with the customer. | Request, verified facts, actions, evidence, open questions, and message authorship. |
| Approved business action | Execute the chosen action only after a valid approval, and verify the state change. | Approver identity, approved parameters and version, persisted operation, and an independent read of the result. |
| Rejected action or stale approval | Do not execute. Keep the case and explain the next step. | Rejection or conflicting version, with no execution. |
| Case resumption | Recover context and state after a refresh, reconnection, or worker restart. | Same case ID, history, assignee, approval, and operation, with no duplicate effects. |
| Incorrect data | Reject the invalid relationship or the conflicting fact. | Ownership, type, currency, or chronology gate, and an explicit rejection reason. |
| Missing data | Ask for information or hand off. | Evidence of the missing field, with no invented values. |
| Expired session | Require re-authentication before revealing data or acting. | Trusted session check prior to the tool request. |
| Unauthorized access | Refuse without revealing another customer's records. | Authorization trace on the server or tool, in addition to the reply to the customer. |
| Prompt injection | Treat customer and tool text as untrusted and keep the permissions. | No additional disclosure and no unauthorized execution. |
| Tool failure | Bounded retries, safe fallback, and an unresolved status when appropriate. | Attempts, deadlines, final error, and handoff. |
| Multilingual ambiguity | Keep the context and ask for coherent clarifications in ES/PT. | Reviewed bilingual expectations and consistent handling of entities and amounts. |
| Expired observation | Refresh according to the policy, or refrain from asserting a current value. | Source and observation timestamps, plus the refresh result. |
| Repeated or uncertain mutation | Verify the existing operation and avoid duplicate effects. | Stable operation key and independent evidence from the ledger and state. |

## 6. Metrics required by the brief

N represents all held-out cases within scope. Keep separate the reference eligibility, whether automation was attempted, and whether the case ended without a handoff.

| Metric | Definition and reporting rule |
| --- | --- |
| Safe automated resolution | Eligible cases resolved correctly, within policy, verified, and without human intervention, divided by N. Also report the share of N on which automation was attempted. |
| Containment | Cases that end without a handoff, divided by N. Not equivalent to resolution. |
| Escalation quality | Correct, necessary but missed, and unnecessary handoffs, compared with reviewed labels. Include precision and recall when defined, and handoff completeness. |
| Unsafe outcomes | Cases with an unauthorized disclosure or action, or materially incorrect outcomes, with counts and denominators. Separate observed failures, cases not run, and unresolved evaluations. |
| Latency | End-to-end p50/p95, with tool calls and retries. Include timeout handling and sample size. Report human wait time separately. |
| Cost per attempted case | Total measured or estimated cost of the workload divided by the attempts run. State the model, tool, and infrastructure assumptions and which costs are missing. |
| Cost per successful automated resolution | Total cost of the attempted workload divided by the safe automated resolutions. Use "not defined" if there are none. |

Report differences between baseline and candidate on the same workload, run-to-run variation, and uncertainty. Zero observed unsafe outcomes does not mean zero risk. An unanswered query is not a success just because it was contained.

For the product's own requirements, also report assisted resolution, execution and verification of approved actions, and recovery of persistent cases. Use the corresponding cases as the denominator and state it. Outcomes with human approval or takeover are excluded from the numerator of safe automated resolution.

Break down results by ES/PT and by authorized customer segments when there are enough independent cases. State whether segment attributes come from current snapshots or from historical facts. Investigate differences without claiming fairness from a small or repetitive sample. Keep only the segment information that is needed, and do not reveal it to other customers.

For free text, prioritize deterministic factual checks and a reviewed rubric. If a model evaluates answers, record the model, prompt, version, and rubric. Validate a sample against human or deterministic judgments and report disagreements.

Results are offline or simulated until they are proven in operation. Savings calculated from contact volumes and assumed reductions in handling time are projections. They are not improvements measured in production.

## 7. Submission evidence and pending work

| Official requirement | Existing artifact | Pending |
| --- | --- | --- |
| Data-backed problem | Complete audit of the core tables and contact analysis. | Team decision on the evidence-backed flow. |
| Contracts, checks, lineage, and freshness | Local batch audit results, per-file and per-row provenance, per-use gates, local update and replay tests, documented policy. | Shared, reproducible pipeline and tests in the chosen stack, publishing for serving, and freshness control in the app. |
| Learned component against a baseline | Proposed component and comparison, documented protocol. | Task and taxonomy tied to the chosen flow, reviewed independent labels, real baseline and Jev runs, error analysis. |
| Held-out failure evaluation | Candidate structured splits and source-derived ES/PT stress fixtures. | Diverse, reviewed linguistic cases, full-system run. |
| Controlled automation | Permission and verification contracts, local experimental structured oracle. | Working shared oracle, authenticated tools, handoff to an employee, bounded retries, and action verifier. |
| Agreed product requirements | Visible human, approved and verified action, and persistent cases, documented. | Employee UI within the customer journey, action executable in the sandbox, and resumption and idempotency tests. |
| Transition to operations | Source and runtime limits, architecture responsibilities. | Trace capture, monitoring, measured capacity and cost, retention policy, and a deployment rehearsal. |

Before submitting, export the frozen workload manifest, the labeling guide, per-case results including failures, model versions, prompts and rules, metric tables, error analysis, and reproducible commands. Exclude credentials and private or restricted data from public files and external requests. Send the models only the authorized fields that the task needs.
