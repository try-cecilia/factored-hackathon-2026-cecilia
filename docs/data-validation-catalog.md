# Dataset errors and ingestion validation contract

Review of September 28, 2026, against the [official data dictionary](https://drive.google.com/file/d/***REMOVED***/view). The re-downloaded copy matches the one used in the audit. Its SHA256 is `65cc2bd37d525fc0c7812ea442d56fdfb8152f1b937e5a8995bb98bfd7dea513`.

This document defines validations based on observed defects. At the time of writing it did not implement the pipeline; today `data/pipeline.py` runs a large share of them, and section 9 says which ones, with the test that backs them and what is missing. The audit's check scripts and detailed reports remain local.

## Coverage and criteria

The definitions of 260 columns, including 136 `NOT NULL` constraints, were checked against the 13 tables analyzed. Coverage is still 11 complete tables plus date-based samples of digital events and campaign sends. That is 6,311,493 rows from 5,516 files. Results for sampled tables are not extrapolated to the rest of the source.

Column presence, nulls, `VARCHAR` lengths, type representation, decimal precision and the four additional fields declared `UNIQUE` were verified. The previous audit covers primary keys, relationships and chronology. Selected ranges described in the dictionary were also checked, not every possible business rule.

We classify each finding by its basis:

- **Explicit contract:** violates `NOT NULL`, `UNIQUE` or a declared foreign key.
- **Semantic consistency:** the rows are valid individually, but their combination does not serve the intended use.
- **Insufficient evidence:** the dictionary allows the missing value, but the application cannot make a certain claim or take a certain action without it.
- **Representation or documentation difference:** needs a parsing policy or an agreed contract. It does not justify discarding rows automatically.

Counts for different rules may include the same rows. They must not be added up to obtain a total number of defective records.

## 1. Explicit violations of the dictionary

| ID | Contract and reference | Observed result | Validation and handling |
| --- | --- | --- | --- |
| DQ-001 | `products.product_number`, `NOT NULL, UNIQUE`, page 5. | 6 repeated numbers, 12 affected products out of 400,000. Each number corresponds to two `product_id` values and two different customers. That is 6 rows in excess of uniqueness. | Group by number and require a single identity within the snapshot. Block identity resolution by that number. Keep the raw rows; do not merge products or owners. |
| DQ-002 | `service_agents.employee_code`, `NOT NULL, UNIQUE`, page 6. | 13 repeated codes, 26 affected agents out of 1,200. Each code appears twice. | Block identification, assignment or authentication based only on that code. Use a validated `agent_id` and a trusted session. Do not merge agents automatically. |
| DQ-003 | `customers.registration_branch_id`, `FK, NOT NULL`, pages 4 and 15. | 149,995 of 150,000 references do not exist in `branches`. None is null. | Check existence with an anti-join. Block attribution and routing by registration branch. Keep the customer's other valid uses. |
| DQ-004 | `service_agents.assigned_branch_id`, `FK`, pages 6 and 15. | 831 orphan references among 833 non-null ones. The other 367 agents have a permitted null. | Check only non-null references. Block routing or branch context based on the orphans. Do not treat the 367 nulls as `NOT NULL` violations. |
| DQ-005 | `call_transcripts.duration_seconds`, `INTEGER, NOT NULL`, page 10. | 24,029 null values out of 171,321 transcripts. | Record the violation. Exclude those rows from uses that require the duration and from a publication that promises that strict contract. Do not substitute zero, or the duration from another table, without a justified rule. |

The previous audit checked for duplicate primary keys. This review adds the alternate `UNIQUE` fields. That is why zero duplicate primary keys can coexist with repeated product numbers or employee codes.

The fields `customers.document_number` and `branches.branch_code`, also declared `UNIQUE`, showed no non-null repetitions in the complete tables analyzed.

## 2. Inconsistencies between records

These rules combine the semantics of the fields with the needs of the product. Not all of them appear as a literal `CHECK` in the dictionary.

| ID | Rule | Observed result | Handling |
| --- | --- | --- | --- |
| DQ-006 | A complaint can only be linked to a product of the same customer. | The 44,570 non-null references in `complaints.affected_product_id` exist, but all of them point to products of another customer. | Block that join for serving, permissions and labels. The complaint can be kept for lookups by its customer and for aggregate analysis. Do not change its owner. |
| DQ-007 | For the historical payments cohort, the transaction must be on or after the customer's registration and the product's opening. | 1,451,309 of 4,425,008 transactions fail at least one condition. Only 2,973,699 pass both. | Exclude them from that cohort and from contexts that assert that history. Record the reason per row. Validate dates before comparing them. |
| DQ-008 | Under the contract adopted for the cohort, a historical interaction cannot precede the customer's registration. | 128,453 of 686,296 interactions predate the registration. | Exclude them from the historical cohort and report the reduced coverage. Do not replace dates. |

According to the dictionary, registration dates represent the customer's sign-up. If the organization clarifies that they are actually migration dates, the temporal rules will have to be revisited. That explanation will not be applied on assumption.

The transaction → product → customer chain does have consistent ownership across the 4,425,008 transactions. This does not remove the need to check chronology or to authorize the user at runtime.

## 3. Optional data that is insufficient for certain uses

| ID | Finding | Observed result | Proposed usage gate |
| --- | --- | --- | --- |
| DQ-009 | Claimed amount without a currency. The dictionary allows nulls in both fields, page 12. | 1,040 of the 21,751 complaints with a populated `claimed_amount` lack a `currency`. All 1,040 amounts are positive. The full table has 67,095 rows. | Do not propose or execute a monetary action based on that amount. Request or recover the currency with authorized evidence. Do not infer it from the country or from the wrongly linked product. |
| DQ-010 | Resolution status without sufficient evidence. `resolution_date` and `resolution` are optional, page 12. | Among 16,121 `Resolved` or `Closed` complaints, 772 have no resolution date and 811 have no description. The union is 1,549 complaints. | The recorded status can be reported as such. Do not claim what action took place, or when it was verified, without additional evidence. Do not count those statuses on their own as verified resolutions. |
| DQ-011 | Complaints without an originating interaction. `origin_interaction_id` is an optional FK, pages 12 and 16. | Null in all 67,095 complaints. | Disable the complaint → conversation link and its use as ground truth for the conversational outcome. Do not invent a join based on proximity of dates or customer. |
| DQ-012 | Missing historical versions of dimensions. The dictionary announces `monthly_snapshot`, pages 4 and 5. | The inventoried delivery contains one customers file and one products file, without the announced monthly snapshots. Some `last_updated` values reach June 2027. | Do not treat snapshot attributes as features available at an earlier date. Declare the available version and separate event time, ingestion time and observation time. |

The `complaints.currency` column is described as the currency of the claimed amount. The dictionary does not explicitly define the currency of `compensation_granted`. Do not assume they are the same, and do not execute compensations from that field without completing the simulator's contract.

A recent re-ingestion does not make historical data current. The acceptable staleness limit is defined per use case and applied to observations from the simulator. No real banking SLA is inferred from these CSVs.

## 4. Format and documentation differences

### INTEGER values serialized as decimals

There are 13 `INTEGER` columns with non-null values represented in decimal format, such as `700.0`. The additional check confirmed zero non-integral or invalid values in those columns. These are representation differences, not numbers that need to be rounded.

| Field | Values with non-canonical representation |
| --- | ---: |
| `customers.credit_score` | 127,508 |
| `products.days_past_due` | 125,350 |
| `service_agents.total_monthly_interactions` | 1,089 |
| `call_center_interactions.duration_seconds` | 590,062 |
| `call_center_interactions.wait_time_seconds` | 480,678 |
| `call_transcripts.duration_seconds` | 147,292 |
| `satisfaction_surveys.question_1_response` | 121,370 |
| `satisfaction_surveys.question_2_response` | 81,496 |
| `satisfaction_surveys.question_3_response` | 40,103 |
| `digital_events.duration_seconds` | 60,060 (sample only) |
| `complaints.resolution_days` | 15,363 |
| `complaints.resolution_satisfaction` | 2,484 |
| `campaign_sends.click_count` | 1,130 (sample only) |

The parser must check with decimal arithmetic that the value is finite, integral and representable by the target type. It can convert `700.0` to `700` without loss. It must reject `700.5` in an integer field and `200000.005` in a `DECIMAL(15,2)` (it would be stored as `200000.01`), and avoid conversions that silently truncate or round. `10.500` in that column is accepted: it is the same number. The comparison is made to 9 decimal places. These examples illustrate the rule and are not identifiers from the source. Keep the raw text.

This does not require re-normalizing the relational model. It is explicit CSV parsing.

### Categories described in English and values delivered in Spanish

The dictionary describes `products.product_type` with English names. The 400,000 products use eight categories in Spanish, such as `Cuenta Ahorro` and `Tarjeta Crédito`.

`call_center_interactions.reason_category` contains Spanish categories in the 686,296 rows. In addition, 20,578 contain `Retención`, which does not appear in the list of five categories on page 9.

Do not build a closed enum by copying those descriptions without checking it against the data. Keep the original value and agree on a versioned catalog of accepted values. If the application needs canonical codes, use an explicit, reviewed mapping. An unknown category must raise a schema/domain drift event, not a translation improvised by the LLM.

### Currency conversion and coverage

The exploratory comparison of `amount_usd` with the same-day exchange rate differs by more than one cent in 749,769 ARS rows and 1,031,847 COP rows. The dictionary does not define which rate, point in time or rounding convention produced `amount_usd`. It is a diagnosis pending clarification, not a confirmed financial error.

The absence of MXN transactions and the use of USD by Mexican customers describe the dataset's coverage. The customer's country does not mandate a transaction currency.

## 5. Checks that passed and limits of the review

In the inputs analyzed:

- No dictionary columns are missing, and no malformed records or missing or duplicate primary keys were found, according to the structural audit.
- No `VARCHAR` length overruns were detected, nor amounts outside the declared `DECIMAL` precision and scale. Parsing used decimal arithmetic, without rounding to make the checks pass.
- The only `NOT NULL` column with nulls found when checking the 136 constraints was `call_transcripts.duration_seconds`.
- Non-null booleans use `True` or `False`. That is the observed representation; the ingestion contract must declare which representations it accepts.
- The non-null dates and times checked could be parsed. This does not prove correct chronology, nor does it establish a time zone that is absent from the source.
- The reviewed ranges of `credit_score`, `avg_csat`, `fraud_score`, `sentiment_score`, `accent_confidence`, `resolution_satisfaction` and `main_score` for CSAT and NPS showed no out-of-range values. CES was not held to a range that the dictionary does not specify.
- The 154,157 non-null values of `mentioned_entities` are syntactically valid JSON. Their semantics still require checks if they are used to act.

The approximate proportions of duplicates or nulls in the PDF are not an exact count specification. Nor can it be concluded that a download was missing because the observed count differs from the approximate one. Ingestion completeness is checked against the selected object inventory.

The 42 distinct customer texts are a diversity and evaluation problem, not duplicate primary keys. They must block claims of linguistic generalization based on a random split, without deleting business records for sharing text.

## 6. Required pipeline behavior

The proposed sequence is raw ingestion → parsing and checks → publication per use. There is no need to redesign the tables or to repair the source automatically.

1. Record the object, size, hash, available version, ingestion timestamp and source line. Keep raw unmodified.
2. Validate the schema and convert types without loss. A missing key or an unparseable value goes to quarantine with a reason.
3. Check primary keys and the alternate `UNIQUE` fields. Separate exact duplicates from conflicting identities. DQ-001 and DQ-002 are conflicts, not identical rows that can be consolidated.
4. Run foreign keys, ownership, chronology and evidence gates on the joins the product will use.
5. Publish a view or snapshot with an explicit contract per use. A customer can be usable even if their registration branch is not. Serving must not expose the blocked join.
6. Publish atomically. An incomplete batch does not replace the previous one. Reprocessing the same bytes does not duplicate effects.
7. Generate a quality report per release. If no valid set remains for a use, disable that use and show the cause.

Future monthly snapshots must have a key that includes their version or period. The same identity in two snapshots is not a duplicate by itself. `UNIQUE` rules apply within the relevant version, not across the whole history without distinguishing snapshots.

The minimum report for each rule must include `rule_id`, version, basis type, table and fields, dataset version, rows evaluated, non-applicable nulls, affected groups where applicable, failed rows, blocked use and decision. Per-record examples must be kept with restricted access and lineage; shared documentation uses aggregate counts.

### Priority for the hackathon

First implement schema, parsing, PK, `UNIQUE`, ownership, chronology and currency for the selected flow. Apply freshness to the simulator's state. Branch relationships can remain disabled and documented if they play no part in the product; there is no need to repair them to move on.

Ingestion checks do not replace authorization, approval or verification at runtime. Before executing an action, re-check session, ownership, version and eligibility. Afterwards, read the result independently. The `Resolved` status of a historical row does not replace that verification.

## 7. Reference queries and expected results

These queries document the criteria and can be adapted to the chosen engine. They run on the analyzed version, with empty fields represented as NULL. They are not a complete shared pipeline. No source rows or credentials are included.

### DQ-001 and DQ-002: uniqueness outside the primary key

```sql
SELECT COUNT(*) AS conflicting_values,
       SUM(n) AS affected_rows,
       SUM(n - 1) AS excess_rows
FROM (
  SELECT product_number, COUNT(*) AS n
  FROM products
  WHERE product_number IS NOT NULL
  GROUP BY product_number
  HAVING COUNT(*) > 1
) conflicts;
-- Expected: 6 values, 12 affected rows, 6 in excess.
-- Repeat for service_agents.employee_code:
-- 13 values, 26 affected rows, 13 in excess.
```

### DQ-003 and DQ-004: nonexistent references

```sql
SELECT COUNT(*) AS failed_rows
FROM customers c
LEFT JOIN branches b ON b.branch_id = c.registration_branch_id
WHERE c.registration_branch_id IS NOT NULL AND b.branch_id IS NULL;
-- Expected: 149995.
-- Repeat for service_agents.assigned_branch_id: 831.
```

### DQ-005: empty mandatory field

```sql
SELECT COUNT(*) AS failed_rows
FROM call_transcripts
WHERE duration_seconds IS NULL;
-- Expected: 24029.
```

### DQ-006: the foreign key exists, but the customer is a different one

```sql
SELECT COUNT(*) AS failed_rows
FROM complaints c
JOIN products p ON p.product_id = c.affected_product_id
WHERE c.customer_id <> p.customer_id;
-- Expected: 44570. Check missing references separately.
```

### DQ-009 and DQ-010: insufficient evidence

```sql
SELECT COUNT(*) AS failed_rows
FROM complaints
WHERE claimed_amount IS NOT NULL AND currency IS NULL;
-- Expected: 1040.

SELECT COUNT(*) AS insufficient_evidence
FROM complaints
WHERE status IN ('Resolved', 'Closed')
  AND (resolution_date IS NULL OR resolution IS NULL);
-- Expected: 1549, without counting twice the records that have both fields empty.
```

Temporal rules compare already-parsed dates, not strings in arbitrary formats. For transactions, `transaction_date >= registration_date` is required, and their calendar date must not precede `opening_date`, which the dictionary defines as DATE. Do not infer an intraday opening time or a time zone that does not exist in the source.

## 8. Acceptance tests for the future implementation

- Detect the 6 conflicting product numbers and 13 conflicting employee codes without merging identities.
- Block the 44,570 complaint-product joins with incorrect ownership, while keeping the complaint's independent uses.
- Distinguish the 24,029 nulls in a mandatory field from the nulls permitted in optional references.
- Convert integers with a `.0` suffix without loss, and reject real fractions in INTEGER columns and decimals with more digits than the scale in DECIMAL columns.
- Block monetary decisions based on the 1,040 claimed amounts without a currency.
- Do not declare the resolutions of the 1,549 complaints with incomplete evidence as verified based on the historical status alone.
- Test a replay, a truncated file, a conflicting correction and a new column with identified fixtures. Keep the previous valid publication on failure.
- If the source changes, compare counts with a versioned baseline and explain the variation. The counts in this report are an audit result, not permanent acceptance thresholds.

## 9. Status in the code (2026-09-29)

Which parts of sections 6 and 8 the repository's pipeline runs today, and with which test (`make validate-data-ml`
runs the ones in `tests/test_data_ml_validation.py`; the rest are in `tests/test_pipeline.py` and `tests/test_cross_checks.py`).

