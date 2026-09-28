# Factored AI hackathon plan

Updated: September 28, 2026. Status: team review draft based on the planning interview.

## Objective

Build a customer-facing banking assistant that resolves payment inquiries through **Understand → Decide → Act → Verify → Escalate**. The main customer request is: **"My transfer hasn't arrived."**

The product combines a simulated banking app with an employee console. The AI investigates and takes permitted actions, requests human approval for financial actions, and checks the outcome before reporting success. Cases continue asynchronously after the customer leaves the chat.

The distinction we want judges to see is a complete, evidence-backed resolution workflow. The demo must show when automation works, when a person takes control, and what happens when an action cannot be verified.

## Constraints and confirmed decisions

| Area | Decision |
| --- | --- |
| Time | Ten days, planned for September 28 through October 7, 2026. Confirm the official submission time. |
| Team | Three people, two hours each per weekday and four to six hours each per weekend day. |
| Capacity | Approximately 72–84 person-hours. Reserve 18–21 for integration, evaluation, fixes, and rehearsal. |
| Language | Spanish, English, and Portuguese are mandatory. |
| Customer channel | Web chat inside a simulated banking app. |
| Employee experience | Approval console, evidence review, conversation takeover, and return to automation. |
| Framework | TanStack Start, full TypeScript, Turborepo. |
| Architecture | Modular monolith, organized by vertical slices, with selective ports and adapters. |
| Execution | Hybrid AI investigation and an explicit persisted workflow controlling consequential transitions. |
| Background work | Separate logical worker for asynchronous processing. Physical deployment depends on the hosting choice. |
| AI | Jev through OpenRouter for classification and routing, plus a conversational LLM. No custom model training. |
| Accounts | Pre-created customer and employee accounts. No registration or onboarding. |
| Data | A curated, reproducible subset of the supplied synthetic dataset, with clearly identified simulator additions. |
| Hosting | Cloudflare or Vercel are candidates. No hackathon cloud credits are available. |

PostgreSQL with Drizzle is the proposed database default. The team accepted MySQL or PostgreSQL as options but has not explicitly finalized the database or ORM. The conversational model, workflow runtime, UI library, and authentication library are also open implementation choices.

## Product scope

### Customer banking app

- Sign in with a pre-created demo account.
- View account balances and transactions belonging to that customer.
- Start a payment inquiry from chat or a selected transaction.
- Converse in Spanish, English, or Portuguese, including switching language without losing case context.
- View a persistent case timeline and current status.
- Leave the chat and return to the same case.
- Receive an in-app update after a verified outcome or when more information is needed.

Timeline entries must correspond to recorded events, such as payment identified, status checked, awaiting approval, and reversal verified. Do not invent progress messages while waiting for tools.

### Employee console

- Review cases awaiting investigation, approval, or verification.
- See the transcript, relevant records, proposed action, policy checks, and classification output.
- Approve or reject a specific action.
- Take over the conversation and ask the customer for information.
- Explicitly return the conversation to automation.
- Inspect the action history and verification evidence.

During takeover, the AI pauses customer-facing replies. It can prepare internal evidence and summaries. Approval and conversation ownership are separate controls; taking over a chat does not itself authorize a reversal.

### Automation boundary

The AI may identify a payment, retrieve authorized records, ask clarifying questions, explain a recorded status, open a routine trace, and track progress.

Retries, reversals, and refunds require employee approval. Only the reversal path is part of the required implementation. Mentioning other financial actions in the permission model does not add them to the build scope.

AI scores inform routing. They cannot override authorization, eligibility checks, or approval requirements. Uncertain evidence must remain uncertain in the customer response.

## Demo scenarios

| Scenario | Expected behavior | Proof shown to judges |
| --- | --- | --- |
| Inquiry resolved automatically | Identify the selected payment, retrieve its status, and provide a supported explanation. | Source record and timeline show why the answer is justified. |
| Failed transfer eligible for reversal | Investigate, propose reversal, wait for an employee, execute the approved action, then verify. | Approval record, operation ID, transaction state, and ledger/balance reconciliation. |
| Ambiguous payment | Ask for missing information; escalate when the payment or outcome cannot be established. | No invented association or financial action; employee can take over. |
| Reversal outcome uncertain | Simulate a timeout or inconsistent result after approval. Keep the case open and recheck the existing operation. | Customer sees verification pending; employee is alerted; no duplicate reversal occurs. |

