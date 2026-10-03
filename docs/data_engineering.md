# Data engineering: layers, measured load, guarantees

Start at [DATA.md](DATA.md) for the overview. `docs/data_quality.md` has the contract, checks and findings; this page
says how the data flows, what a full load costs, which guarantees are tested, and what we did not build.

## The layers, by their usual names

We did not build a Delta lakehouse. We have the same separation of concerns inside one DuckDB file, plus an open Parquet
copy, and we say where it differs from a textbook medallion:

| Layer | In this repository | Differs from a textbook layer in |
|---|---|---|
| **Bronze**: the data as delivered | The organizer's original CSV files, read from a local directory or from a local cache of the S3 objects under `--raw-dir` (downloaded as they are), and never rewritten. Each load records every file's size and SHA-256 in `_source_files` | No separate bronze store: the hash is the proof of what was read. A raw staging table exists only inside the load's transaction |
| **Silver**: typed, validated, de-duplicated | `branches`, `customers`, `products`, `transactions`, `daily_exchange_rates` (serving) and `call_center_interactions`, `complaints`, `call_transcripts`, `satisfaction_surveys` (analysis): `TRY_CAST` to the dictionary's types, contract checks, bad rows moved to `_quarantine_<table>`, latest record wins, upsert by primary key. Every row carries `_source_file`, `_run_id`, `_ingested_at` | One layer serves the agent directly: there is no separate cleaned copy |
| **Gold**: business-ready aggregates | Three marts, built by `python -m data.gold` (`make gold`): `gold_daily_activity`, `gold_customer_summary` and `gold_contact_demand`. Each declares its columns and types and its grain, and is reconciled to the silver rows it summarizes | The baseline report reads five of its figures from `gold_contact_demand`; the agent and the other reports still read silver. There is no feature store |
| **Open copy**: silver and gold as Parquet | `python -m data.lake` (`make lake`): one zstd file per table and a `manifest.json` with each file's rows, size, SHA-256 and columns, and the silver and gold runs it was written from | A copy for portability and checking, not a second source of truth: the warehouse stays the one the agent reads |

The figure of the flow, with the row count of every table, one row traced from its file to the agent, and the checks of
the last full load are in [DATA.md](DATA.md), generated from the committed reports.

