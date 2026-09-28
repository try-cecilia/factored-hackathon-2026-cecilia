# Data engineering: contracts, quality, lineage, freshness

## Pipeline

`python -m data.pipeline` (see `make ingest`, `make ingest-demo`). Sources are
the organizer's read-only S3 bucket or a local directory, which is what the
tests use with hand-made fixtures.

| Profile | Tables | Used by |
|---|---|---|
| serving | branches, daily_exchange_rates, customers, products, transactions | the agent's tools |
| analysis | call_center_interactions, call_transcripts, satisfaction_surveys | problem evidence and baseline only |

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
   agreement, currency vs country.
8. **Lineage.**
   - `_ingestion_log`: one row per table per run (mode, files, bytes,
     partition range, row counts, contract version, code version, parameters).
   - `_partition_log`: one row per daily partition loaded.
   - `_dq_results`: every check result.

   The JSON report is written to `--report` (`data/reports/quality_report.json`
   by default; in the container, next to the warehouse on the persistent disk)
   and exposed at `/admin/data_quality`.

Contracts live in `data/contracts.py`, contract version 2.0.0.

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

Full run 20260926T012329Z: 8 tables, 6.06M rows, 238 checks, **0 errors, 6 warnings**,
0 rows quarantined.

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

The quality gate was exercised on real data at least once: the first full run
quarantined 14% of `call_transcripts` over the `duration_seconds` NOT NULL rule
and rolled back that table's load. That led to the explicit deviation above
rather than a silently relaxed contract.
