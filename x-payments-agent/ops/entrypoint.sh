#!/bin/sh
set -e

# Started as root: only to hand the data directories to the app user (a persistent disk may be mounted owned by
# root), then everything below runs as that user.
if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/data/warehouse /app/data/raw /app/data/reports
  chown -R agent:agent /app/data
  exec setpriv --reuid=agent --regid=agent --init-groups "$0" "$@"
fi

# First boot with no warehouse: ingest. Default INGEST_ARGS is a deterministic
# 5k-customer / 12-month sample (~15 MB, fits a 512 MB instance). For the full
# dataset set INGEST_ARGS="--profile serving" and give the container ~2 GB.
# Without the organizer's S3 access, INGEST_ARGS="--profile serving --source local
# --raw-dir /app/tests/fixtures/raw" loads the hand-made fixture instead.
# Production note: ingest on a schedule into persistent storage instead of at
# boot (see LIMITATIONS.md).
# The quality report goes next to the warehouse, on the persistent disk, where
# /admin/data_quality reads it. The warehouse is built under a temporary name and
# renamed only after the load succeeded: a load that fails, or that is killed half
# way (a cancelled deploy, out of memory), leaves nothing a later boot could take
# as loaded, and that boot loads again.
if [ ! -f "$DUCKDB_PATH" ]; then
  building="$DUCKDB_PATH.building"
  rm -f "$building" "$building.wal" "$DUCKDB_PATH.wal"  # what a killed boot left; a stale WAL would be replayed
  echo "[entrypoint] no warehouse at $DUCKDB_PATH; ingesting with: $INGEST_ARGS"
  if ! DUCKDB_PATH="$building" python -m data.pipeline $INGEST_ARGS --report "${DQ_REPORT_PATH:-/app/data/warehouse/quality_report.json}"; then
    rm -f "$building" "$building.wal"
    echo "[entrypoint] ingestion failed: nothing was kept, so the next boot loads again" >&2
    exit 1
  fi
  if [ -f "$building.wal" ]; then mv "$building.wal" "$DUCKDB_PATH.wal"; fi  # normally checkpointed on close
  mv "$building" "$DUCKDB_PATH"  # same directory: an atomic rename
fi

if [ -z "$DEMO_IDP_SECRET" ]; then
  echo "[entrypoint] WARNING: DEMO_IDP_SECRET not set; /auth/session will refuse all logins (fails closed)"
fi
if [ -z "$DEMO_PUBLIC_CUSTOMERS" ]; then
  DEMO_PUBLIC_CUSTOMERS="$(python -m ops.demo_customers)"
  export DEMO_PUBLIC_CUSTOMERS
  echo "[entrypoint] sandbox demo customers: $DEMO_PUBLIC_CUSTOMERS"
fi

exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
