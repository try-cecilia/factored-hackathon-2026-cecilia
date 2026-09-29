#!/bin/sh
# The local stack from scratch on the fixture warehouse, checked end to end: `make compose-e2e` (and the CI job "compose").
# It builds both images, starts API + web + Prometheus, waits for them to be healthy, then checks:
#   the API's probes and the smoke test (ops/container_smoke.py), the web's page and its path to the API, the security headers,
#   the access checks that matter most, /metrics with and without credentials, that Prometheus scrapes the API and has
#   loaded every alert rule, and that Grafana is provisioned with a dashboard whose queries Prometheus accepts.
# The stack and its volumes are removed at the end, pass or fail. The llm-local profile (a model server) is not started here.
set -eu
cd "$(dirname "$0")/.."

python3 ops/bootstrap_env.py
val() { grep "^$1=" .env | head -1 | cut -d= -f2-; }
API_PORT="$(val API_PORT)"; API_PORT="${API_PORT:-8000}"
WEB_PORT="$(val WEB_PORT)"; WEB_PORT="${WEB_PORT:-3000}"
PROM_PORT="$(val PROMETHEUS_PORT)"; PROM_PORT="${PROM_PORT:-9090}"
GRAFANA_PORT="$(val GRAFANA_PORT)"; GRAFANA_PORT="${GRAFANA_PORT:-3001}"
GRAFANA_PASSWORD="$(val GRAFANA_ADMIN_PASSWORD)"
ADMIN="$(val ADMIN_API_KEY)"; METRICS="$(val METRICS_TOKEN)"
API="http://127.0.0.1:$API_PORT"; WEB="http://127.0.0.1:$WEB_PORT"
COMPOSE="docker compose -f ops/docker-compose.yml --env-file .env --profile monitoring"

ok() { echo "ok   $*"; }
fail() { echo "FAIL $*" >&2; $COMPOSE logs --no-color --tail 60 >&2 || true; exit 1; }
cleanup() { $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

started=$(date +%s)
$COMPOSE up --build --wait --wait-timeout 900
echo "stack healthy after $(( $(date +%s) - started )) s (build included)"

# --- API ---
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/livez")" = 200 ] || fail "/livez"
curl -fs "$API/readyz" | grep -q '"status":"ready"' || fail "/readyz is not ready"
ok "API live and ready"
curl -fs "$API/health" | grep -q '"data_as_of":"2024-01-16"' || fail "/health does not report the fixture's as-of date"
python3 ops/container_smoke.py "$API" || fail "smoke test"
headers() { curl -s -D - -o /dev/null "$1" | tr -d '\r'; }  # a GET, headers only: the page has no HEAD route
headers "$API/livez" | grep -qi '^x-content-type-options: nosniff' || fail "security headers missing"
headers "$API/" | grep -qi "^content-security-policy: .*script-src 'sha256-" || fail "the page has no script-hash CSP"
ok "security headers"

# --- web ---
[ "$(curl -s -o /dev/null -w '%{http_code}' "$WEB/")" = 200 ] || fail "the web does not answer /"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$WEB/login")" = 200 ] || fail "the web does not answer /login"
health="$(curl -fs "$WEB/api/agent/health")" || fail "the web's /api/agent/health did not reach the API"
echo "$health" | grep -q '"status":"ok"' && echo "$health" | grep -q '"data_as_of":"2024-01-16"' || fail "web health: $health"
ok "web serves its pages and reaches the API"

# --- access ---
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/admin/ops")" = 401 ] || fail "/admin/ops is open"
[ "$(curl -s -o /dev/null -w '%{http_code}' -H "X-Admin-Key: $ADMIN" "$API/admin/ops")" = 200 ] || fail "/admin/ops refuses the admin key"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/openapi.json")" = 404 ] || fail "the API schema is published"
ok "admin closed without its key, schema not published"

