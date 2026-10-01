# Plan for the Factored AI hackathon

Updated on September 28, 2026, after reading the [official brief](https://docs.google.com/document/d/18AwONT8hQupRcfNPLFrPo6fHOJ_OUn1nBf-3jMnla2c/edit) in full and auditing the provided dataset.

## Goal and grounding in the data

Build an AI banking service that follows the Understand → Decide → Act → Verify → Escalate cycle. The system must understand the query, choose an allowed action, execute it through tools, verify the result, and escalate when appropriate. The submission includes a customer app and an employee console, connected through persistent cases.

The original demo was "Mi transferencia no llegó" ("My transfer did not arrive"), with a simulated reversal approved by a person. The audit does not allow us to demonstrate demand for that contact reason. The 171,321 customer transcripts talk about balances, and none of them mentions transfers. The dataset contains payment statuses, but it has no settlement sequence and no beneficiary ledger.

We rule out balance queries as the problem to solve in this submission. The transcripts repeat only 42 customer texts derived from two opening questions. That repetition does not justify prioritizing balances on the basis of demand.

The choice of the main use case is still pending, between payments and complaints. Transactions make it possible to verify statuses; complaint categories provide evidence of problems recorded in the synthetic corpus. Their limitations are documented in the audit. The chosen flow must include visible human participation, an approved and verified business action, and case persistence. Reversal is a candidate action in the simulator. We can choose another one, but a status query or the creation of a ticket on its own does not complete the agreed scope.

## Product requirements we keep

- The customer sees the person who steps in, their name and role, and their messages within the conversation. The handoff preserves the context. The console lets the employee take the case, converse, approve or reject, and hand control back to the automation.
- The demo executes at least one business action that changes the state of an operation or product in the banking simulator. It requires explicit human approval and independent verification of the result. Showing a proposal or logging a ticket does not count as executing that action.
- Cases persist across sessions and survive a refresh, a reconnection, and a worker restart. The conversation, assignee, approvals, operation, evidence, and timeline are preserved. Resuming must not duplicate effects.

These requirements stand even if the use case and the technologies change. The path with human intervention and an approved action is evaluated separately from automated resolution, because it requires a person.

The results and their limits are in [dataset-audit.md](dataset-audit.md). The evaluation process is in [evaluation-protocol.md](evaluation-protocol.md).

## What the brief requires

- A coherent, data-backed banking customer-service flow, with normal resolution, ambiguity or out-of-scope requests, and human intervention.
- Interactions in Spanish and Portuguese, with their coverage limitations documented. English is not mandatory, and we propose removing it from the committed scope.
- Reproducible data preparation, contracts, quality checks, lineage, and an update and freshness policy.
- At least one learned component evaluated against an appropriate baseline. Training a new model is optional. We keep the original decision to use a pretrained component.
- Baseline and candidate on the same held-out workload, with incorrect or missing data, expired sessions, unauthorized access, prompt injection, tool failures, and multilingual ambiguity.
- Correct and unsafe outcomes, handoff quality, latency, cost, sample size, and limitations. Containment must be distinguished from safe resolution.
- Traces, bounded retries, safe fallback, reproducible setup, access controls, and a concrete plan to operate the solution.

The brief does not set a minimum number of test cases. The size and coverage of the workload must be justified. Nor does it require streaming, multiple agents, dashboards, or real banking integration. It allows sandbox tools and a trusted test session.

## Constraints, architecture, and pending technology choices

The stack is still open. TypeScript, Turborepo, and TanStack Start were initial proposals. Python is also an option for the backend, data engineering, and evaluation. The exploratory audit does not determine the language of the product or that of the final pipeline.

| Area | Decision |
| --- | --- |
| Timeline | Ten days, planned from September 28 to October 7, 2026. The official submission time is still to be confirmed. |
| Capacity | Three people, two hours per business day and between four and six hours per person on each weekend day. Between 72 and 84 person-hours. |
| Frontend | Web chat inside the simulated banking app. TanStack Start is an initial option, pending confirmation. |
| Repository and languages | Organization and tooling to be defined. Evaluate TypeScript, Python, or a combination, depending on the work of each component. Turborepo remains a candidate if it fits the chosen stack. |
| Architecture | Modular monolith with vertical slices, and ports/adapters where they provide isolation. |
| Agent behavior | Hybrid. Bounded AI investigation, and explicit persisted rules for transitions with consequences. |
| Cases | Asynchronous and resumable, with a timeline and in-app updates. |
| Human control | Approve or reject actions, take over the conversation, and explicitly hand control back to the automation. |
| Identity | Pre-created accounts, trusted sessions, and authorization on the server and in tools. No sign-up or onboarding. |
| Financial authority | Routine investigation can be automatic. Financial mutations require human approval and are simulated. |
| AI | Jev via OpenRouter as the candidate classifier, and a conversational LLM for the dialogue. The integration, the schema, and the specific models are still to be verified. |
| Hosting | Cloudflare and Vercel are initial candidates. Review the choice together with the languages, jobs, and runtime before deployment. No credits are available. |
| Database | PostgreSQL or MySQL. Choose data access and ORM after the language. Drizzle was a proposal for TypeScript. |

## Product behavior

The customer logs in and asks, in ES or PT, about an operation or a complaint, depending on the flow chosen. The system retrieves only the allowed data, asks for clarification when the selection is ambiguous, and shows progress backed by recorded events. It must state whether a data point comes from a historical snapshot or from the simulator. It cannot claim that a payment settled or that a complaint was resolved without evidence.

The customer sees who has the case, when an employee takes over the conversation, and which messages come from that person. The interventions stay in the same history and remain available when the customer returns to the app. The states for awaiting approval, execution, verification, and resolution must reflect persisted events.

The employee sees the request, the verified facts, the actions taken, the evidence, and the open questions. During the takeover, the AI stops replying to the customer, although it can prepare internal summaries. Approving actions and controlling the conversation are separate permissions.

The chosen action must run in the sandbox banking service and change its authoritative state. The approval is bound to the action, its parameters, and the record version. It includes amount and currency when applicable. The executor re-checks eligibility, uses a stable idempotency key, and independently queries the result. For a reversal, it verifies the operation and the ledger. If the result is uncertain, the case stays open with verification pending. Before retrying, it must query the existing operation.

Persist the case before dispatching asynchronous work. On resume, recover the state, the human assignment, the current approval, and the operation identifier. The demo must show that an open case can be picked up again and that an action already executed is not applied again because of a refresh or retry.

Model-generated text cannot grant access, change policies, or declare an action successful without verifying it.

## Data engineering as a core deliverable

The initial audit was run with local exploratory scripts, excluded from version control. Its results are documented in [dataset-audit.md](dataset-audit.md). It inventoried the 13 tables and processed 6,311,493 rows from 5,516 files. It includes 11 complete tables and explicit samples of digital events and campaign sends. An independent read matched the row count and the SHA256 of every analyzed file.

The [validation catalog](data-validation-catalog.md) checks the dictionary against the observed errors and defines ingestion checks per use. It covers primary keys, additional `UNIQUE` constraints, ownership, chronology, lossless parsing, and the evidence that is missing to operate on amounts.

The final pipeline must cover these stages, in whichever language the team chooses:

1. Inventory and download a declared set of source objects.
2. Parse and validate files, recording schema, keys, counts, hashes, and lineage.
3. Separate exact duplicates, conflicting keys, malformed records, and relationships that cannot be used.
4. Verify ownership, chronology, label meaning, missing evidence, and snapshot limits.
5. Publish serving and evaluation datasets with an explicit purpose, along with their manifests.
6. Verify replay, updates, isolation between cohorts, and per-use quality gates.

The local scripts made it possible to validate this process, but an implementation that the team can run from a clean checkout has yet to be added to the repository. We keep the audit's manifests, SQL queries, and results in the local environment. This submission includes only Markdown documentation. The shared implementation and its commands will be defined once the stack is settled.

Findings that affect the design:

- All 44,570 non-null references from complaints to products point to another customer's products. That join must be blocked.
- All 67,095 complaints have an empty reference to the originating interaction. They cannot serve as labels linked to conversations.
- There are 128,453 interactions that predate the customer's registration. They are excluded from the candidate historical cohorts.
- Only 2,973,699 transactions pass both chronology checks, customer registration and product opening.
- The transaction → product → customer ownership chain is consistent across all 4,425,008 transactions.
- Customers and products are single snapshots. Their current balances and statuses cannot be used as historical features at the start of a query.
- All transcripts are in Spanish and repeat 42 variants of customer text, derived from two opening questions. The source's general categories do not reliably represent the visible intents.

Keep the raw records for diagnosis and block the affected use. A complaint with a wrongly linked product can still count in a volume report, but it cannot authorize a lookup of that product.

Use batch processing for this static source. Each published release needs a source manifest and a dataset version. Test late arrivals, conflicts, new columns, truncations, and replay with fixtures identified as such. Keep event time, ingestion time, and the simulator's observation time separate. A new import does not make an old balance current.

## Architecture and rationale

Organize the code by use case and isolate external systems behind interfaces. [Vertical slices](https://www.jimmybogard.com/vertical-slice-architecture/) keep the changes for one feature together. [Ports and adapters](https://alistair.cockburn.us/hexagonal-architecture) make it possible to test banking rules without depending on providers, persistence, or UI.

The proposed logical separation does not depend on the language and does not yet fix the folder structure:

| Component | Responsibility |
| --- | --- |
| Web | Customer and employee interfaces. |
| Application and domain | Use cases, invariants, permissions, and transitions. |
| Worker | Background execution and case resumption. |
| Ports and adapters | Integrations for persistence, the AI provider, and the banking simulator. |
| Contracts | Validation of requests, events, evidence, and results. |
| Data pipeline | Ingestion, quality, lineage, and snapshot publishing. |
| Evaluation | Reviewed workloads, oracles, metrics, and manifests. |

Web and worker must use the same business rules through whatever handlers or contracts the chosen stack allows. If we combine languages, we must define how the contracts between them are validated. The banking rules do not depend on the web framework, the ORM, the AI provider, or the hosting SDK. The interfaces have concrete purposes, such as retrieving authorized records, persisting cases, or executing banking operations. Common UI helpers do not need an adapter layer.

| Choice | Reason | Cost or limitation |
| --- | --- | --- |
| Modular monolith | Shared contracts and fewer deployments for three people. | Imports and responsibilities must be kept under control as the code grows. |
| Vertical slices | Each team member can implement a complete behavior. | Shared invariants need a single implementation. |
| Selective adapters | They make it possible to replace external providers with controlled test implementations. | They add some interfaces and contract tests. |
| Persisted workflow | Waits on humans and restarts do not lose cases. | Concurrency, retries, and stale approvals must be handled. |
| Quality before serving | Prevents invalid joins and unsupported facts from reaching the model. | Some records or features are left out of use. |
| Independent verification | Every claim of success requires an observed result. | A verification failure must be an explicit case state. |

The worker defines a logical responsibility. Choose the jobs or workflow mechanism together with the language and hosting, and keep its orchestration separate from the business handlers. Task dispatch must be reliable with respect to the persisted transitions. Do not build a generic workflow engine.

SQLite is local analytical storage for the audit. It does not determine the app's database. Record the relevant decisions in short ADRs that explain the problem, the choice, the alternatives, and its verification.

## Learned component and baseline

The task proposed for Jev is to classify intent and ambiguity. Use independently reviewed ES/PT queries and a small taxonomy tied to the chosen flow. Do not train or evaluate semantic intent using `reason_category` as the ground truth for the repetitive transcripts.

Compare:

- A deterministic baseline of keywords and entity selection, with explicit abstention.
- Jev with the same allowed context and the same output contract.

Both use the same policy layer, tools, and verifier. Financial authority stays outside the classifiers. Choose confidence or abstention thresholds on validation, and report the relationship between coverage, errors, and handoffs.

A structured output does not show that the model got it right. Report errors by class and language. Measure calibration only if the provider exposes probabilities with usable semantics. Do not promise improvements before measuring them.

The committed scope does not need a tabular model trained by the team. The historical datasets serve for descriptive analysis and a possible future experiment. We will not spend the ten-day budget just to demonstrate training.

## Held-out evaluation and runtime verification

Follow [evaluation-protocol.md](evaluation-protocol.md). Keep separate the evidence for data quality, classification, service outcomes, and the verification of each action.

Artifacts produced during the local audit:

- Structured partitions with no shared customers, with 245,074 development interactions, 15,839 validation interactions, and 15,675 test candidates.
- 200 payment contexts derived from the source, expanded into 3,600 ES/PT fixtures with nine variants. They are exploratory and must be adapted or replaced if the chosen flow requires other evidence.
- A local experimental oracle for structured decisions, disclosure of allowed statuses, forbidden mutations, and unsupported claims about receipt of funds.

These artifacts are not yet model evaluation results. The 3,600 fixtures correspond to 200 independent contexts, use templated language, and are awaiting linguistic review. They do not replace diverse held-out queries, nor do they prove linguistic generalization.

Create independently reviewed language cases. Separate customer groups, scenarios, and wording families before producing variants. Keep the translations of the same case together. Freeze the dataset, labels, policies, prompts, model versions, thresholds, retry budget, and seeds before comparing. Run both systems on the same cases and with equivalent initial sandbox states. Include failures and declared repetitions.

The matrix must cover normal resolution, ambiguity, visible human intervention, incorrect or missing data, expired sessions, unauthorized access, prompt injection, tool failures, ES/PT ambiguity, and expired observations. For the agreed action, test approval, rejection, stale approval, execution, uncertain verification, and retries without duplicate effects. For persistence, test refresh, reconnection, and worker restart without loss of context or permissions.

Report:

- Safe automated resolution over all in-scope cases, and the coverage of automation attempts.
- Containment, separately from resolution.
- Correct, missed, and unnecessary escalations, together with the usefulness of the handoff context.
- Unauthorized disclosures or actions and materially incorrect outcomes, with counts and denominators.
- End-to-end p50/p95 latency, including retries and tool failures.
- Cost per attempted case and per successful automated resolution. If there are no successful resolutions, the second cost is reported as "not defined".
- Sample size, number of independent cases, run-to-run variation, and differences by language and authorized segments.

Use deterministic tool and state checks to verify facts and actions. If a model evaluates free text, validate a sample against independent human judgments or deterministic checks and report disagreements. Zero observed failures does not mean zero risk. Offline and simulator results are not improvements measured in production.

## Responsibilities and ten-day schedule

Reserve between 18 and 21 of the 72 to 84 person-hours for evaluation, integration, fixes, and rehearsal. Proposed split:

| Owner | Main work |
| --- | --- |
| A | Data pipeline, quality and freshness contracts, labels, held-out workloads, and evaluation reports. |
| B | Workflow, AI and tool adapters, authorization, approvals, verification, and deployment. |
| C | Both minimal interfaces, ES/PT, conversation handoff, timeline, and demo. |

All three review labels and errors. Reuse UI components and limit the employee console to a queue and the case detail. Assign names and adjust tasks according to each member's experience.

| Day | Team capacity | Deliverable |
| --- | ---: | --- |
| Monday, September 28 | 6 hours | Review the audit and the brief, choose the data-backed flow, evaluate languages, hosting, database, and Jev, define contracts. |
| Tuesday, September 29 | 6 hours | Bring the reproducible pipeline into the chosen stack, prepare the snapshot and quality gates, pre-created sessions, and a minimal UI structure. |
| Wednesday, September 30 | 6 hours | Deterministic baseline and a first bounded flow of AI investigation and evidence capture. |
| Thursday, October 1 | 6 hours | Initial flow of customer → visible employee → approval → executed action → verified result. |
| Friday, October 2 | 6 hours | Persistent asynchronous cases, takeover, retries, and update and freshness behavior. |
| Saturday, October 3 | 12 to 18 hours | Complete ES/PT, reference labels, the normal, ambiguous, and human flows, and the failure matrix. |
| Sunday, October 4 | 12 to 18 hours | Integrate traces and evaluators. Freeze scope, workloads, prompts, and rules. |
| Monday, October 5 | 6 hours | Run the baseline and the candidate on the same held-out set and test authorization. |
| Tuesday, October 6 | 6 hours | Analyze failures and differences between groups, test recovery, and finalize the architecture and limitations. |
| Wednesday, October 7 | 6 hours | Reproduce artifacts, rehearse, verify the deployment, and prepare the submission. |

The audit is already finished, with the documented coverage. Still missing are the shared reproducible pipeline, the app, the model comparison, and the final linguistic benchmark. If time runs short, cut English, visual details, dashboards, additional provider comparisons, and additional actions. Keep the visible human, one approved and verified action, the persistent cases, and the data and evaluation work the brief requires.

## Privacy and transition to operations

Use only data authorized by the organizers and permitted external resources. The provided corpus is synthetic. Separately identify the language generated by the team, the fixtures with injected defects, and the sandbox state. Do not include credentials, private records, or restricted data in public submissions or in requests to models.

Limit the provider's inputs to the query and the allowed facts. Verify identity and ownership in services and tools. A customer ID does not authenticate a person. Log bounded retries, rejection reasons, verification failures, and handoff outcomes. Define trace retention, deletion, access, and redaction before deployment.

Measure concurrency, provider limits, job recovery, latency, and cost on the declared workload. Document monitoring and the remaining work for a real bank, such as identity integration, policy owners, reliable up-to-date data, security review, human operations, and a broader evaluation. The brief neither requires nor authorizes real money movements.

## Exclusions and pending decisions

Out of scope: balance queries as a use case, user sign-up, onboarding, password recovery, voice, WhatsApp, email, LLM fine-tuning, real banking mutations, credit decisions, other banking flows, business analytics, and microservices. Batch updates are sufficient. Streaming earns no points by itself.

Still to be settled: the evidence-backed flow, the specific business action, languages and frameworks, repository tooling, database, hosting, runtime, conversational model, reviewed taxonomy, workload size, inference budget, named owners, retention policy, and the official submission time. The brief has already resolved the questions about languages, training, failure scenarios, and mandatory metrics.