The fourth scenario is a controlled failure mode of the reversal flow, not a separate product feature. All scenarios should be repeatable through a development/demo reset mechanism that is unavailable to ordinary customer accounts.

## Data and simulator

The supplied links are documentation PDFs:

- [Complete data dictionary](https://drive.google.com/file/d/***REMOVED***/view)
- [Dataset summary](https://drive.google.com/file/d/***REMOVED***/view)

The documentation describes approximately 19 million synthetic rows across 13 tables for Mexico, Colombia, and Argentina, covering June 2023 through June 2026. The initial review accessed the read-only dataset and sampled early daily CSV partitions. Observations from those partitions are not a complete dataset audit.

Useful records include customers, products, transactions, interactions, transcripts, complaints, and service agents. Sampled transactions included Approved, Declined, Pending, and Reversed statuses. Source text is Spanish; the sample does not establish an English or Portuguese evaluation corpus. Sampled intent labels were broad and transcripts showed substantial templating.

Material limitations:

- There is no documented live banking mutation API or settlement timeline.
- Complaints have no direct transaction foreign key. Customer, product, and time can suggest a match but cannot prove one.
- A transaction marked Approved does not, by itself, prove that the recipient received the funds.
- No bank policy knowledge base was identified in the supplied material.

Import only the records needed for the demo customers and cases. Preserve source IDs and record which fields come from the dataset. Add explicit simulator records for settlement events, ledger entries, payment operations, and action outcomes. These additions must be identifiable as simulated rather than presented as original dataset evidence.

Proposed default: use one fictional bank with a small, versioned demo policy. Define reversal eligibility from simulator evidence, including an original debit, lack of settlement, and absence of a previous reversal. Do not infer eligibility merely from a Pending or Declined label. Use exact decimal or minor-unit amounts, with currency kept explicit.

Keep access credentials in local environment configuration or the hosting secret store. The plan, fixtures, logs, and repository must not contain the credentials supplied with the data documentation.

## Architecture and rationale

Use vertical slices for feature organization and selective hexagonal boundaries for external dependencies. [Vertical slices](https://www.jimmybogard.com/vertical-slice-architecture/) group code around use cases. [Ports and adapters](https://alistair.cockburn.us/hexagonal-architecture) keep application rules independent of the systems that invoke them and the services they call.

Proposed layout:

```text
apps/
  web/                         # TanStack Start; customer and employee routes
  worker/                      # Async entry points and runtime integration
packages/
  cases/
    investigate-transfer/
    approve-reversal/
    execute-reversal/
    verify-reversal/
    take-over-conversation/
    domain/                    # Shared invariants and case transitions
    ports/                     # Interfaces required by use cases
  adapters/
    persistence/
    openrouter/
    banking-simulator/
  contracts/                   # Validated requests, responses, and events
  ui/                          # Shared presentation components
docs/
  plan.md
```

Each slice owns its input schema, handler, and behavior tests. Related UI belongs in the corresponding web feature. Shared approval and financial rules have one implementation. Package boundaries should prevent browser code from importing server adapters or secrets.

TanStack server functions and worker entry points invoke the same application use cases. Use cases depend on purpose-specific interfaces such as a case store, classifier, and banking gateway. Concrete adapters implement those interfaces; startup code connects them. Core rules must not import TanStack, OpenRouter, the ORM, or a hosting SDK.

| Decision | Why it fits this project | Cost or limitation |
| --- | --- | --- |
| Modular monolith | One team can share contracts and rules with a small deployment footprint. | Requires enforced module boundaries as the code grows. |
| Vertical slices | Teammates can own complete behaviors and review changes by use case. | Common invariants must be extracted deliberately to avoid duplication. |
| Selective ports | Banking and AI adapters can be replaced with controlled test implementations. | A few interfaces and adapter contract tests are necessary. |
| Persisted case state | Cases survive closed browser tabs, approvals, and restarts. | Transitions must handle concurrent changes and retries. |
| Durable background execution | Human waiting periods do not occupy a web request. | Workflow runtime integration is provider-specific. |
| Separate simulator adapter | Makes banking actions and failure injection observable and repeatable. | The demo does not prove integration with an actual bank. |

Keep simple read paths simple. Avoid a generic repository framework, dependency-injection container, or separate service for every slice. Record significant implementation tradeoffs in short ADRs when the corresponding choices are made.

### Background execution and hosting

The worker is a logical execution boundary, not a requirement for an always-running Node process. [Cloudflare Workflows](https://developers.cloudflare.com/workflows/) and [Vercel Workflows](https://vercel.com/docs/workflows) both document durable execution and waiting for external events.

Choose one provider early and implement one runtime adapter. Verify TanStack Start integration, database connectivity, local development, deployment, and pricing in a short spike. Keep business use cases portable; do not attempt to build a universal workflow engine. PostgreSQL hosting may require a separate managed database integration even when application hosting is on one platform.

The workflow runtime owns scheduling and retries. Application records own the customer-visible case state, approvals, action identifiers, and audit history. Persist a work request with the corresponding state transition, using an outbox or an equivalent reliable dispatch mechanism, so a crash cannot silently lose the next step.

## AI and workflow behavior

| Stage | AI responsibility | Application responsibility |
| --- | --- | --- |
| Understand | Interpret the inquiry and language; classify intent; identify missing information. | Validate inputs and scope access to the signed-in customer. |
| Decide | Choose among allowed investigation tools and propose the next step. | Enforce policy, tool limits, and permitted case transitions. |
| Act | Request a permitted tool or prepare an approval proposal. | Authorize and execute the operation with a stable identifier. |
| Verify | Explain the result using retrieved evidence. | Independently query operation, transaction, and ledger state. |
| Escalate | Prepare a concise summary with evidence and unresolved questions. | Assign human control and preserve the case until resolved. |

Jev will classify and route through OpenRouter, as identified during the interview. Confirm the exact model identifier, supported request/response format, probability semantics, and three-language behavior in the day-one integration spike. TypeSafe describes Jev as producing structured decisions and probabilities in its [announcement](https://typesafe.ai/blog/introducing-system-one-models-and-jev). Valid output structure is not proof of a correct banking decision.

The conversational LLM handles multilingual dialogue and explanations. Its provider/model remains to be selected. Define a replaceable classifier interface and a fallback path for provider failures. Do not assume fallback scores are calibrated like Jev's; uncertain cases can be routed to a person.

The AI may choose investigation steps within a bounded set of tools. Limit calls and execution time. It must not receive arbitrary SQL access or a way to invoke banking mutations outside the application handlers.

### State, approvals, and concurrency

Illustrative case states are investigating, awaiting customer, awaiting approval, executing, verifying, verification pending, awaiting human, and resolved. Conversation ownership, AI or human, is tracked separately. Final names can change during implementation; the transition rules cannot be implicit in prompts.

Proposed implementation requirements:

- Bind approval to a specific case, payment, action, amount, currency, and relevant record version.
- Check employee authority server-side and recheck eligibility immediately before execution.
- If relevant evidence changes after approval, stop and request review rather than silently reusing the old approval.
- Give each financial operation a stable idempotency key. Enforce uniqueness in the simulator and persistence layer.
- Treat workflow delivery as potentially repeated. Retrying a job must not credit the account twice.
- Verify the linked ledger change and expected transaction outcome. A tool's success message alone is insufficient.
- On an uncertain result, query the existing operation before attempting another mutation. Keep the case open, notify an employee, and tell the customer verification is pending.
- Reject stale automation writes after an employee takes ownership. Returning to automation is an explicit recorded event.

Store the evidence used, model and policy versions, human decisions, tool results, and state changes. The employee view shows concise reasons and supporting records, not hidden model reasoning.

## Multilingual experience

Spanish, English, and Portuguese are required for customer UI, chat, timelines, and notifications. Use translation keys for fixed interface text and canonical codes for backend statuses. Render amounts and dates for the selected locale without translating transaction identifiers or altering amounts.

Preserve original messages when generating employee summaries or translations. A language switch must not reset the case or change the underlying policy. Proposed default: the employee chooses a UI language and sees a summary in that language alongside the original transcript. Portuguese locale details remain an implementation choice to confirm.

## Evaluation and completion criteria

Proposed minimum evaluation set: four scenarios × three languages × two phrasings, for 24 labeled conversations. Add a language-switch case and focused failure tests. This is a small demo evaluation set, not evidence of production-level accuracy.

Required checks:

- All demo scenarios produce the expected route and outcome in all three languages.
- No financial action executes without the required valid employee approval.
- Duplicate delivery and repeated approval submissions cannot produce duplicate ledger effects.
- Changed eligibility blocks stale approvals.
- A verification timeout leaves the case open and exposes the uncertainty.
- Customer A cannot read or mutate customer B's records; customers cannot call employee actions.
- Employee takeover stops subsequent automated customer replies.
- Cases resume after closing the browser and after interruption of background execution.
- Customer success messages are supported by backend evidence.

Use pure rule tests, adapter integration tests against the chosen database, and a small number of end-to-end flows through both interfaces. Evaluate live model classification and responses separately from deterministic workflow tests. A scripted provider adapter is useful for repeatable tests and must be labeled if used in a demo.

Report observed routing accuracy by language, unsupported outcome claims, safe escalations, end-to-end latency, and estimated AI cost per case. Do not advertise accuracy or latency figures before measuring them.

## Team ownership and schedule

Assign names on day one. These are proposed ownership areas, not three independent projects. All three teammates integrate through shared contracts and one end-to-end journey.

| Owner | Primary responsibility |
| --- | --- |
| Teammate A | Customer app, localization, chat, timeline, and notifications. |
| Teammate B | Employee console, approvals, authorization, and takeover. |
| Teammate C | Case workflow, AI adapters, simulator, data import, and deployment. |

Teammate C has the largest integration load. Once their initial screens work, A and B should own their corresponding backend slices and help with evaluations and failure tests. Agree contracts before splitting work, and integrate daily.

| Day | Date | Team capacity | Deliverable |
| --- | --- | --- | --- |
| 1 | Mon Sep 28 | 6 hours | Confirm mandatory judging requirements, assign owners, scaffold the monorepo, and spike hosting, DB, and AI access. Deploy a minimal page. |
| 2 | Tue Sep 29 | 6 hours | Seed demo customers and payments; establish sessions, access checks, case contracts, and UI shells. |
| 3 | Wed Sep 30 | 6 hours | Connect a persisted investigation case, simulator tools, and the first live AI path. |
| 4 | Thu Oct 1 | 6 hours | Complete a rough customer → employee approval → reversal → verification flow. Styling can remain basic. |
| 5 | Fri Oct 2 | 6 hours | Make the flow asynchronous and resumable; connect approval state and case timeline. |
| 6 | Sat Oct 3 | 12–18 hours | Finish takeover, automatic resolution and ambiguous scenarios, and all three language paths. |
| 7 | Sun Oct 4 | 12–18 hours | Integrate the uncertainty scenario, recovery behavior, and notifications. Reach feature freeze. |
| 8 | Mon Oct 5 | 6 hours | Run multilingual and access-control evaluations; fix critical failures. |
| 9 | Tue Oct 6 | 6 hours | Test retries, stale approvals, and restart recovery; finalize architecture explanation and demo script. |
| 10 | Wed Oct 7 | 6 hours | Rehearse, verify deployment and reset behavior, prepare submission, and keep time for fixes. |

Days 8–10 reserve 18 hours. Reserve up to three additional weekend hours for integration and rehearsal when the team can contribute at the upper end of its availability. Core feature work should fit within approximately 54–63 hours.

If the schedule slips, cut styling polish, extra fixtures, and nonessential employee analytics. Preserve the complete approval/verification loop, required languages, access checks, and failure behavior. Do not add new banking journeys before submission.

## Out of scope

- Training or fine-tuning a custom model.
- Voice, WhatsApp, email, SMS, and other customer channels.
- Registration, onboarding, identity verification, and password recovery.
- Real funds movement or production banking integrations.
- Implementing refunds, transfer retries, fraud disputes, or other additional financial journeys.
- Country-specific banking policy coverage or claims of regulatory compliance.
- Loading the entire dataset, building an analytics warehouse, or creating a broad policy retrieval system.
- Microservices, multiple workflow providers, and a generalized banking-agent platform.

## Remaining decisions

| Item | Proposed next step |
| --- | --- |
| Official challenge brief and judging rubric | Check for requirements beyond languages and architecture before committing to final scope. This was not supplied during the interview. |
| Database and ORM | Confirm the proposed PostgreSQL + Drizzle default or choose the team's familiar equivalent. |
| Hosting and workflow runtime | Spike Cloudflare or Vercel on day one; choose one based on compatibility, operational effort, and cost. |
| AI configuration | Confirm Jev access and response semantics; select the conversational model and an evaluation budget. |
| Simulator policy | Write a short fictional policy and explicit eligibility fixtures; distinguish them from dataset facts. |
| Ownership and submission | Assign teammate names and verify the official deadline and required submission artifacts. |

This document records the agreed product direction and proposed implementation details. It does not indicate that the application has already been built, deployed, or evaluated.
