#!/bin/sh
set -e

# First boot on a fresh volume/container: no warehouse yet, so ingest from S3.
# Production note: this is a hackathon-prototype simplification — a real
# deployment would ingest on a schedule into a persistent volume/object store
# and never block request-serving startup on a full re-ingestion. See
# LIMITATIONS.md.
if [ ! -f "$DUCKDB_PATH" ]; then
  echo "[entrypoint] No warehouse found at $DUCKDB_PATH — running initial ingestion from S3..."
  python -m data.pipeline
fi

exec uvicorn api.main:app --host 0.0.0.0 --port 8000
