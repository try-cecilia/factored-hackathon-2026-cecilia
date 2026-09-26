#!/bin/sh
set -e

# First boot with no warehouse: ingest. Default INGEST_ARGS is a deterministic
# 5k-customer / 12-month sample (~15 MB, fits a 512 MB free tier). For the full
# dataset set INGEST_ARGS="--profile serving" and give the container ~2 GB.
# Production note: ingest on a schedule into persistent storage instead of at
# boot (see LIMITATIONS.md).
if [ ! -f "$DUCKDB_PATH" ]; then
  echo "[entrypoint] no warehouse at $DUCKDB_PATH; ingesting with: $INGEST_ARGS"
  python -m data.pipeline $INGEST_ARGS --report /app/data/reports/quality_report_boot.json
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
