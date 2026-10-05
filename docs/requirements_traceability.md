# Requirements traceability

Each requirement from the challenge brief (*Problem Statement*) and from the September 25 kickoff, where this repository meets it and
how to verify it. Status: ✅ met · 🟡 partial (the gap is stated) · ⬜ pending.

Figures are not repeated here: they live in the generated reports that are cited. Everything measured is offline and on synthetic
data; none of this is a production measurement.

## Scope

| Requirement | Status | Evidence | How to verify |
|---|---|---|---|
| One coherent flow | ✅ | Account and payment inquiries (balances, transactions, payment and delinquency status, currency exchange); a single action, tracing a pending movement ([ADR-002](decisions/ADR-002-one-action-confirmed-in-code.md)) | [README](../README.md#why-this-workflow-measured-on-the-provided-data) |
| Normal resolution path | ✅ | Case types `balance_*`, `payment_ok`, `fx`, `transactions` | [`SYSTEM_EVAL.md`](../eval/reports/SYSTEM_EVAL.md), "By case type" table |
| Ambiguous or unsupported request | ✅ | `CLARIFY` and `ABSTAIN` dispositions in [`agent/policy/router.py`](../agent/policy/router.py); types `ambiguous_type`, `out_of_scope`, `code_switch` | Same |
| Case that requires a person | ✅ | Types `fraud`, `suspended`, `trace_review`; structured handoff in [`agent/policy/escalation.py`](../agent/policy/escalation.py) | Same; operator console in `web/` |
| Spanish and Portuguese | 🟡 | The 548 test cases are in ES and PT; the web app has ES/PT i18n | Portuguese written by the team: the dataset does not include it ([LIMITATIONS](../LIMITATIONS.md#data-and-ml)) |
| Data and language limitations | ✅ | [LIMITATIONS.md](../LIMITATIONS.md), [data_quality.md](data_quality.md) | Read |
| Working prototype, evidence of a path to production and an honest account of what is missing | ✅ | [operations.md](operations.md), [LIMITATIONS.md](../LIMITATIONS.md) | Deployed demo: https://cecil-ai.onrender.com |

## 1. A problem backed by data

| Requirement | Status | Evidence | How to verify |
|---|---|---|---|
| Contact reasons, demand, data quality, operational constraints | ✅ | Share, times, first-contact resolution and CSAT by reason ([README](../README.md#why-this-workflow-measured-on-the-provided-data), [EVALUATION §1](../EVALUATION.md)); [dataset-audit.md](dataset-audit.md), [data_evidence.md](data_evidence.md), [data_quality.md](data_quality.md) | `make baseline` regenerates [`baseline_metrics.md`](evidence/baseline_metrics.md) |
| Human baseline to measure the improvement | ✅ | [`baseline_metrics.md`](evidence/baseline_metrics.md): ≈341 s per inquiry (120 s in queue + 221 s on the call) | Same |
| Limits of the evidence | 🟡 | The 171 thousand transcripts repeat 42 customer texts: they serve to measure demand by reason, not to train or evaluate language | [LIMITATIONS](../LIMITATIONS.md#data-and-ml) |

## 2. An AI system that works

| Requirement | Status | Evidence | How to verify |
|---|---|---|---|
| Conversational context | ✅ | Per-turn session state (`agent/session/`, `agent/core/orchestrator.py`); case type `multi_turn` | `tests/test_orchestrator.py` |
| Clarify ambiguity | ✅ | `CLARIFY` disposition with the customer's options | "ambiguo" (Ambiguous) guided scenario in the demo |
| Answers grounded in permitted information | ✅ | The model receives no customer records and does not write to the customer: every answer is a template or verified data ([ADR-001](decisions/ADR-001-model-interprets-code-speaks.md), [`agent/core/render.py`](../agent/core/render.py)) | "Cases that sent a customer record to the model" metric in the reports; `tests/test_privacy.py` |
| Tools in service of the flow | ✅ | [`agent/tools/`](../agent/tools/) | `tests/test_tools.py` |
| Report only verified actions | ✅ | The action is announced after reading it back; if it does not match, the case is handed off ([ADR-002](decisions/ADR-002-one-action-confirmed-in-code.md), rule `action:trace_unverified`) | `tests/test_trace.py` |

## 3. Controlled automation

| Requirement | Status | Evidence | How to verify |
|---|---|---|---|
| What gets answered, what needs confirmation, when to abstain or hand off | ✅ | Deterministic policy with fixed precedence ([`agent/policy/router.py`](../agent/policy/router.py), [`escalation.py`](../agent/policy/escalation.py)); the only action requires the customer's "sí" (yes), judged in code | Each decision carries its `rule` in the trace; **Why?** button in the demo |
| Permissions and policies outside the model's prose | ✅ | Per-customer authorization in the tool layer; a route × role matrix that prevents startup if a route is missing ([`api/access.py`](../api/access.py)) | `tests/test_access_matrix.py` |
| The handoff carries the request, verified facts, actions, evidence and open questions | ✅ | `Ticket` in [`agent/policy/escalation.py`](../agent/policy/escalation.py) | "Handoff completeness" metric in [`SYSTEM_EVAL.md`](../eval/reports/SYSTEM_EVAL.md) |
| Identity: a document or customer number does not prove identity | ✅ | Session with a signed token issued by a test IdP ([`agent/session/identity.py`](../agent/session/identity.py)) | `tests/test_privacy.py`, `tests/test_api.py`; the test IdP is listed in [LIMITATIONS](../LIMITATIONS.md#security-and-privacy) |

## 4. Data and ML

| Requirement | Status | Evidence | How to verify |
|---|---|---|---|
| Repeatable preparation with contracts | ✅ | [`data/contracts.py`](../data/contracts.py), [`data/pipeline.py`](../data/pipeline.py), [data-validation-catalog.md](data-validation-catalog.md) | `make ingest-demo`; `tests/test_pipeline.py` |
| Quality and lineage checks | ✅ | [`data/quality.py`](../data/quality.py), [`data/lineage.py`](../data/lineage.py); **Data quality** view in the demo | [data_quality.md](data_quality.md) |
| Update and freshness policy | ✅ | [data_quality.md, "Update and freshness policy"](data_quality.md) | Same |
| Correctness of the update with a labeled fixture (static data) | ✅ | Late-arrival test: a partition is re-delivered and the latest `last_updated` wins | `tests/test_pipeline.py` |
| A learned component against an appropriate baseline | ✅ | Intent classifier versus keywords, on text it had not seen | [`intent_classifier.md`](../eval/reports/intent_classifier.md); [EVALUATION §2](../EVALUATION.md) |
| Valid labels | 🟡 | The training and evaluation texts were written by the team; there is same-author bias. A set of messages from real people is in progress ([human_set.md](human_set.md), [preregistration](preregistration.md)). The organizer's fraud labels were measured and are not used to decide: `is_fraud` cannot be learned from the transaction (AUC 0.506) ([label_signal.md](evidence/label_signal.md), [ADR-005](decisions/ADR-005-no-fraud-or-risk-model.md)) | [LIMITATIONS](../LIMITATIONS.md#data-and-ml); [`pendientes.md`](pendientes.md) item 4 |
| Automated validation of contracts, quality, lineage, freshness, classifier against baseline, and leakage | ✅ | All in PASS, with what they leave open stated | `make validate-data-ml`; [`data_ml_validation.md`](evidence/data_ml_validation.md) |
| No data leakage | ✅ | Near-duplicate check between training and evaluation ([`eval/leakage.py`](../eval/leakage.py)); dev (seed 7) and test (seed 11) splits with distinct customers and phrases | `tests/test_leakage.py` |
| Justified metrics, thresholds and splits | ✅ | [EVALUATION §2 and §3](../EVALUATION.md); Wilson intervals ([`eval/stats.py`](../eval/stats.py)) | Reports in `eval/reports/` |
| Experiment tracking | ✅ | MLflow ([`eval/tracking.py`](../eval/tracking.py)), fingerprint of the evaluated code ([`eval/fingerprint.py`](../eval/fingerprint.py)) | [EVALUATION §5](../EVALUATION.md) |

## 5. Measured quality and failure handling

| Requirement | Status | Evidence | How to verify |
|---|---|---|---|
| Evaluate on held-out cases, baseline and system on the same workload | ✅ | 548 test cases; keyword baseline ([`eval/baseline_bot.py`](../eval/baseline_bot.py)) | `make eval` → [`SYSTEM_EVAL.md`](../eval/reports/SYSTEM_EVAL.md) |
| Incorrect or missing data, expired session, unauthorized access, injection, tool failure, multilingual ambiguity | ✅ | Types `hallucination_guard`, `expired_session`, `injection`, `tool_failure`, `code_switch`; reserved failure set ([`eval/heldout/`](../eval/heldout/)) with injected failures | [`FAILURE_EVAL.md`](../eval/reports/FAILURE_EVAL.md); [`SYSTEM_EVAL_ADVERSARIAL.md`](../eval/reports/SYSTEM_EVAL_ADVERSARIAL.md) |
| Safe resolution, containment, escalation quality, unsafe outcomes with counts and denominators | ✅ | Defined and reported separately in each report; missed and unnecessary escalations are counted | [EVALUATION §3](../EVALUATION.md) |
| p50/p95 latency and cost per case and per safe resolution | ✅ | With live models | [`SYSTEM_EVAL_LIVE.md`](../eval/reports/SYSTEM_EVAL_LIVE.md); capacity in [EVALUATION §6](../EVALUATION.md) |
| Results by language and segment, with the limitations of a small sample | ✅ | By country·segment cell and by language | [EVALUATION, "Fairness and coverage"](../EVALUATION.md) |
| Model and prompt versions, and variability across runs | ✅ | `prompt_sha256`, prompt version, three runs with live models | [`SYSTEM_EVAL_LIVE.md`](../eval/reports/SYSTEM_EVAL_LIVE.md) |
| Answer judge with a validated rubric | ✅ | No LLM is used as a judge: the judge deterministically reconstructs the answers the system could send | [LIMITATIONS](../LIMITATIONS.md), item 5 of "Not yet measured" |
| Live models on the whole workload | ✅ | All 548 test cases, 3 runs per model (2026-10-04); the safety bound is ≈0.55%, not zero; Haiku 4.5 had 1 unsafe outcome in one of its 3 runs, Sonnet 5 none; the cases are synthetic and the Portuguese is team-written | [LIMITATIONS](../LIMITATIONS.md#not-yet-measured) |
| What each group of safety controls contributes (counterfactual) | ✅ | The same models, ideal and bad, with groups of controls removed in a cumulative ladder, without attributing individual effects: with no controls, the bad model produces unsafe outcomes in most cases; with all of them, 0. The naive variants do not open traces, so the confirmation of the action is not measured | `make eval-ablation` → [`ABLATION.md`](../eval/reports/ABLATION.md) |
| Offline measurement labeled as such | ✅ | Every report states it; nothing is presented as an improvement measured in production | [EVALUATION](../EVALUATION.md) |
| Red team session on the deployed demo | ✅ | Run on 2026-09-30 ([red_team.md](red_team.md)); report in [`RED_TEAM.md`](../eval/reports/RED_TEAM.md): no finding in the records, ten observations open, participants' notes still to come | `python -m eval.red_team report` rebuilds [`red_team.json`](../eval/reports/red_team.json) from the snapshot |

## 6. A credible path to operations

| Requirement | Status | Evidence | How to verify |
|---|---|---|---|
| Traces and execution logs | ✅ | End-to-end correlation ID, one trace per turn with the rule that decided ([operations.md, "Resilience and traces"](operations.md)) | `tests/test_trace.py`; `/admin/trace_log` |
| Bounded retries and safe fallback | ✅ | Per-turn and per-step budget; degraded mode if the model does not respond ([operations.md](operations.md)) | `tests/test_resilience.py`; "simular caída del modelo" (Simulate model outage) button in the demo |
| Reproducible setup | ✅ | `make up`, dependencies pinned with hashes, CI that builds and starts the image the way Render does | [operations.md, "Setup, reproducibly"](operations.md) |
| Capacity limits | ✅ | `make loadtest`, `GET /admin/capacity` | [EVALUATION §6](../EVALUATION.md) |
| Monitoring | ✅ | `/metrics`, Prometheus, 23 alert rules with tests | [`ops/alerts.yml`](../ops/alerts.yml); [operations.md, "Monitoring"](operations.md) |
| Access controls | ✅ | Named operator keys; read separated from action | [operations.md, "Access control"](operations.md); `tests/test_access_matrix.py` |
| Data retention | ✅ | Scheduled and audited retention ([`ops/retention.py`](../ops/retention.py)) | `tests/test_retention.py` |
| Explanations based on sources, rules and execution logs (not on chain of thought) | ✅ | **Why?**: what the model received (masked), what it chose and what the code verified, with the rule | Deployed demo |
| Remaining work to deploy for real | ✅ | [LIMITATIONS.md](../LIMITATIONS.md) | Read |

## Data and execution limits

| Requirement | Status | Evidence | How to verify |
|---|---|---|---|
| Label whether each input is real, de-identified, synthetic or from the team | ✅ | Provenance table for every evaluation input (supplied synthetic, generated by the team, injected, test fixture, real people) | [EVALUATION, "Provenance of every evaluation input"](../EVALUATION.md) |
| No credentials or restricted data in the public repository | 🟡 | Public-copy procedure with a scan of the whole history ([operations.md, "Public repository"](operations.md), [`ops/export_public.py`](../ops/export_public.py)). **This repository is private and its history contains the organizer's PDFs**: it must not be published as is | See "Submission" below |
| Sandbox services documented with their contracts and limits | ✅ | Simulated trace service ([ARCHITECTURE.md](../ARCHITECTURE.md)); the demo's public test IdP and PINs, declared in [LIMITATIONS](../LIMITATIONS.md#security-and-privacy) | Read |

## Submission (kickoff, "Submission Details")

| Requirement | Status | Evidence | How to verify |
|---|---|---|---|
| **Public** GitHub repository, named `factored-hackathon-2026-[equipo]` | ✅ | [`try-cecilia/factored-hackathon-2026-cecilia`](https://github.com/try-cecilia/factored-hackathon-2026-cecilia), a new repository generated with `ops/export_public.py` from the team's private one: its history rewritten without the organizer's PDFs, the per-case reports and workloads (dataset ids) and the console keys; the tests that need them are skipped there | — |
| Link to the deployed tool | ✅ | Web: https://cecil-ai.onrender.com · API: https://x-payments-agent.onrender.com | Open `/login`; the API responds at `/health` |
| 4 to 6 slides | ✅ | New six-slide [PDF](demo/final-demo-v10-2026-10-04/cecilia-presentation.pdf) and [editable HTML](demo/final-demo-v10-2026-10-04/cecilia-presentation.html), with Team Cecilia, deployment URL and sourced figures. The approved exports retain their repository placeholder; the current public URL is listed above. | Open both exports |
| Mandatory presentation video | ✅ | [Updated English pitch](demo/final-demo-v10-2026-10-04/cecilia-3min-en.mp4), 163.2 seconds, real deployed ES/PT scenarios, ElevenLabs voice, captions and animated architectural explanation. Editable Remotion project included. | Play video; inspect [deployment check](demo/final-demo-v10-2026-10-04/deployment-check.json) and [video validation](demo/final-demo-v10-2026-10-04/validation.json) |
| Send everything to hackathon.admin@factored.ai | ⬜ | Not sent | Send |

## Evaluation criteria (kickoff)

| Criterion | Where to look |
|---|---|
| Project justification and documentation | [README](../README.md), [ADR-001](decisions/ADR-001-model-interprets-code-speaks.md), [ADR-002](decisions/ADR-002-one-action-confirmed-in-code.md), [LIMITATIONS](../LIMITATIONS.md) |
| AI engineering (backend, frontend, deployment) | [ARCHITECTURE.md](../ARCHITECTURE.md), `agent/`, `api/`, `web/`, [operations.md](operations.md) |
| Data analytics (quality and insights) | [data_quality.md](data_quality.md), [data_evidence.md](data_evidence.md), [`baseline_metrics.md`](evidence/baseline_metrics.md) |
| Data engineering (extraction and transformation) | [`data/`](../data/), [data-validation-catalog.md](data-validation-catalog.md) |
| Machine learning (selection, optimization, implementation, tracking) | [EVALUATION §2 and §5](../EVALUATION.md), [`eval/models/`](../eval/models/) |
