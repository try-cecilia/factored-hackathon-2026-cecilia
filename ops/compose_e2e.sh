#!/bin/sh
# The local stack from scratch on the fixture warehouse, checked end to end: `make compose-e2e` (and the CI job "compose").
# It builds both images, starts API + web + Prometheus + Grafana, waits for them to be healthy, then checks:
#   the API's probes and the smoke test (ops/container_smoke.py), the web's page and its path to the API, through the web (the
#   BFF, in production mode, as a browser would use it): a customer's login and a chat turn, an operator's login on the plain form
#   with the origin the compose configures (and a post without it refused) and the queue behind it, and /dev/ui closed; the
#   security headers, the access checks that matter most, /metrics with and without credentials, that Prometheus scrapes the API and has
#   loaded every alert rule, and that Grafana is provisioned with a dashboard whose queries Prometheus accepts.
# The llm-local profile (a model server) is not started here.
#
# It is isolated from the stack a person runs with `make up`: its own random compose project (cecilai-e2e-<random>, never
# cecilai-local), its own temporary settings file with fresh secrets, the fixture warehouse and ports nothing is using. Its
# cleanup removes that project's containers, volumes and images and nothing else, and refuses any other project name.
# COMPOSE_E2E_DRY_RUN=1 prints that isolation and starts nothing (tests/test_compose_isolation.py).
set -eu
cd "$(dirname "$0")/.."

PROJECT="cecilai-e2e-$(python3 -c 'import secrets, string; print("".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8)))')"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/cecilai-e2e.XXXXXX")"
ENVFILE="$WORK/env"
python3 ops/bootstrap_env.py --out "$ENVFILE" --free-ports >/dev/null

# Settings the checks below look for in the running container: a value written in the settings file must take effect there
for override in SECURITY_HSTS=1 FRESHNESS_SLO_HOURS=12 RETENTION_TRACES_DAYS=7 RETENTION_TICKETS_DAYS=45; do
  sed "s|^${override%%=*}=.*|$override|" "$ENVFILE" > "$ENVFILE.tmp" && mv "$ENVFILE.tmp" "$ENVFILE"
  grep -q "^$override\$" "$ENVFILE" || { echo "the settings file has no ${override%%=*} to override" >&2; exit 1; }
done
val() { grep "^$1=" "$ENVFILE" | head -1 | cut -d= -f2-; }
# Names below start with E2E_ so the unset of the settings file's own names (further down) cannot remove them
E2E_API_PORT="$(val API_PORT)"; E2E_PROM_PORT="$(val PROMETHEUS_PORT)"; E2E_GRAFANA_PORT="$(val GRAFANA_PORT)"
E2E_ADMIN="$(val ADMIN_API_KEY)"; E2E_METRICS="$(val METRICS_TOKEN)"; E2E_GRAFANA_PASSWORD="$(val GRAFANA_ADMIN_PASSWORD)"
E2E_WEB_PORT="$(val WEB_PORT)"; E2E_OPERATOR="$(val OPERATOR_KEYS | cut -d= -f2-)"
API="http://127.0.0.1:$E2E_API_PORT"; WEB="http://127.0.0.1:$E2E_WEB_PORT"
COMPOSE="docker compose -p $PROJECT -f ops/docker-compose.yml --env-file $ENVFILE --profile monitoring"

cleanup() {
  status=$?  # the script's own exit status, which the cleanup must not replace
  case "$PROJECT" in cecilai-e2e-*) ;; *) echo "refusing to clean up project $PROJECT: not an e2e project" >&2; exit 1 ;; esac
  if [ -z "${COMPOSE_E2E_DRY_RUN:-}" ]; then $COMPOSE down -v --remove-orphans --rmi local >/dev/null 2>&1 || true; fi
  rm -rf "$WORK"
  exit "$status"
}
trap cleanup EXIT

if [ -n "${COMPOSE_E2E_DRY_RUN:-}" ]; then
  echo "project=$PROJECT"
  echo "env_file=$ENVFILE"
  echo "ports=$E2E_API_PORT,$E2E_WEB_PORT,$E2E_PROM_PORT,$E2E_GRAFANA_PORT"
  exit 0
fi

# Nothing from the caller's shell may override the settings file (compose gives the environment priority over --env-file)
for name in $(grep -E '^[A-Z][A-Z0-9_]*=' "$ENVFILE" | cut -d= -f1) RAW_DIR LLM_PROVIDERS LOCAL_LLM_BASE_URL LOCAL_LLM_MODEL; do unset "$name" || true; done

