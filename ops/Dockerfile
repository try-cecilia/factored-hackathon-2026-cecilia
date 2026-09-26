FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY data/ ./data/
COPY agent/ ./agent/
COPY api/ ./api/
COPY eval/ ./eval/
COPY ops/entrypoint.sh ./ops/entrypoint.sh
RUN chmod +x ./ops/entrypoint.sh

ENV DUCKDB_PATH=/app/data/warehouse/bank.duckdb
ENV RAW_DATA_DIR=/app/data/raw

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["./ops/entrypoint.sh"]
