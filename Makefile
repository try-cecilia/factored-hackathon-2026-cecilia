# Reproducible entry points. Every number in the docs comes from one of these.
PY ?= python3
PNPM ?= pnpm
API_HOST ?= 0.0.0.0
API_PORT ?= 8000
WEB_HOST ?= 127.0.0.1
WEB_PORT ?= 3000
# Combined development always connects to its local API, unless overridden.
AGENT_API_URL ?= http://127.0.0.1:$(API_PORT)

.PHONY: gate operator-labels retention loadtest setup ingest ingest-demo analysis train-eval workload eval eval-adversarial eval-failures eval-failures-live eval-failures-local eval-live live-smoke test serve docker-build all mlflow-ui
.PHONY: web-setup serve-web web-build web-typecheck serve-all

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

setup:            ## install pinned dependencies, with experiment tracking (the serving image takes requirements.txt only)
	$(PY) -m pip install -r requirements-tracking.txt

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

eval-failures:    ## calidad y fallos por categoría e idioma: set reservado en el warehouse de prueba (sin S3 ni claves) + filas del workload de test
	$(PY) -m eval.heldout
	$(PY) -m eval.failure_eval

HELDOUT_DB ?= data/warehouse/heldout_fixture.duckdb

eval-failures-live: ## el set reservado con modelos en vivo, sobre el warehouse de prueba (un modelo sin su clave se omite)
	$(PY) -m eval.heldout --build-warehouse $(HELDOUT_DB)
	DUCKDB_PATH=$(HELDOUT_DB) $(PY) -m eval.run_system_eval --cases eval/heldout/cases_failures.jsonl --system proposed --llm live --repeats 3 --models $(EVAL_MODELS)
	DUCKDB_PATH=$(HELDOUT_DB) $(PY) -m eval.run_system_eval --cases eval/heldout/cases_failures_2.jsonl --system proposed --llm live --repeats 3 --models $(EVAL_MODELS)

eval-failures-local: ## el set reservado con un modelo local (Ollama; ver docker compose --profile llm-local), sin cuentas ni claves
	$(MAKE) eval-failures-live EVAL_MODELS=local:$${LOCAL_LLM_MODEL:-gpt-oss:20b}

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

retention:        ## prune traces/audit (30d) and local tickets (90d)
	$(PY) -m ops.retention

loadtest:         ## throughput of the non-LLM layers on the real warehouse
	$(PY) -m ops.loadtest --threads 8 --turns 400