ok() { echo "ok   $*"; }
fail() { echo "FAIL $*" >&2; $COMPOSE logs --no-color --tail 60 >&2 || true; exit 1; }

started=$(date +%s)
$COMPOSE up --build --wait --wait-timeout 900
echo "stack $PROJECT healthy after $(( $(date +%s) - started )) s (build included)"

# --- API ---
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/livez")" = 200 ] || fail "/livez"
curl -fs "$API/readyz" | grep -q '"status":"ready"' || fail "/readyz is not ready"
ok "API live and ready"
curl -fs "$API/health" | grep -q '"data_as_of":"2024-01-16"' || fail "/health does not report the fixture's as-of date"
python3 ops/container_smoke.py "$API" || fail "smoke test"
headers() { curl -s -D - -o /dev/null "$1" | tr -d '\r'; }  # a GET, headers only: the page has no HEAD route
headers "$API/livez" | grep -qi '^x-content-type-options: nosniff' || fail "security headers missing"
headers "$API/" | grep -qi "^content-security-policy: .*script-src 'sha256-" || fail "the page has no script-hash CSP"
headers "$API/livez" | grep -qi '^strict-transport-security: max-age=' || fail "SECURITY_HSTS=1 did not reach the container"
ok "security headers, and SECURITY_HSTS from the settings file"

# --- web ---
[ "$(curl -s -o /dev/null -w '%{http_code}' "$WEB/")" = 200 ] || fail "the web does not answer /"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$WEB/login")" = 200 ] || fail "the web does not answer /login"
health="$(curl -fs "$WEB/api/agent/health")" || fail "the web's /api/agent/health did not reach the API"
echo "$health" | grep -q '"status":"ok"' && echo "$health" | grep -q '"data_as_of":"2024-01-16"' || fail "web health: $health"
ok "web serves its pages and reaches the API"

# --- web, as a browser uses it: customer login + chat, operator login + queue, /dev/ui closed ---
# The server functions' ids are hashes of the build: read them from the running image, where the build is.
rpc_id() { $COMPOSE exec -T web sh -c "grep -rhoE 'var $1 = createServerFn.{0,200}createSsrRpc\\(\"[0-9a-f]{64}\"\\)' dist/server" | grep -oE '[0-9a-f]{64}' | head -1; }
E2E_LOGIN_FN="$(rpc_id login)"; E2E_SEND_FN="$(rpc_id sendMessage)"
[ -n "$E2E_LOGIN_FN" ] && [ -n "$E2E_SEND_FN" ] || fail "could not find the login and chat server functions in the web build"
E2E_CUSTOMER="$(curl -fs "$API/demo/customers" | python3 -c 'import json, sys; c = json.load(sys.stdin)[0]; print(c["customer_id"] + ":" + c["test_pin"])')" || fail "the API lists no demo customer"
python3 - "$WEB" "$E2E_LOGIN_FN" "$E2E_SEND_FN" "$E2E_CUSTOMER" "$E2E_ADMIN" "$E2E_OPERATOR" <<'PY' || fail "the web's login, chat or operator console (see above)"
import json, re, sys, urllib.error, urllib.parse, urllib.request

web, login_fn, send_fn, customer, admin_key, operator_key = sys.argv[1:7]
customer_id, pin = customer.split(":")


