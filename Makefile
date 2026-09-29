# Reproducible entry points. Every number in the docs comes from one of these.
PY ?= python3
PNPM ?= pnpm
API_HOST ?= 0.0.0.0
API_PORT ?= 8000
WEB_HOST ?= 127.0.0.1
WEB_PORT ?= 3000
# Combined development always connects to its local API, unless overridden.
AGENT_API_URL ?= http://127.0.0.1:$(API_PORT)

.PHONY: gate operator-labels retention loadtest setup ingest ingest-demo analysis train-eval workload eval eval-adversarial eval-live live-smoke test serve docker-build all mlflow-ui
.PHONY: web-setup serve-web web-build web-typecheck serve-all
.PHONY: env up down monitoring-up up-llm-local up-llm-host up-dataset lock lock-check alerts-check compose-e2e
COMPOSE = docker compose -f ops/docker-compose.yml --env-file .env
GPU_FILE = $(if $(GPU),-f ops/docker-compose.gpu.yml)
# The model-serving choices below only set what the API is told; the `local` provider itself is agent/llm/client.py's
LOCAL_IN_COMPOSE = LLM_PROVIDERS=local LOCAL_LLM_BASE_URL=http://ollama:11434/v1
LOCAL_ON_HOST = LLM_PROVIDERS=local LOCAL_LLM_BASE_URL=http://host.docker.internal:11434/v1

web-setup:        ## install the frontend's pinned dependencies (Node 24, pnpm 10.33.2)
	$(PNPM) --dir web install --frozen-lockfile

serve-web:       ## frontend only; AGENT_API_URL can also come from web/.env
	$(PNPM) --dir web dev --host "$(WEB_HOST)" --port "$(WEB_PORT)"

web-build:        ## build the TanStack Start client and server
	$(PNPM) --dir web build

web-typecheck:    ## check frontend TypeScript
	$(PNPM) --dir web typecheck

serve-all:       ## run serve and serve-web; stop both when either exits
	AGENT_API_URL="$(AGENT_API_URL)" $(PNPM) --dir web exec concurrently --kill-others --kill-timeout 5000 --names api,web \
		"$(MAKE) -C .. serve" "$(MAKE) -C .. serve-web"

setup:            ## install the locked dependencies (exact versions and hashes), with experiment tracking (the serving image takes requirements.txt only)
	$(PY) -m pip install --require-hashes -r requirements-tracking.txt

lock:             ## regenerate both lock files (versions and sha256 of every wheel) from requirements*.in
	uv pip compile requirements.in --universal --python-version 3.11 --generate-hashes -o requirements.txt
	uv pip compile requirements-tracking.in --universal --python-version 3.11 --generate-hashes -o requirements-tracking.txt

lock-check:       ## fail if a lock file no longer matches its .in (the CI runs this)
	python3 ops/check_locks.py

env:              ## create .env from .env.example with generated secrets (leaves an existing one alone)
	$(PY) ops/bootstrap_env.py

up: env           ## the whole stack (API + web) in Docker on the fixture warehouse: http://127.0.0.1:3000 and :8000
	$(COMPOSE) up --build --wait

monitoring-up: env ## the same plus Prometheus (alert rules) and Grafana (provisioned dashboard): :9090 and :3001
	$(COMPOSE) --profile monitoring up --build --wait

up-llm-local: env ## the stack plus a local model (Ollama in Docker, CPU unless GPU=1; LOCAL_LLM_MODEL, default gpt-oss:20b)
	$(LOCAL_IN_COMPOSE) $(COMPOSE) $(GPU_FILE) --profile llm-local up --build --wait api web ollama
	$(LOCAL_IN_COMPOSE) $(COMPOSE) $(GPU_FILE) --profile llm-local up -d ollama-pull
	@echo "the model downloads in the background: docker compose -f ops/docker-compose.yml --profile llm-local logs -f ollama-pull"

up-llm-host: env  ## the stack using an Ollama already running on this machine (macOS: Metal speed): ollama serve, then this
	$(LOCAL_ON_HOST) $(COMPOSE) up --build --wait

