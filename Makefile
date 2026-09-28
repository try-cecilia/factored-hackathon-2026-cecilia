# Reproducible entry points. Every number in the docs comes from one of these.
PY ?= python3

.PHONY: retention loadtest setup ingest ingest-demo analysis train-eval workload eval eval-adversarial eval-live live-smoke test serve docker-build all

setup:            ## install pinned dependencies
	$(PY) -m pip install -r requirements.txt

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

eval-live:        ## live models compared on one 120-case sample, 3 repeats each (a model without its API key is skipped)
	$(PY) -m eval.run_system_eval --split test --system proposed --llm live --repeats 3 --limit 120 --models $(EVAL_MODELS)

live-smoke:       ## live model on the fixture warehouse: every required path, ES/PT, per-turn cost and latency
	$(PY) -m ops.live_smoke --out eval/reports/LIVE_SMOKE.md

test:             ## hermetic test suite (fixture warehouse; no S3, no API keys)
	$(PY) -m pytest tests/ -q

serve:
	uvicorn api.main:app --host 0.0.0.0 --port 8000

docker-build:
	docker build -f ops/Dockerfile -t latam-bank-agent .

all: ingest analysis train-eval workload eval eval-adversarial test

retention:        ## prune traces/audit (30d) and local tickets (90d)
	$(PY) -m ops.retention

loadtest:         ## throughput of the non-LLM layers on the real warehouse
	$(PY) -m ops.loadtest --threads 8 --turns 400