class Stay(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # a login answers with a redirect and a cookie: look at it, do not follow it
        return None


opener = urllib.request.build_opener(Stay)


def call(method, path, body=None, headers=None):
    request = urllib.request.Request(web + path, data=body, headers=headers or {}, method=method)
    try:
        response = opener.open(request, timeout=60)
    except urllib.error.HTTPError as error:
        response = error
    return response.status, response.headers, response.read().decode()


def cookie_of(headers, name):
    """`name=value` of the cookie a response sets, or None."""
    for line in headers.get_all("Set-Cookie") or []:
        if line.startswith(name + "=") and "Max-Age=0" not in line:
            return line.split(";")[0], line
    return None, None


def check(condition, what):
    print(("ok   " if condition else "FAIL ") + what)
    if not condition:
        raise SystemExit(1)


def serverfn(fn, cookie=None, **data):
    """A call to a server function as the browser makes it: seroval JSON, same-origin (the framework's CSRF check)."""
    obj = lambda i, fields: {"t": 10, "i": i, "p": {"k": list(fields), "v": [{"t": 1, "s": v} for v in fields.values()]}, "o": 0}
    payload = {"t": {"t": 10, "i": 0, "p": {"k": ["data", "context"], "v": [obj(1, data), obj(2, {})]}, "o": 0}, "f": 127, "m": []}
    headers = {"Content-Type": "application/json", "x-tsr-serverFn": "true", "Sec-Fetch-Site": "same-origin"}
    if cookie:
        headers["Cookie"] = cookie
    return call("POST", "/_serverFn/" + fn, json.dumps(payload).encode(), headers)


# customer: a wrong PIN is refused (401), the right one starts a session held in an httpOnly cookie, and a turn goes through
status, headers, body = serverfn(login_fn, customer_id=customer_id, pin="000000" if pin != "000000" else "111111")
check(status == 200 and '"k":["ok","status"],"v":[{"t":2,"s":3},{"t":0,"s":401}]' in body, "web login: a wrong PIN is refused with 401")
check(cookie_of(headers, "__Host-cecilai_session")[0] is None, "web login: a refused login sets no session")
status, headers, body = serverfn(login_fn, customer_id=customer_id, pin=pin)
session, line = cookie_of(headers, "__Host-cecilai_session")
check(status == 200 and '"k":["ok"],"v":[{"t":2,"s":2}]' in body and session, "web login: the customer's login starts a session")
check(all(a in line for a in ("HttpOnly", "Secure", "SameSite=Lax", "Path=/")), "web login: the session cookie is __Host-, httpOnly, Secure and SameSite=Lax")
status, _, body = serverfn(send_fn, cookie=session, message="cual es mi saldo", key="e2e-key-0001")
check(status == 200 and '"k":["ok","reply"],"v":[{"t":2,"s":2}' in body and '"s":"AUTO_RESOLVE"' in body, "web chat: a turn through the BFF answers, resolved from verified data")
status, _, body = serverfn(send_fn, message="cual es mi saldo", key="e2e-key-0002")
check(status == 200 and '"s":"session_expired"' in body and '"reply"' not in body, "web chat: without the session cookie there is no turn (session_expired)")

# operator: the plain form, from this origin (what the compose configures as WEB_PUBLIC_ORIGIN), and the queue behind it
origin = web
form = urllib.parse.urlencode({"admin_key": admin_key, "operator_key": operator_key}).encode()
same = {"Content-Type": "application/x-www-form-urlencoded", "Origin": origin, "Referer": origin + "/operador/login"}
for name, headers in (("with no Origin or Referer", {"Content-Type": same["Content-Type"]}),
                      ("from another origin", {**same, "Origin": "https://attacker.invalid", "Referer": "https://attacker.invalid/x"})):
    status, response, _ = call("POST", "/operador/sesion", form, headers)
    check(status == 403 and cookie_of(response, "__Host-cecilai_operator")[0] is None, f"operator login {name}: refused with 403, no session")
status, response, _ = call("POST", "/operador/sesion", form, same)
cookie, line = cookie_of(response, "__Host-cecilai_operator")
check(status == 303 and response["Location"] == "/operador/cola" and cookie, "operator login from this origin: 303 to the queue with a session")
check(all(a in line for a in ("HttpOnly", "Secure", "SameSite=Strict")), "operator session cookie: __Host-, httpOnly, Secure and SameSite=Strict")
check(call("GET", "/operador/cola")[0] == 307, "the queue without a session redirects to the login")
status, _, page = call("GET", "/operador/cola", headers={"Cookie": cookie})
check(status == 200 and "Cola humana" in page and re.search(r"pendientes? de [1-9]", page), "operator queue: opens with the session and lists the tickets the stack filed")
check("No se pudo cargar" not in page and operator_key not in page and admin_key not in page, "operator queue: loaded from the API, and no key in the page")

# the UI kit gallery is a development tool: a production build answers 404 unless UI_GALLERY=1
check(call("GET", "/dev/ui")[0] == 404, "/dev/ui answers 404 in the production build")
PY
# A browser sends `Origin: null` with a form post under `Referrer-Policy: no-referrer`, which the operator forms refuse: the web
# must send a policy that keeps the origin for its own posts (found by logging in with Chromium; curl cannot show it)
headers "$WEB/operador/login" | grep -qi '^referrer-policy: same-origin' || fail "the web's Referrer-Policy is not same-origin: a browser's operator login would send Origin: null"
ok "web as a browser uses it: customer login and chat, operator login and queue, /dev/ui closed"

# --- access ---
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/admin/ops")" = 401 ] || fail "/admin/ops is open"
[ "$(curl -s -o /dev/null -w '%{http_code}' -H "X-Admin-Key: $E2E_ADMIN" "$API/admin/ops")" = 200 ] || fail "/admin/ops refuses the admin key"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/openapi.json")" = 404 ] || fail "the API schema is published"
ok "admin closed without its key, schema not published"

