# Data engineering: contracts, quality, lineage, freshness

## Pipeline

`python -m data.pipeline` (see `make ingest`, `make ingest-demo`). Sources are
the organizer's read-only S3 bucket or a local directory, which is what the
tests use with hand-made fixtures.

| Profile | Tables | Used by |
|---|---|---|
| serving | branches, daily_exchange_rates, customers, products, transactions | the agent's tools |
| analysis | call_center_interactions, complaints, call_transcripts, satisfaction_surveys | problem evidence and offline analysis only |

Per table, inside one transaction:

1. **Raw staging.** CSVs are read as-is, with lineage columns added:
   `_source_file`, `_run_id`, `_ingested_at`.
2. **Schema drift** (`quality.schema_drift`):
   - a missing required column fails the load;
   - a missing optional column is a warning;
   - new columns are a warning, and they are **added** to the table (schema evolution), never silently dropped.
3. **Typed staging.** Every column is `TRY_CAST` to the data dictionary's type.
   A non-null value that fails its cast is a contract violation.
4. **Measure.** Checks and their severity:

   | Check | Severity |
   |---|---|
   | Primary-key duplicates in the batch | warn |
   | Type conformance | error |
   | NOT NULL | error |
   | Null rate of every nullable column | info |
   | Domain rules (enums, ranges) | error or warn |
   | Pydantic row contract on a 1,000-row sample (an independent second implementation of the contract) | error |

5. **Quarantine.** Rows breaking any error-level rule go to `_quarantine_<table>`
   with the failed rules listed. If more than 1% of the batch is quarantined
   (`--max-quarantine-rate`), the whole load **rolls back** and the warehouse
   keeps its previous state.
6. **Dedup and upsert.** The latest record wins (`last_updated`, else the later
   source file, i.e. the later partition), then upsert by primary key.
   Replays are idempotent.
7. **Cross-table checks.** FK orphans, transaction/product ownership
   agreement, complaint/product ownership, currency vs country, keys the
   dictionary declares unique besides the primary key, dates before the
   product's opening or the customer's registration, and dimension rows
   updated after the data's as-of date. If a required parent table is absent,
   the report records an info result in the `dependency` category with the
   missing table name. It counts executed and not-run checks separately and
   does not report the skipped check as passed.
8. **Lineage.**
   - `_ingestion_log`: one row per table per run (mode, files, bytes,
     partition range, row counts, contract version, code version, parameters).
   - `_partition_log`: one row per daily partition loaded.
   - `_dq_results`: every check result.

   The JSON report is written to `--report` (`data/reports/quality_report.json`
   by default; in the container, next to the warehouse on the persistent disk)
   and exposed at `/admin/data_quality`. Lineage times are UTC on any machine.

   In the jury demo (`DEMO_MODE=1`), the **Data quality** view
   (`/demo/data_quality`) shows anyone the warehouse being served as these
   tables describe it (rows, daily partitions, loads and the last good one,
   the checks of that load that did not pass, the as-of date and the freshness
   policy), the committed report of the complete-dataset run and the contract
   with its deviations. Aggregates only: no rows, no source locations (on a
   deploy they name the organizer's bucket) and no error text.

Contracts live in `data/contracts.py`, contract version 2.1.0.

## Complaints ingestion

`complaints` is a customer-scoped daily table in the `analysis` profile. The
source adapter resolves the same layout used by the other daily facts:
`data/complaints/year=YYYY/month=MM/day=DD/*.csv`. It does not depend on a
particular CSV basename. The dictionary defines the table on pages 12 and 13
and its foreign keys on pages 15 and 16.

The primary key is `complaint_id`. The source has no update timestamp, so a
duplicate uses the pipeline's existing fallback: the row from the later source
path wins. Incremental loads still apply the configured lookback and upsert by
primary key. `tests/fixtures/raw_complaints_late/` covers a corrected row, a
new row, and an idempotent replay.

This local command loads only the synthetic fixture and writes both the
warehouse and report outside the repository:

```bash
DUCKDB_PATH=/tmp/cecilai-complaints.duckdb python -m data.pipeline \
  --tables complaints --source local --raw-dir tests/fixtures/raw \
  --report /tmp/cecilai-complaints-quality.json
```

For S3, `--tables complaints` works against an existing warehouse. Load
`branches`, `customers`, `products`, and `call_center_interactions` first if
the run must execute every available relationship check. The repository does
not ingest `service_agents`, so the assigned-agent check is recorded as not run
unless that table already exists. A complaint-only load with no parents is
valid, but its report names the checks it could not run.

The ownership check is a warning, not a quarantine rule. It keeps the complaint
and counts cases where `affected_product_id` belongs to another customer. Code
must not use that relationship for serving, authorization, or labels. Null
`origin_interaction_id` values are allowed and included in the column's null
coverage. Non-null values are checked only when interactions are present.
`compensation_granted` has no documented currency. Ingestion does not infer one.

## Update and freshness policy

- **Unit of update:** the daily partition (`year=/month=/day=`).
  `--incremental` reloads from (watermark − `--lookback-days`, default 3)
  onward, so late or re-delivered partitions are absorbed.
- **Update correctness** is tested with a clearly labeled fixture
  (`tests/fixtures/raw_late/`): a re-delivered partition with one corrected
  amount and one new row updates in place, adds exactly one row, and a replay
  changes nothing (`tests/test_pipeline.py`).
- **Batch, not streaming.** The source is daily files with no latency
  requirement below a day, so streaming would add cost without value, as the
  brief itself notes.
- **As-of date.** The warehouse's as-of date (`max(process_date)`, 2026-06-17
  for this dataset) is stated in every answer.
