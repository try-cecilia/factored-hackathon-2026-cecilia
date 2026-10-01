# Dataset audit and design implications

Audit performed on September 28, 2026 on the S3 dataset identified in the data dictionary provided by the organizers. The recommendations incorporate a full reading of the [official brief](https://docs.google.com/document/d/18AwONT8hQupRcfNPLFrPo6fHOJ_OUn1nBf-3jMnla2c/edit).

## Recommendation

Balance queries are ruled out as the problem to solve. Their presence in every transcript is explained by template repetition and does not justify prioritizing them on the basis of demand. We keep that finding as a limitation of the corpus.

Payments and complaints remain as alternatives. Transactions make it possible to build verified status queries, and complaint categories document problems recorded in this synthetic dataset. They do not make it possible to show that unreceived transfers are a frequent contact reason. The main flow has not been chosen yet. It must include a person visible in the conversation, a business action approved and verified in the simulator, and persistent cases. Reversal is a possible action, still pending a choice.

We keep the original decision not to train our own model. The brief allows pretrained models and does not require training a new one. A component such as Jev must be evaluated against a deterministic baseline, with reviewed labels and a shared held-out workload. Data engineering and metric-based evaluation remain mandatory.

The main technical finding is that a record can conform to the schema and still be unfit for a specific use. Before trusting a join, the app and the evaluator must verify ownership, temporal consistency, available evidence, and the meaning of the labels.

The later review against the dictionary's 260 columns is documented in the [validation catalog](data-validation-catalog.md). It adds conflicts in alternate `UNIQUE` fields, amounts without a currency, and concrete ingestion rules. It distinguishes explicit constraints, semantic consistency, and insufficient evidence.

## Coverage and reproducibility

The audit inventoried the 13 tables. It processed all the files of 11 tables and a date-based sample of the other two event tables. In total it analyzed 6,311,493 rows from 5,516 files, equivalent to 1,309,213,022 bytes. These are counts obtained by parsing the files, not estimates from the PDF.

| Table | Rows analyzed | Coverage |
| --- | ---: | --- |
| Customers | 150,000 | Complete |
| Products | 400,000 | Complete |
| Branches | 350 | Complete |
| Service agents | 1,200 | Complete |
| Marketing campaigns | 200 | Complete |
| Daily exchange rates | 13,164 | Complete |
| Call center interactions | 686,296 | All 1,097 daily files |
| Transcripts | 171,321 | All 1,097 daily files |
| Complaints | 67,095 | All 1,097 daily files |
| Satisfaction surveys | 212,759 | All 1,097 daily files |
| Transactions | 4,425,008 | All 1,097 daily files |
| Digital events | 164,857 | 13 dates, the 17th of March, June, September, and December when available |
| Campaign sends | 19,243 | 12 dates with the same selection rule |

The event samples are not random and were not designed to be representative. Their rates must not be extrapolated to the full population. Daily-file coverage runs through June 17, 2026, although some event timestamps reach June 18. Process day and event day are different. That difference alone does not demonstrate late ingestion.

Each file has object metadata, a local SHA256, a row count, and per-record lineage in the local audit database. A second implementation, using the CSV parser from Python's standard library, re-read every file and matched the counts and SHA256 values. There were zero differences. The audit used local exploratory scripts in TypeScript and SQL. Those scripts are excluded from version control and do not fix the project's technology.

A full rebuild also reproduced the hashes and counts of the 5,516 files and the hashes of both evaluation datasets. This verifies reproducibility in the local environment with the same source bytes. The implementation and the commands still have to be published, in the language the team chooses, so that the process can be repeated from a clean checkout. The manifests and results alone do not replace that deliverable. Nor do they show that the records are correct for every use.

The evidence artifacts remain in the local environment, under `reports/data-audit/`. This submission includes only Markdown documentation. The scripts, reports, and datasets are not included and will not be available in a fresh checkout.

- `source-manifest.json`, with the selected objects, coverage, and bytes.
- `ingestion.json`, with hashes, counts, schema variants, nulls, and duplicates.
- `metrics.json` and `queries.sql`, with aggregate findings and the queries used in the audit.
- `independent-verification.json`, with the results of the second parser.
- `reproducibility.json`, with the comparison from the full rebuild.
- `quality-gates.json`, with failures linked to the affected use.

## What the contacts support

| Source category | Contacts | Share | Recorded rate of unresolved cases |
| --- | ---: | ---: | ---: |
| Transaccional (transactional) | 240,056 | 34.98% | 8.49% |
| Producto (product) | 150,863 | 21.98% | 10.37% |
| Queja (complaint) | 117,021 | 17.05% | 56.40% |
| Técnico (technical) | 102,899 | 14.99% | 30.07% |
| Comercial (commercial) | 54,879 | 8.00% | 34.79% |
| Retención (retention) | 20,578 | 3.00% | 39.84% |

The denominator is the 686,296 interactions. These categories are descriptive metadata from the source. `contact_reason` matches `reason_category` in every row. There is no independent label with a more specific reason.

All 171,321 customer texts mention a balance. The documented lexical checks found no mentions of transfers, unrecognized charges, fees, or payments. The review of the 42 distinct texts found two opening questions, one about a savings account balance and the other about a credit card balance. Generic conversational phrases are added to these. There are only 546 distinct full transcripts and 42 distinct agent texts.

Each of the 42 variants appears under several reason categories. `detected_intents` contains `consulta_general` when it is not null. This limits the conclusions:

- Balance queries are present, but their repetition does not make it possible to measure their demand or to justify their priority as a product.
- The per-category shares are not equivalent to validated semantic-intent shares.
- The transcript count does not represent 171,321 distinct linguistic examples or real market demand.
- The prevalence of queries about unreceived transfers cannot be measured from these transcripts.

The transactions table contains 896,438 transfers. It includes 17,841 Pending, 44,979 Declined, and 8,942 Reversed. These records make it possible to query statuses and build controlled scenarios. They do not prove that there was an inquiry, a delay, or receipt by the beneficiary. There is no settlement sequence and no linked beneficiary ledger.

The complaints include 12,297 cases in the Cargo no reconocido (unrecognized charge) subcategory and 12,194 in Cobro indebido (undue charge). However, the whole table uses only five generic descriptions. The categories make it possible to describe complaint volume, but the descriptions offer little variety for evaluating natural language.

## Quality defects that change the design

| Finding | Measured result | Consequence |
| --- | --- | --- |
| Product number declared `UNIQUE` | 6 numbers appear on 12 products belonging to different customers, out of 400,000 products. | Block identity resolution by those numbers. Do not merge products or owners. |
| Employee code declared `UNIQUE` | 13 codes appear on 26 agents, out of 1,200 agents. | Do not identify or authorize employees by that code alone. |
| Ownership between complaint and product | All 44,570 non-null references point to a product of another customer. | Block that join in serving and labeling. Do not silently change either of the owners. |
| Link between complaint and interaction | `origin_interaction_id` is null in all 67,095 complaints. | They cannot be used as outcomes linked to conversations. |
| Customer's registration branch | 149,995 of 150,000 references point to nonexistent branches. | Exclude features and attributions based on that branch. |
| Agent's branch | 831 of the 833 non-null references point to nonexistent branches. | Do not use that relationship to route agents by branch. |
| Contact before registration | 128,453 of 686,296 contacts, or 18.72%. | Exclude impossible chronologies from the candidate historical cohort. |
| Payment chronology | 1,451,309 of 4,425,008 transactions, or 32.80%, predate the customer's registration, the product's opening, or both. | Only 2,973,699 pass both checks. |
| Mandatory transcript duration | 24,029 null durations, although the dictionary requires the field. | Record the contract violation. Do not impute duration to evaluate outcomes. |
| Claimed amount without currency | 1,040 of the 21,751 complaints with an amount have no currency. Both fields are optional in the dictionary. | Block monetary decisions based on that amount until there is evidence of the currency. |
| Resolution with incomplete evidence | 1,549 of the 16,121 `Resolved` or `Closed` complaints lack a resolution date, a description, or both. These are optional fields. | Report the recorded status without claiming a verified action and without using it as sufficient proof of resolution. |
| Historical dimensions | Customers and products are single files. No monthly snapshots are exposed. Some `last_updated` values reach June 2027. | Do not use current balances and statuses as historical features at the start of a query, or as live observations. |
| Currency coverage | There are no MXN transactions. The 2,216,431 transactions of customers from Mexico are in USD. | Document the actual coverage. These records do not support a demo in MXN. |
| USD conversion reconciliation | 749,769 ARS rows and 1,031,847 COP rows with a reported USD amount differ by more than one cent from the conversion at that calendar day's exchange rate. | Do not use `amount_usd` as verified financial evidence until the conversion convention is resolved. |

Checking only that foreign keys exist would not detect the ownership defect in the complaints. The transaction → product → customer chain, by contrast, has zero ownership mismatches across the 4,425,008 transactions. The customer also matches between transcript and interaction, and between survey and interaction. These relationships are usable after applying temporal and purpose-specific checks.

The source does not include an opening balance, entries signed as debit or credit, or a complete balance history. All the observed amounts are positive. Summing them does not reconcile `current_balance`. Although balance queries were left out of scope, this limitation still affects any optional reversal. Verifying one requires the simulator's independent ledger.

All the selected files could be parsed, each table presented a single header schema, and no duplicate primary keys appeared in the analyzed inputs. The later review did find repeats in `product_number` and `employee_code`, which carry an additional `UNIQUE` constraint. This corrects the earlier, overly broad claim that there were no duplicate business keys. The dictionary's approximate duplicate rate does not determine the count that must appear in each table. Defects are not ruled out in unsampled digital or campaign files, or in future deliveries. The local exploratory pipeline includes controlled fixtures for duplication, conflicts, truncation, and schema changes to test those behaviors. Those fixtures are not included in this documentation submission.

An invalid link to a product does not force discarding the whole complaint. It can be kept for aggregate analysis by category while the unsafe join is forbidden. The quality decision depends on the use.

## Labels and leakage

`was_escalated` is around 10% in all six categories. A classifier that always predicts no escalation gets 90.03% accuracy on the exploratory 2026 partition. This shows the risk of using accuracy as the only metric. The audit does not show that escalation is unpredictable, but a predictor of that outcome needs more justification.

`was_resolved` varies across categories, although these contradict the visible text and it is not proven that they are available at the start of the query. `requires_followup` is true in every case recorded as unresolved, so it introduces a risk of outcome leakage. The full transcripts, agent replies, duration, satisfaction, resolution dates, and compensations must not become input features.

In a simple temporal split with 2026 as a diagnostic holdout:

- 74,303 of the 75,981 held-out customers already appear earlier, or 97.79%.
- All 26,620 held-out transcripts repeat customer text seen earlier.
- Each of the 42 variants is associated with several escalation outcomes and several reason categories.

A random split by rows would hide these problems. Two families of opening questions are not enough for a broad linguistic benchmark with strict separation by template. ES/PT language has to be created or transformed under a documented protocol, reviewed, and kept separate from prompt development. Translations remain linked to the original case.

## Evaluation artifacts built

The local file `reports/data-audit/evaluation-manifest.json` records reproducible splits by customer hash and date. After excluding contacts that predate registration, these structured cohorts remain:

| Partition | Cases | Unique customers |
| --- | ---: | ---: |
| Train/development | 245,074 | 81,202 |
| Validation | 15,839 | 11,050 |
| Candidate test | 15,675 | 11,229 |

No customers are shared between the retained partitions. Another 281,255 contacts with a valid chronology fall outside the selected customer and period combinations. That exclusion is recorded. These are candidate historical datasets and do not require training a model. Their aggregate results were inspected during the audit, so they do not constitute an already executed blind benchmark.

The pipeline also selected 200 distinct customers, with 50 payment contexts per status, and created 3,600 structured fixtures. They come from 200 contexts × two languages × nine variants. They cover normal query, wrong owner, missing status, expired session, prompt injection, tool failure, multilingual ambiguity, inconsistent currency, and expired observation.

These fixtures serve deterministic verification and runner development. The number of independent contexts is 200. The 3,600 variants are not independent conversations. The prompts are synthetic, linguistic review is still missing, and no agent has been evaluated yet. They do not replace a diverse, reviewed held-out workload or a real comparison against the baseline. They cover payment status queries and do not fix the scope. Scenarios for the approved action, human participation, and persistence are missing, as is any adaptation needed if complaints are chosen.

## Recommended next implementation

1. Choose one flow, payments or complaints, based on its evidence and limitations, without using the repetition of balance queries as a demand signal. Keep clarifications, visible human participation, an approved and verified business action, and persistent cases. Identify financial mutations as simulator work.
2. Publish allowed facts with lineage and explicit quality flags. Invalid ownership, missing evidence, and freshness failures must trigger deterministic gates before data is sent to the model.
3. Compare an ES/PT rule-based intent and ambiguity baseline with Jev, using independently reviewed labels. Both must share tools, permissions, and verification. Do not use `reason_category` as semantic ground truth for these transcripts.
4. Run the complete systems on the same held-out workload and report outcomes, escalation, safety, latency, cost, and differences between groups, as the brief requires. Follow the [evaluation protocol](evaluation-protocol.md).

The audit is complete with the declared coverage. Still pending are the shared pipeline in the chosen stack, the baseline and model measurements, the human linguistic review, and runtime verification of the banking application.
