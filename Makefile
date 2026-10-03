# Reproducible entry points. Every number in the docs comes from one of these.
PY ?= python3
PNPM ?= pnpm
API_HOST ?= 0.0.0.0
API_PORT ?= 8000
WEB_HOST ?= 127.0.0.1
WEB_PORT ?= 3000
# Combined development always connects to its local API, unless overridden.
AGENT_API_URL ?= http://127.0.0.1:$(API_PORT)

# The raw source files: `ingest-local` loads from here and `lineage` re-hashes them from here, so both always read the same folder.
RAW_DATA_DIR ?= data/raw
QUALITY_REPORT ?= data/reports/quality_report.json

.PHONY: gate label-scan real-speech tracking-report model-study model-card unit-economics validate-data-ml lineage gold pipeline ingest-local lake operator-labels retention test-resilience loadtest loadtest-fixture loadtest-http setup ingest ingest-demo analysis label-signal train-eval workload eval eval-adversarial eval-ablation check-readme sync-eval-latencies evidence-table eval-failures eval-failures-live eval-live-sample eval-live-sample-report eval-failures-local eval-live live-smoke test serve docker-build all mlflow-ui
.PHONY: web-setup serve-web web-build web-typecheck web-test serve-fixture serve-all-fixture serve-all
.PHONY: env env-check env-fill evidence up down clean-volumes monitoring-up up-llm-local up-llm-host up-dataset lock lock-check alerts-check compose-e2e
.PHONY: human-set-export human-set-sheet human-set-pages human-set-agreement human-set-cases human-set-eval human-set-report
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

web-test:         ## frontend tests (node:test): unit tests, then HTTP tests against the production build
	$(PNPM) --dir web test:all

serve-fixture:    ## API on the tests' fixture warehouse with a keyword stand-in for the model (no S3, no keys); DEMO_MODE=1
	$(PY) -m ops.serve_fixture $(API_PORT)

serve-all-fixture: ## serve-fixture and serve-web together, to try the customer app with no S3 and no model key
	AGENT_API_URL="$(AGENT_API_URL)" $(PNPM) --dir web exec concurrently --kill-others --kill-timeout 5000 --names api,web \
		"$(MAKE) -C .. serve-fixture" "$(MAKE) -C .. serve-web"

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

env-check:        ## list what .env.example has and .env lacks (names only, never values) and warn if INGEST_ARGS would read S3; never fails
	$(PY) -m ops.env_check

env-fill:         ## append to .env the settings it lacks, with generated secrets; nothing already there changes, no value is printed
	$(PY) -m ops.env_check --fill

up: env env-check ## the whole stack (API + web) in Docker on the fixture warehouse: http://127.0.0.1:3000 and :8000
	$(COMPOSE) up --build --wait

monitoring-up: env env-check ## the same plus Prometheus (alert rules) and Grafana (provisioned dashboard): :9090 and :3001
	$(COMPOSE) --profile monitoring up --build --wait

up-llm-local: env env-check ## the stack plus a local model (Ollama in Docker, CPU unless GPU=1; LOCAL_LLM_MODEL, default gpt-oss:20b)
	$(LOCAL_IN_COMPOSE) $(COMPOSE) $(GPU_FILE) --profile llm-local up --build --wait api web ollama
	$(LOCAL_IN_COMPOSE) $(COMPOSE) $(GPU_FILE) --profile llm-local up -d ollama-pull
	@echo "the model downloads in the background: docker compose -f ops/docker-compose.yml --profile llm-local logs -f ollama-pull"

up-llm-host: env env-check  ## the stack using an Ollama already running on this machine (macOS: Metal speed): ollama serve, then this
	$(LOCAL_ON_HOST) $(COMPOSE) up --build --wait

up-dataset: env env-check   ## the stack on your local CSVs (RAW_DIR=/path/to/data/raw), read-only, no S3; first boot ingests them
	@test -n "$(RAW_DIR)" || { echo "usage: make up-dataset RAW_DIR=/path/to/data/raw   (INGEST_ARGS to change what is ingested)"; exit 1; }
	@if docker volume inspect cecilai-local_warehouse >/dev/null 2>&1; then echo "note: a warehouse already exists in the volume, so nothing is ingested from RAW_DIR. To load it: make clean-volumes, then this again."; fi
	RAW_DIR="$(RAW_DIR)" INGEST_ARGS="$${INGEST_ARGS:---profile serving --source local --raw-dir /app/data/raw --sample-customers 5000 --since 2025-06-17}" \
	  $(COMPOSE) up --build --wait --wait-timeout 1800

down:             ## stop the stack; its volumes (warehouse, sessions, tickets, monitoring data, models) are kept
	$(COMPOSE) --profile monitoring --profile llm-local down

