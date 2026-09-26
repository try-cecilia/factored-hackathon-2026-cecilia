FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY data/ ./data/
COPY agent/ ./agent/
COPY api/ ./api/
COPY eval/ ./eval/
COPY ops/ ./ops/
RUN chmod +x ./ops/entrypoint.sh && touch ops/__init__.py

ENV DUCKDB_PATH=/app/data/warehouse/bank.duckdb \
    RAW_DATA_DIR=/app/data/raw \
    DUCKDB_MEMORY_LIMIT=400MB \
    INGEST_ARGS="--profile serving --sample-customers 5000 --since 2025-06-17" \
    SESSION_TTL_SECONDS=900

# Non-root runtime user; the warehouse/raw dirs are its only writable paths.
RUN useradd --create-home --uid 10001 agent && mkdir -p /app/data/warehouse /app/data/raw /app/data/reports \
    && chown -R agent:agent /app/data
USER agent

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=900s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

ENTRYPOINT ["./ops/entrypoint.sh"]