A table whose quarantine rate passes `--max-quarantine-rate` (by default 1% of that table's batch) or that lacks a required column
rolls back: that table keeps its previous state, earlier tables in the run stay committed, and the run stops
(`data/pipeline.py`).

## One command

`make pipeline` runs ingest, gold, `gold VERIFY=1`, lineage, lake and `lake VERIFY=1` in that order and stops at the first
step that fails. `INGEST=ingest-local` reads the folder in `RAW_DATA_DIR` (`data/raw` by default) instead of S3, and the
lineage step re-hashes the files in that same folder, so a load from anywhere else is checked against where it came from
(`tests/test_makefile_raw_dir.py`). The load below was run step by step on Windows, where there is no `make`; the chain as one
command was run later with `make` (see "Run again, on another machine").

## What a full load costs (measured)

**Measurements by Ivan, from PR #21, not reproduced in this integration** (the raw files and S3 were not available here). Everything below is from one run, `20261001T022411Z-5bf225`, local files into a new DuckDB file, with nothing else running:
Windows 11 (10.0.26200) on AMD64, 12 logical CPUs, Python 3.11.8, DuckDB 1.5.5 with 12 threads and a 1.8 GiB memory
limit. The machine is now recorded in each load's `params` (`_ingestion_log`), so a later figure can be read against it.

| Table | Profile | Files | Size | Rows | Quarantined | Seconds |
|---|---|---|---|---|---|---|
| branches | serving | 1 | 0.1 MB | 350 | 0 | 0.6 |
| daily_exchange_rates | serving | 1 | 0.8 MB | 13,164 | 0 | 0.4 |
| customers | serving | 1 | 46.9 MB | 150,000 | 0 | 4.3 |
| products | serving | 1 | 68.2 MB | 400,000 | 0 | 8.9 |
| transactions | serving | 1,097 | 808.3 MB | 4,425,008 | 0 | 221.9 |
| call_center_interactions | analysis | 1,097 | 139.7 MB | 686,296 | 0 | 49.1 |
| complaints | analysis | 1,097 | 18.0 MB | 67,095 | 0 | 23.0 |
| call_transcripts | analysis | 1,097 | 137.2 MB | 171,321 | 0 | 18.5 |
| satisfaction_surveys | analysis | 1,097 | 46.4 MB | 212,759 | 0 | 21.4 |
| **Total** | | **5,489** | **1,266 MB** | **6,125,993** | **0** | **349** |

The serving profile is 4,988,522 rows in 236 s and the analysis profile 1,137,471 rows in 112 s; `transactions` loads at
about 20,000 rows per second. The run passed with 0 failed errors and 16 failed warnings out of 294 checks.

**An earlier figure, and why it is gone.** An earlier version of this page said the serving profile loaded in 143 s
(`transactions` in 130 s). That came from a load on 2026-09-29 with code `17fe081` and no host recorded. The serving tables
run the same 161 checks in both, so the number of checks does not explain the difference, and we do not know what does:
the machine's state, the file cache, or the code between the two commits. It cannot be reproduced, so it is no longer
cited. A run that overlapped with our test suite took 234 s for `transactions`, which is why the table above is from a run
with nothing else going.

The same page also said the analysis profile was "about 18 million rows". That was wrong: the 18 million are the
organizer's tables we do not ingest (digital events, campaign sends and others). The four analysis tables are 1.14 million.

## The gold marts

| Mart | Grain | Rows (full warehouse) | Answers |
|---|---|---|---|
| `gold_daily_activity` | day, country, currency, type, status | 178,941 | How much moves each day, and in what currency and state |
| `gold_customer_summary` | customer | 134,515 | How many movements a customer has, over what span, through how many channels, countries and products |
| `gold_contact_demand` | month, customer country, channel, reason category | 3,927 | How many contacts there are, how many were resolved or followed up, and how long they took |

Each build runs inside one transaction and checks, before it commits, three things: the columns, in order and with their
types, are the contract declared in `MARTS`; the grain is unique; and the mart adds up to silver (row counts, and amounts
for `gold_daily_activity`). If a check fails the transaction rolls back and the previous mart stays. `_gold_log` keeps one
row per mart and build, with the SQL's SHA-256, the silver loads it read and the code version, and every mart row carries
`_gold_run_id` and `_built_at`. `make gold VERIFY=1` re-checks the built marts against silver, so a silver reload after the
build shows up as a mismatch. A mart whose source tables are not in the warehouse is skipped and says so: the deployment's
serving warehouse has no contact-center tables.

**Who reads them.** `analysis/baseline_contact_center.py` takes its contact reasons, the channel mix, the share of text
channels, contacts by country and the monthly median of transactional contacts from `gold_contact_demand`, and stops with
"run `make gold`" if the mart is missing (`make analysis` builds it first). The figures are the same ones the raw contacts
give: `tests/test_baseline_gold.py` compares both on a fixture that includes a contact whose customer is unknown, and the
committed `docs/evidence/baseline_metrics.json` came out identical after the change. The report's other figures need columns
the mart does not carry (segment, hour of day, the survey join) and still read silver.

The three marts build in 3.9 s on the database above (Ivan's measurement from PR #21, not reproduced in this integration; so are the 3,927 rows of `gold_contact_demand` in the table above).

## The Parquet copy

`make lake` writes one zstd Parquet file per silver table and gold mart under `data/lake/` (git-ignored), then a
`manifest.json` last, so a half-written export has none. On the database above (Ivan's measurements from PR #21, not reproduced in this integration): 12 files, **284 MB** against 1,266 MB of
source CSV, written in 5.0 s. `make lake VERIFY=1` needs no warehouse: it re-hashes every file and reads its row count and
schema back, and with the warehouse it also compares each table's row count. It took 0.7 s there. A file that was edited,
truncated, swapped or deleted fails, as does a warehouse table that changed after the export (`tests/test_lake.py`).

## Run again, on another machine

The same commands were run with `make` on macOS (Apple M5 Pro, 18 logical CPUs, Python 3.11.16, DuckDB 1.5.5), on a copy of
the serving warehouse kept in `/tmp` (the same 4,425,008 `transactions`, 150,000 customers, 400,000 products and 67,095
complaints as above; the raw files and the other analysis tables were not on that machine). The machine was busy (load
average above 80 from other test suites), so the times are an upper bound.

| Step | What it did | Seconds |
|---|---|---|
| `make gold` | built `gold_daily_activity` (178,941 rows) and `gold_customer_summary` (134,515 rows); `gold_contact_demand` skipped, as there is no `call_center_interactions` there | 1.4 to 2.4 |
| `make gold VERIFY=1` | totals still add up | 0.2 |
| `make lake` | 8 files, 253.7 MB | 1.7 to 1.8 |
| `make lake VERIFY=1` | every file matches the manifest, and the row counts match the warehouse | 0.3 |

The two marts' row counts are the ones in the table above. The 3.9 s, 12 files, 284 MB and 5.0 s of this page (Ivan's measurements from PR #21) include
`gold_contact_demand` and the contact tables, which this copy lacks, so they were not reproduced and are not corrected.
`make pipeline INGEST=ingest-local RAW_DATA_DIR=<folder outside the repository>`, the whole chain in one command, ran on the
test fixtures in 1.6 s with every step exiting 0, lineage included.

## Guarantees and the test that holds each one

| Guarantee | Test |
|---|---|
| Contracts, de-duplication and lineage columns on every row | `tests/test_pipeline.py::test_contracts_dedup_and_lineage` |
| A re-delivered or late partition updates in place; replays change nothing | `test_late_arriving_partition_updates_in_place_and_is_idempotent`, `test_s3_partition_replay_is_idempotent` |
| `--incremental` reads only the lookback window | `test_incremental_reads_only_the_lookback_window` |
| Over the quarantine threshold the load rolls back; under it, rows are quarantined | `test_quality_gate_rolls_back_then_quarantines_under_threshold` |
| A new column is added, not dropped; a missing required column fails | `test_schema_evolution_adds_new_column`, `test_complaints_quality_gate_and_missing_schema_roll_back` |
| Lineage times are UTC whatever the machine's time zone | `test_lineage_times_are_utc_whatever_the_machine_time_zone` |
| Each load records the machine it ran on | `test_each_load_records_the_machine_it_ran_on` |
| A served row traces back to its load and its file's hash | `python -m data.lineage --verify --raw-dir $RAW_DATA_DIR` (`make lineage`; the folder `make ingest-local` loads from, `data/raw` by default) | `tests/test_makefile_raw_dir.py`
| Contracts, quality, lineage and freshness pass as a whole | `make validate-data-ml`, which CI runs through `make gate` |
| A gold mart has the declared columns and a unique grain, adds up to silver, keeps the previous version when a check fails, and names the loads it read | `tests/test_gold.py` |
| The baseline's gold-derived figures equal the ones the raw contacts give | `tests/test_baseline_gold.py` |
| The Parquet copy reads back as its tables, and a changed copy is caught | `tests/test_lake.py` |

## What we did not build

- **No Delta and no Databricks.** DuckDB over CSV, loaded in one process, with a Parquet copy. Parquet is an open format,
  not a lakehouse: no table versions, no time travel, no concurrent writers.
- **The agent does not read gold.** Only the baseline report does, and only five of its figures.
- **No scheduler for ingestion or for the marts.** `make pipeline` is a command, run by hand or at deploy. Only retention
  runs on a schedule.
- **The deployment serves a sample.** Render loads 5,000 customers since 2025-06-17 (`render.yaml`), not the full estate,
  because of its 512 MB instance, and has no contact-center tables, so `gold_contact_demand` is not built there.
- **The Parquet copy is not published anywhere.** It is written to a local directory and not part of the repository.
- **One writer.** The warehouse is one DuckDB file; there is no concurrent loading.