clean-volumes:    ## stop the stack AND delete its volumes: the warehouse is rebuilt on the next up. Asks first (YES=1 skips it)
	@echo "This deletes the volumes of the compose project cecilai-local (warehouse, sessions, tickets, Prometheus, Grafana, models):"
	@docker volume ls --filter label=com.docker.compose.project=cecilai-local --format '  {{.Name}}'
	@[ -n "$(YES)" ] || { printf "Type yes to continue: "; read answer; [ "$$answer" = yes ] || { echo "nothing deleted"; exit 1; }; }
	$(COMPOSE) --profile monitoring --profile llm-local down -v

PROMTOOL = docker run --rm --entrypoint promtool -v "$(CURDIR)/ops:/ops:ro" prom/prometheus:v3.5.0

alerts-check:     ## promtool: syntax of ops/alerts.yml and its unit tests (needs Docker)
	$(PROMTOOL) check rules /ops/alerts.yml
	$(PROMTOOL) test rules /ops/alerts_test.yml

compose-e2e:      ## the whole stack from scratch on the fixture in its own throwaway compose project, checked end to end (the CI job; needs Docker)
	sh ops/compose_e2e.sh

ingest:           ## full warehouse (serving + analysis tables) from S3, with contracts + lineage
	$(PY) -m data.pipeline --profile all --raw-dir $(RAW_DATA_DIR) --report $(QUALITY_REPORT)

ingest-local:     ## the same full load, from a local directory (RAW_DATA_DIR, data/raw by default) instead of S3
	$(PY) -m data.pipeline --profile all --source local --raw-dir $(RAW_DATA_DIR) --report $(QUALITY_REPORT)

pipeline:         ## the whole chain, stopping at the first step that fails: ingest -> gold -> gold VERIFY -> lineage -> lake -> lake VERIFY (INGEST=ingest-local reads a local directory)
	$(MAKE) $(or $(INGEST),ingest)
	$(MAKE) gold
	$(MAKE) gold VERIFY=1
	$(MAKE) lineage
	$(MAKE) lake
	$(MAKE) lake VERIFY=1

ingest-demo:      ## small deterministic sample for demo deploys (5k customers, last 12 months)
	$(PY) -m data.pipeline --profile serving --sample-customers 5000 --since 2025-06-17 --report data/reports/quality_report_demo.json

analysis: gold    ## problem evidence + human baseline -> docs/evidence/baseline_metrics.md (its contact figures read the gold mart, so the marts are rebuilt first)
	$(PY) -m analysis.baseline_contact_center

real-speech:      ## the intent classifier, untouched, on 1,090 real calls to an e-banking line (MInDS-14, es-ES/pt-PT) -> docs/evidence/real_speech.md
	$(PY) -m eval.real_speech

model-study:      ## sensitivity and learning curve of the intent classifier on dev only (the shipped model does not change) -> docs/evidence/model_study.md
	$(PY) -m eval.model_study

model-card:       ## the intent classifier's model card, rendered from the reports -> docs/MODEL_CARD.md
	$(PY) -m eval.model_card

unit-economics:   ## where the human time goes and what automating the slice is worth under stated scenarios -> docs/evidence/unit_economics.md
	$(PY) -m analysis.unit_economics

label-signal:     ## is there signal in the fraud labels? -> docs/evidence/label_signal.md
	$(PY) -m analysis.label_signal

label-scan:       ## which column each accounts-and-payments outcome depends on, with a permuted-label control -> docs/evidence/label_scan.md
	DUCKDB_PATH=data/warehouse/full_all.duckdb $(PY) -m analysis.label_scan

train-eval:       ## train/select the intent model on dev, score on held-out test -> eval/reports/intent_classifier.md
	$(PY) -m eval.test_cases.build_intent_dataset
	$(PY) -m eval.evaluate_intent_classifier

workload:         ## regenerate the dev/test system workloads (oracle labels from the warehouse)
	$(PY) -m eval.workload

eval:             ## baseline vs proposed on the test workload (offline, scripted ideal model)
	$(PY) -m eval.run_system_eval --split test

eval-adversarial: ## same workload with a deliberately bad model: safety must not depend on the model
	$(PY) -m eval.run_system_eval --split test --system proposed --llm adversarial

eval-ablation:    ## what each group of safety controls buys: the same models with the groups taken off, cumulatively -> eval/reports/ABLATION.md
	$(PY) -m eval.ablation

check-readme:    ## the README's headline figures, the latencies EVALUATION.md and the slides cite, and the landing's machine-dependent figures, against the generated reports (fails on a mismatch)
	$(PY) -m eval.check_readme

