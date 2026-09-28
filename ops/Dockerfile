FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# curl for the health check; util-linux for setpriv (the entrypoint drops root after preparing the data disk)
RUN apt-get update && apt-get install -y --no-install-recommends curl util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY data/ ./data/
COPY agent/ ./agent/
COPY api/ ./api/
COPY eval/ ./eval/
COPY ops/ ./ops/
# The hand-made fixture warehouse: the CI boot test, and a deploy before the organizer's dataset is reachable
COPY tests/fixtures/raw/ ./tests/fixtures/raw/
RUN chmod +x ./ops/entrypoint.sh && touch ops/__init__.py

ENV DUCKDB_PATH=/app/data/warehouse/bank.duckdb \
    RAW_DATA_DIR=/app/data/raw \
    DUCKDB_MEMORY_LIMIT=400MB \
    INGEST_ARGS="--profile serving --sample-customers 5000 --since 2025-06-17" \
    SESSION_TTL_SECONDS=900

# The app runs as this unprivileged user. The container starts as root only so the entrypoint can hand it the
# data directories, which a platform may mount owned by root (Render's persistent disk), and then drops to it.
RUN useradd --create-home --uid 10001 agent && mkdir -p /app/data/warehouse /app/data/raw /app/data/reports \
    && chown -R agent:agent /app/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=900s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

ENTRYPOINT ["./ops/entrypoint.sh"]