- **Freshness SLO.** With `FRESHNESS_ENFORCE=1`, balance and transaction
  answers become "data unavailable → escalate" when the warehouse is older
  than `FRESHNESS_SLO_HOURS` (default 36). It is off by default only because
  this dataset is a static 2023–2026 snapshot (tested in
  `tests/test_tools_and_grounding.py`).

## Findings on the supplied data

Full run 20260929T145046Z (`data/reports/quality_report.json`, also shown in the demo's Data quality view):
9 tables, 6.13M rows (including the audit's 67,095 complaint rows), 294 checks (295 with one that did not run), **0 errors, 16 warnings**, 0 rows
quarantined. The 246 checks of the previous full run (20260928T204248Z, 8 tables) give the same results, check for
check, and so did the runs of 2026-09-28 (20260928T153707Z) and 2026-09-26 (20260926T012329Z) on their first 238.
The 4 new warnings come from the complaints table and one category rule: `reason_category_in_dictionary` (20,578
of 686,296 contacts, 3.0%), `claimed_amount_has_currency` (1,040), `resolved_has_evidence` (1,549) and
`customer_owns_affected_product` (44,570 of 44,570 checked, 100%).

| Finding | Evidence | What the system does about it |
|---|---|---|
| `transactions.amount_usd` null in **57.3%** of rows (the dictionary implies every row has it) | warn `usd_amount_present` 2,537,456 / 4,425,008 | the agent never uses `amount_usd`; it converts via `daily_exchange_rates` and says which date it used |
| **12,983** credit products lack `credit_limit` or `days_past_due`; **6,622** lack `days_past_due` | warn `credit_fields_present` | payment-status questions on those escalate as *data unavailable* instead of guessing |
| **31,156** Closed products with a non-zero balance | warn `closed_has_zero_balance` | answers show product status next to every balance |
| `customers.registration_branch_id` matches no branch for **149,995 / 150,000** customers (150,000 distinct ids vs 350 branches) | cross `fk_registration_branch` | branch data isn't used by this workflow; reported |
| No product or transaction is in **MXN**; all 200,398 Mexican customers' products are in USD | `docs/evidence/baseline_metrics.md` | FX answers default to USD→local and are always explicit about currencies |
| 100% of transcript `agent_text` contain unrendered placeholders (`{monto}`); only **42 distinct** customer texts in 171K transcripts; text doesn't vary with contact reason | warn `agent_text_rendered`; baseline report | transcripts can't serve as training or evaluation text → held-out set written separately (see EVALUATION.md) |
| `contact_reason` = `reason_category` in 100% of rows | baseline report | treated as one field |
| `call_transcripts.duration_seconds` null in **14.0%** though the dictionary says NOT NULL | warn `dictionary_not_null:duration_seconds` | documented **contract deviation** (warn, not quarantine; analysis-only column), in `CONTRACT_DEVIATIONS` |
| Dictionary lists product types in English; data ships them in Spanish (`Tarjeta Crédito`) | enum rules | contracts follow the data; the mismatch is recorded here, not "fixed" |
| Documented ~2% duplicates and late arrivals **not observed** in these tables | `pk_duplicates_in_batch` = 0, `not_late_arrival` = 0 | dedup and lookback stay in place (and are tested with fixtures) because the dictionary says they can happen |
| **827,610** movements (18.7%) are dated before their product was opened and **829,540** (18.7%) before their customer registered; 1,450,689 (32.8%) break one or the other, and 11.9% do in the last 12 months (the window the demo serves) | warn `cross:tx_not_before_product_opening`, `cross:tx_not_before_customer_registration` | kept as delivered: answers show every movement with its date, and the checks count them on every load |
| **128,316** contacts (18.7%) happened before the customer registered | warn `cross:contact_not_before_registration` | the baseline counts them; leaving them out moves the transactional share from 35.0% to 34.9% |
| **25,113** products and **9,316** customers were last updated after the data's as-of date, as late as 2027-06-15 | warn `cross:products_not_updated_after_as_of`, `cross:customers_not_updated_after_as_of` | dedup keeps the latest `last_updated`, so a later, real correction would lose to one of these rows; no duplicate reached dedup in this dataset, so no answer changes today |
| **6** product numbers are shared by two customers' products, though the dictionary declares the number unique | warn `cross:product_number_unique` | ownership is checked by `product_id`, and the number is only ever shown as its last 4 digits (`document_number` and `branch_code`, also declared unique, pass) |

The quality gate was exercised on real data at least once: the first full run
quarantined 14% of `call_transcripts` over the `duration_seconds` NOT NULL rule
and rolled back that table's load. That led to the explicit deviation above
rather than a silently relaxed contract.