sync-eval-latencies: ## copy the regenerated reports' latencies per case into EVALUATION.md, the slides and the landing's figures.ts (only those cells and values, plus the landing's offline day), then check
	$(PY) -m eval.check_readme --write-latencies

evidence-table:   ## docs/EVIDENCE.md: rewrite its evidence table from the reports and its code links' line numbers (the test fails until it is run)
	$(PY) -m eval.evidence_table --write

eval-failures:    ## calidad y fallos por categoría e idioma: set reservado en el warehouse de prueba (sin S3 ni claves) + filas del workload de test
	$(PY) -m eval.heldout
	$(PY) -m eval.failure_eval

HELDOUT_DB ?= data/warehouse/heldout_fixture.duckdb

eval-failures-live: ## el set reservado con modelos en vivo, sobre el warehouse de prueba (un modelo sin su clave se omite)
	$(PY) -m eval.heldout --build-warehouse $(HELDOUT_DB)
	DUCKDB_PATH=$(HELDOUT_DB) $(PY) -m eval.run_system_eval --cases eval/heldout/cases_failures.jsonl --system proposed --llm live --repeats 3 --models $(EVAL_MODELS)
	DUCKDB_PATH=$(HELDOUT_DB) $(PY) -m eval.run_system_eval --cases eval/heldout/cases_failures_2.jsonl --system proposed --llm live --repeats 3 --models $(EVAL_MODELS)
	DUCKDB_PATH=$(HELDOUT_DB) $(PY) -m eval.run_system_eval --cases eval/heldout/cases_failures_3.jsonl --system proposed --llm live --repeats 3 --models $(EVAL_MODELS)

eval-live-sample: ## la muestra chica con Groq (ids en eval/reports/live_sample_selection.json; necesita GROQ_API_KEY; ritmo de 20 s por caso)
	run=$${RUN_ID:-$$(date -u +%Y%m%dT%H%M%SZ)}; \
	$(PY) -m eval.live_sample run --part reserved --run-id $$run && \
	$(PY) -m eval.live_sample run --part generated --run-id $$run

eval-live-sample-report: ## rearma las tablas de una corrida de la muestra desde sus filas por caso (eval/reports/live_sample_groq_rows.jsonl; RUN_ID=... para elegirla, por defecto la última)
	$(PY) -m eval.live_sample report $(if $(RUN_ID),--run-id $(RUN_ID))

eval-failures-local: ## el set reservado con un modelo local (Ollama; ver docker compose --profile llm-local), sin cuentas ni claves
	$(MAKE) eval-failures-live EVAL_MODELS=local:$${LOCAL_LLM_MODEL:-gpt-oss:20b}

EVAL_MODELS ?= anthropic:claude-sonnet-5,anthropic:claude-haiku-4-5,groq:openai/gpt-oss-120b

eval-live:        ## live models compared on one 138-case sample (3 per case type and language), 3 repeats each (a model without its API key is skipped)
	$(PY) -m eval.run_system_eval --split test --system proposed --llm live --repeats 3 --limit 138 --models $(EVAL_MODELS)

# The human-written set, in order (docs/human_set.md). Its files live in eval/workload/, which the public export removes.
HUMAN_SET_MODEL ?= anthropic:claude-sonnet-5

human-set-export: ## the form's answers -> eval/workload/human_raw.jsonl (needs the Cloudflare token file, CLOUDFLARE_SECRETS)
	$(PY) -m eval.human_set.cloud export

human-set-sheet:  ## the labeling sheet: the messages of people who never saw the system, shuffled, no system output -> eval/workload/human_labeling_sheet.csv
	$(PY) -m eval.human_set.classifier_eval sheet

human-set-pages:  ## one labeling page per person: make human-set-pages LABELERS="ana beto" (DISAGREEMENTS=1: the third person's page, only the disagreements)
	@test -n "$(LABELERS)" || { echo 'usage: make human-set-pages LABELERS="name1 name2" [DISAGREEMENTS=1]'; exit 1; }
	$(PY) -m eval.human_set.classifier_eval page $(foreach l,$(LABELERS),--labeler $(l)) $(if $(DISAGREEMENTS),--only-disagreements)

human-set-agreement: ## kappa of the two labelers before settling, and the final labels: make human-set-agreement A=a.csv B=b.csv [THIRD=c.csv]
	@test -n "$(A)" && test -n "$(B)" || { echo "usage: make human-set-agreement A=labels_a.csv B=labels_b.csv [THIRD=labels_c.csv]"; exit 1; }
	$(PY) -m eval.human_set.classifier_eval agreement $(A) $(B) $(if $(THIRD),--third $(THIRD))