# --- metrics ---
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/metrics")" = 401 ] || fail "/metrics is open"
[ "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $METRICS" "$API/admin/ops")" = 401 ] || fail "the metrics token opens /admin"
scrape="$(curl -fs -H "Authorization: Bearer $METRICS" "$API/metrics")" || fail "/metrics with the token"
for m in cecilai_turns_total cecilai_escalations_total cecilai_turn_latency_seconds cecilai_stage_latency_seconds \
         cecilai_http_requests_total cecilai_llm_attempts_total cecilai_llm_budget_exhausted cecilai_llm_circuit_open \
         cecilai_rate_limit_hits_total cecilai_data_age_hours cecilai_data_freshness_slo_hours cecilai_retention_last_run_timestamp_seconds; do
  echo "$scrape" | grep -q "^# TYPE $m " || fail "/metrics lacks $m"
done
# and the smoke test's own turns are in them: two escalations (fraud, suspended account) and one expired session
echo "$scrape" | awk '/^cecilai_turns_total\{.*disposition="ESCALATE"/ {n += $NF} END {exit n >= 2 ? 0 : 1}' || fail "the smoke test's escalations are not counted"
# the container's retention loop ran at boot: its status file is what this gauge reads
echo "$scrape" | grep -Eq '^cecilai_retention_last_run_timestamp_seconds [1-9]' || fail "the retention loop has not run"
curl -fs -H "X-Admin-Key: $ADMIN" "$API/admin/audit_log?limit=500" | grep -Eq '"event": ?"retention_purge"' || fail "the purge left no audit record"
ok "/metrics answers to its token only and exposes the expected series; retention ran and audited itself"

# --- Prometheus ---
i=0
until curl -fs "http://127.0.0.1:$PROM_PORT/api/v1/targets" | grep -q '"health":"up"'; do
  i=$((i + 1)); [ "$i" -le 30 ] || fail "Prometheus does not see the API target up"; sleep 2
done
rules="$(curl -fs "http://127.0.0.1:$PROM_PORT/api/v1/rules")"
[ "$(echo "$rules" | grep -o '"type":"alerting"' | wc -l | tr -d ' ')" -ge 20 ] || fail "Prometheus did not load the alert rules"
echo "$rules" | grep -q '"health":"err"' && fail "a rule fails to evaluate"
ok "Prometheus scrapes the API and evaluates the alert rules"

# --- Grafana ---
G="http://127.0.0.1:$GRAFANA_PORT"
i=0
until curl -fs "$G/api/health" | grep -q '"database": *"ok"'; do
  i=$((i + 1)); [ "$i" -le 30 ] || fail "Grafana does not come up"; sleep 2
done
[ "$(curl -s -o /dev/null -w '%{http_code}' "$G/api/search")" = 401 ] || fail "Grafana answers without a login"
curl -fs -u "admin:$GRAFANA_PASSWORD" "$G/api/search?query=cecilai" | grep -q '"uid":"cecilai-overview"' || fail "the dashboard was not provisioned"
curl -fs -u "admin:$GRAFANA_PASSWORD" "$G/api/datasources/uid/prometheus/health" | grep -q '"status":"OK"' || fail "Grafana cannot reach Prometheus"
# every panel's query is valid PromQL that Prometheus accepts (an empty result is fine: the stack has had no traffic for long)
python3 - "http://127.0.0.1:$PROM_PORT" <<'PY' || fail "a dashboard query is rejected by Prometheus"
import json, sys, urllib.parse, urllib.request
base = sys.argv[1]
dashboard = json.load(open("ops/grafana/dashboards/cecilai.json"))
queries = [t["expr"] for p in dashboard["panels"] for t in p["targets"]]
for q in queries:
    url = f"{base}/api/v1/query?" + urllib.parse.urlencode({"query": q})
    with urllib.request.urlopen(url, timeout=20) as r:
        assert json.load(r)["status"] == "success", q
print(f"{len(queries)} dashboard queries accepted")
PY
ok "Grafana is provisioned with the dashboard and its Prometheus, and login is required"
echo "compose end-to-end passed in $(( $(date +%s) - started )) s"