up-dataset: env   ## the stack on your local CSVs (RAW_DIR=/path/to/data/raw), read-only, no S3; first boot ingests them
	@test -n "$(RAW_DIR)" || { echo "usage: make up-dataset RAW_DIR=/path/to/data/raw   (INGEST_ARGS to change what is ingested)"; exit 1; }
	RAW_DIR="$(RAW_DIR)" INGEST_ARGS="$${INGEST_ARGS:---profile serving --source local --raw-dir /app/data/raw --sample-customers 5000 --since 2025-06-17}" \
	  $(COMPOSE) up --build --wait --wait-timeout 1800

down:             ## stop the stack and drop its volumes (the fixture warehouse is rebuilt on the next up)
	$(COMPOSE) --profile monitoring --profile llm-local down -v

PROMTOOL = docker run --rm --entrypoint promtool -v "$(CURDIR)/ops:/ops:ro" prom/prometheus:v3.5.0

alerts-check:     ## promtool: syntax of ops/alerts.yml and its unit tests (needs Docker)
	$(PROMTOOL) check rules /ops/alerts.yml
	$(PROMTOOL) test rules /ops/alerts_test.yml

compose-e2e:      ## the stack from scratch on the fixture, checked end to end (what the CI's compose job runs; needs Docker)
	sh ops/compose_e2e.sh

ingest:           ## full warehouse (serving + analysis tables) from S3, with contracts + lineage
	$(PY) -m data.pipeline --profile all --report data/reports/quality_report.json

ingest-demo:      ## small deterministic sample for demo deploys (5k customers, last 12 months)
	$(PY) -m data.pipeline --profile serving --sample-customers 5000 --since 2025-06-17 --report data/reports/quality_report_demo.json

analysis:         ## problem evidence + human baseline -> docs/evidence/baseline_metrics.md
	$(PY) -m analysis.baseline_contact_center

train-eval:       ## train/select the intent model on dev, score on held-out test -> eval/reports/intent_classifier.md
	$(PY) -m eval.test_cases.build_intent_dataset
	$(PY) -m eval.evaluate_intent_classifier

workload:         ## regenerate the dev/test system workloads (oracle labels from the warehouse)
	$(PY) -m eval.workload

eval:             ## baseline vs proposed on the test workload (offline, scripted ideal model)
	$(PY) -m eval.run_system_eval --split test

eval-adversarial: ## same workload with a deliberately bad model: safety must not depend on the model
	$(PY) -m eval.run_system_eval --split test --system proposed --llm adversarial

EVAL_MODELS ?= anthropic:claude-sonnet-5,anthropic:claude-haiku-4-5,groq:openai/gpt-oss-120b

eval-live:        ## live models compared on one 132-case sample (3 per case type and language), 3 repeats each (a model without its API key is skipped)
	$(PY) -m eval.run_system_eval --split test --system proposed --llm live --repeats 3 --limit 132 --models $(EVAL_MODELS)

gate:            ## compuerta de calidad: pisos de seguridad y evidencia vigente (la corre el CI)
	$(PY) -m eval.gate

operator-labels: ## las decisiones del operador como etiquetas + barrido del umbral de antigüedad
	$(PY) -m eval.operator_labels

live-smoke:       ## live model on the fixture warehouse: every required path, ES/PT, per-turn cost and latency
	$(PY) -m ops.live_smoke --out eval/reports/LIVE_SMOKE.md

test:             ## hermetic test suite (fixture warehouse; no S3, no API keys)
	$(PY) -m pytest tests/ -q

mlflow-ui:        ## browse every tracked classifier selection and evaluation run: http://127.0.0.1:5000
	$(PY) -m mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db

serve:
	$(PY) -m uvicorn api.main:app --host "$(API_HOST)" --port "$(API_PORT)"

docker-build:
	docker build -f ops/Dockerfile -t latam-bank-agent .

all: ingest analysis train-eval workload eval eval-adversarial test

retention:        ## apply the retention policy to every record store (docs/operations.md, "Data retention")
	$(PY) -m ops.retention

loadtest:         ## throughput of the non-LLM layers on the real warehouse
	$(PY) -m ops.loadtest --threads 8 --turns 400