# --- metrics ---
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/metrics")" = 401 ] || fail "/metrics is open"
[ "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $E2E_METRICS" "$API/admin/ops")" = 401 ] || fail "the metrics token opens /admin"
scrape="$(curl -fs -H "Authorization: Bearer $E2E_METRICS" "$API/metrics")" || fail "/metrics with the token"
for m in cecilai_turns_total cecilai_escalations_total cecilai_turn_latency_seconds cecilai_stage_latency_seconds \
         cecilai_http_requests_total cecilai_llm_attempts_total cecilai_llm_budget_exhausted cecilai_llm_circuit_open \
         cecilai_rate_limit_hits_total cecilai_data_age_hours cecilai_data_freshness_slo_hours cecilai_retention_last_run_timestamp_seconds; do
  echo "$scrape" | grep -q "^# TYPE $m " || fail "/metrics lacks $m"
done
# and the smoke test's own turns are in them: two escalations (fraud, suspended account) and one expired session
echo "$scrape" | awk '/^cecilai_turns_total\{.*disposition="ESCALATE"/ {n += $NF} END {exit n >= 2 ? 0 : 1}' || fail "the smoke test's escalations are not counted"
# the container's retention loop ran at boot: its status file is what this gauge reads
echo "$scrape" | grep -Eq '^cecilai_retention_last_run_timestamp_seconds [1-9]' || fail "the retention loop has not run"
curl -fs -H "X-Admin-Key: $E2E_ADMIN" "$API/admin/audit_log?limit=500" | grep -Eq '"event": ?"retention_purge"' || fail "the purge left no audit record"
echo "$scrape" | grep -Eq '^cecilai_data_freshness_slo_hours 12(\.0)?$' || fail "FRESHNESS_SLO_HOURS did not reach the container"
curl -fs -H "X-Admin-Key: $E2E_ADMIN" "$API/admin/audit_log?limit=500" | grep -Eq '"policy_days": ?\{[^}]*"traces": ?7(\.0)?,[^}]*"tickets": ?45(\.0)?' || fail "RETENTION_*_DAYS did not reach the container"
ok "/metrics answers to its token only and exposes the expected series; retention ran and audited itself"

# --- Prometheus ---
i=0
until curl -fs "http://127.0.0.1:$E2E_PROM_PORT/api/v1/targets" | grep -q '"health":"up"'; do
  i=$((i + 1)); [ "$i" -le 30 ] || fail "Prometheus does not see the API target up"; sleep 2
done
rules="$(curl -fs "http://127.0.0.1:$E2E_PROM_PORT/api/v1/rules")"
[ "$(echo "$rules" | grep -o '"type":"alerting"' | wc -l | tr -d ' ')" -ge 20 ] || fail "Prometheus did not load the alert rules"
echo "$rules" | grep -q '"health":"err"' && fail "a rule fails to evaluate"
ok "Prometheus scrapes the API and evaluates the alert rules"

# --- Grafana ---
G="http://127.0.0.1:$E2E_GRAFANA_PORT"
i=0
until curl -fs "$G/api/health" | grep -q '"database": *"ok"'; do
  i=$((i + 1)); [ "$i" -le 30 ] || fail "Grafana does not come up"; sleep 2
done
[ "$(curl -s -o /dev/null -w '%{http_code}' "$G/api/search")" = 401 ] || fail "Grafana answers without a login"
curl -fs -u "admin:$E2E_GRAFANA_PASSWORD" "$G/api/search?query=cecilai" | grep -q '"uid":"cecilai-overview"' || fail "the dashboard was not provisioned"
curl -fs -u "admin:$E2E_GRAFANA_PASSWORD" "$G/api/datasources/uid/prometheus/health" | grep -q '"status":"OK"' || fail "Grafana cannot reach Prometheus"
# every panel's query is valid PromQL that Prometheus accepts (an empty result is fine: the stack has had no traffic for long)
python3 - "http://127.0.0.1:$E2E_PROM_PORT" <<'PY' || fail "a dashboard query is rejected by Prometheus"
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