human-set-cases:  ## the labeled messages as workload cases, customers from the full warehouse -> eval/workload/human_cases.jsonl
	$(PY) -m eval.human_set.cases

human-set-eval:   ## LIVE, spends model credit (about USD 1 to 2): the keyword bot once and the live model (HUMAN_SET_MODEL, Sonnet 5) 3 times on the human cases; stops without its API key
	$(PY) -m eval.run_system_eval --cases eval/workload/human_cases.jsonl --system both --llm live --repeats 3 --models $(HUMAN_SET_MODEL)

human-set-report: ## the pre-registered gates G0 to G4 and the report of the human set -> eval/reports/HUMAN_SET.md (no model calls)
	$(PY) -m eval.human_set.report

gate:            ## compuerta de calidad: pisos de seguridad y evidencia vigente, más la validación de datos y ML; no deja archivos modificados (la corre el CI)
	$(PY) -m eval.gate
	$(MAKE) validate-data-ml

validate-data-ml: ## contratos, calidad, linaje, frescura, clasificador vs línea base y fuga: PASS/FAIL por criterio; no escribe nada (avisa si la evidencia versionada quedó vieja)
	$(PY) -m eval.validate_data_ml

evidence:         ## regenera la evidencia versionada: docs/evidence/data_ml_validation.{md,json} con la fecha y el commit de hoy (paso explícito; validate-data-ml y gate no escriben)
	$(PY) -m eval.validate_data_ml --out-dir docs/evidence

gold:             ## gold marts built from silver and reconciled to it (rolls back on a mismatch); `make gold VERIFY=1` only re-checks
	$(PY) -m data.gold $(if $(VERIFY),--verify)

lake:             ## silver and gold as Parquet files with a manifest of hashes -> data/lake; `make lake VERIFY=1` re-hashes and re-reads them
	$(PY) -m data.lake $(if $(VERIFY),--verify --with-db)

lineage:          ## the served warehouse traced back to its source files and their hashes (exit 1 if the chain is broken)
	$(PY) -m data.lineage --verify --raw-dir $(RAW_DATA_DIR)

operator-labels: ## las decisiones del operador como etiquetas + barrido del umbral de antigüedad
	$(PY) -m eval.operator_labels

live-smoke:       ## live model on the fixture warehouse: every required path, ES/PT, per-turn cost and latency
	$(PY) -m ops.live_smoke --out eval/reports/LIVE_SMOKE.md

test:             ## hermetic test suite (fixture warehouse; no S3, no API keys)
	$(PY) -m pytest tests/ -q

test-resilience:  ## hermetic: traces, bounded retries, safe fallback and capacity limits (no S3, no API keys)
	$(PY) -m pytest tests/test_tracing.py tests/test_retry.py tests/test_resilience.py tests/test_capacity.py tests/test_local_llm.py tests/test_turn_deadline.py tests/test_record_failures.py tests/test_llm_error_privacy.py tests/test_call_cancellation.py tests/test_handoff_budget.py tests/test_handoff_lock.py tests/test_late_handoff.py tests/test_bounded_ops.py tests/test_call_pool_limit.py tests/test_loadtest.py -q

tracking-report:  ## a versioned snapshot of the MLflow runs, each checked against its committed report -> docs/evidence/ml_tracking.md
	$(PY) -m eval.tracking_report

mlflow-ui:        ## browse every tracked classifier selection and evaluation run: http://127.0.0.1:5000
	$(PY) -m mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db

SERVER_TIMEOUTS ?= --timeout-keep-alive 5 --timeout-graceful-shutdown 20

serve:
	$(PY) -m uvicorn api.main:app --host "$(API_HOST)" --port "$(API_PORT)" $(SERVER_TIMEOUTS)

docker-build:
	docker build -f ops/Dockerfile -t latam-bank-agent .

all: ingest analysis train-eval workload eval eval-adversarial sync-eval-latencies test

retention:        ## apply the retention policy to every record store (docs/operations.md, "Data retention")
	$(PY) -m ops.retention

loadtest:         ## throughput of the non-LLM layers on the real warehouse
	$(PY) -m ops.loadtest --threads 8 --turns 400

loadtest-fixture: ## the same throughput test on the hand-made fixture warehouse (no S3, no keys)
	$(PY) -m ops.loadtest --fixture --threads 8 --turns 400

loadtest-http:    ## the HTTP surface under overload on the fixture warehouse: simulated model latency, 429/503 and Retry-After
	$(PY) -m ops.loadtest --http --out eval/reports/LOADTEST_HTTP.md
	$(PY) -m ops.loadtest --http --ignore-retry-after --levels 128 256 --out eval/reports/LOADTEST_HTTP_NO_BACKOFF.md