| Requirement | Status | Where |
|---|---|---|
| §6.1 object, size, hash, timestamp, source line; raw unmodified | Done, except for the S3 object version | `_source_files` (path, URI, size, SHA-256), `_ingestion_log` (contract and code version), `_run_id`/`_source_file`/`_ingested_at` per row; `test_lineage_*` |
| §6.2 schema and types without loss; missing key or unparseable value to quarantine with a reason | Done | `data/quality.py`; `test_contracts_*`, `test_integer_columns_accept_700_point_0_and_reject_700_point_5`, `test_decimal_columns_accept_trailing_zeros_and_reject_digits_beyond_the_scale`, `test_contracts_a_value_that_would_be_rounded_*` |
| §6.3 PK and `UNIQUE` fields | PK deduplicated; `UNIQUE` measured as a warning (`cross:product_number_unique` = 6), without merging. `service_agents` is not ingested | `data/contracts.py`; `tests/test_cross_checks.py` |
| §6.4 FK, ownership, chronology and evidence gates | Measured as warnings; nothing served uses a blocked join | `CROSS_TABLE_CHECKS`, `DOMAIN_RULES` |
| §6.5 views per use | Not done: there is one served table per entity; the blocked joins are not exposed because the tools do not use them | `agent/tools/account_tools.py` |
| §6.6 atomic publication, reprocessing without duplicating | Done | one transaction per table; `test_contracts_over_the_quarantine_threshold_*`, `test_late_arriving_partition_updates_in_place_and_is_idempotent` |
| §6.7 report per release; disable the use with no valid set | Report done; the use is not disabled automatically (the freshness policy does that, if enabled) | `data/reports/quality_report.json`, `test_quality_*`, `test_freshness_*` |
| §8 replay, truncated file, conflicting correction, new column; the previous state survives a failure | Done | `test_late_arriving_partition_*`, `test_contracts_a_truncated_file_*`, `test_schema_evolution_adds_new_column`, `test_quality_gate_rolls_back_*` |
| §8 counts against a versioned baseline | The full-run report is versioned, and the doc that cites it is checked against it | `test_quality_the_committed_full_run_report_*` |

