# Operations: running, capacity, monitoring, access, retention

## Local development

Python stays at the repository root. `web/` is a separate TanStack Start
package with its own pnpm lockfile. Use Python 3.11, Node 24 and pnpm 10.33.2.
`make setup` installs Python dependencies; `make web-setup` installs frontend
dependencies. Activate `.venv` or pass `PY=.venv/bin/python` to each Make command.

For an offline run, build the fixture warehouse in a temporary directory.
This leaves any existing warehouse in place and needs no S3 or model calls:

```bash
source .venv/bin/activate
export DUCKDB_PATH="$(mktemp -d)/fixture.duckdb"
python -m data.pipeline --profile serving --source local --raw-dir tests/fixtures/raw \
  --report "$(dirname "$DUCKDB_PATH")/quality_report.json"
make web-setup
make serve-all
```

Open `http://127.0.0.1:3000` for the new landing page, or
`http://127.0.0.1:8000` for the existing chat/demo UI. The fixture command
only prepares data; chat still uses the root `.env` settings for identity and
model access. Fetching the landing page and health endpoints makes no model calls.

`make serve-all` runs `make serve` and `make serve-web` through `concurrently`,
installed by `make web-setup`. Both commands use the same settings as when run
separately. The API runs without reload; Vite reloads the frontend as you edit.
Logs are labeled `api` and `web`. Ctrl-C or SIGTERM stops both services and their
children. If either command exits, the other stops too. An occupied web port
fails instead of silently selecting another port.

| Command or setting | Behavior |
| --- | --- |
| `make serve-all WEB_PORT=3001 API_PORT=8001` | Starts both on alternate ports and points the proxy at port 8001 |
| `make serve API_PORT=8001` | Runs only Python, without reload; `API_HOST` defaults to `0.0.0.0` |
| `make serve-web WEB_PORT=3001` | Runs only the frontend; `WEB_HOST` defaults to `127.0.0.1` |
| `make web-typecheck` | Checks TypeScript |
| `make web-build` | Builds client and server bundles in `web/dist/` |

For `make serve-web`, copy `web/.env.example` to `web/.env` and set
`AGENT_API_URL` to the backend URL, or provide it in the command's environment.
It defaults to `http://127.0.0.1:8000`. With `make serve-all`, Make supplies
`http://127.0.0.1:$(API_PORT)` instead; an explicit `AGENT_API_URL` environment
variable or Make argument overrides that value. Backend settings still belong
in the root `.env`. The frontend loads only `AGENT_` settings into its server
environment; never prefix backend secrets with `VITE_`.

`GET /api/agent/health` forwards Python's `/health` JSON and status code with
`Cache-Control: no-store`. Connection failures, invalid JSON and requests that
take longer than five seconds return HTTP 503 with `{"status":"unavailable"}`.
It reports the backend's response as-is, including the current backend's
`status: ok` when `data_as_of` says data is unavailable.

The new frontend is a setup skeleton. Authentication and chat are still in the
existing Python UI. The container and Render deployment below continue to
serve Python; deploying the TanStack server requires a separate hosting setup.

## Deploy (container)

```bash
make docker-build
docker run -p 8000:8000 \
  -e AWS_ACCESS_KEY_ID=... -e AWS_SECRET_ACCESS_KEY=... \
  -e DATASET_BUCKET=... -e LLM_PROVIDERS=anthropic -e ANTHROPIC_API_KEY=... \
  -e DEMO_IDP_SECRET=$(openssl rand -hex 24) -e ADMIN_API_KEY=$(openssl rand -hex 24) \
  -v warehouse:/app/data/warehouse latam-bank-agent
```

First boot ingests `INGEST_ARGS`. The default is a deterministic 5,000-customer
sample with the last 12 months of transactions: about 14 MB, 20 s of load
after download, DuckDB capped at 400 MB. It picks sandbox demo customers,
then serves on `$PORT`.
- Daily files download 24 at a time: the whole dataset's 4,388 (1.1 GB) took
  78 s from Argentina, where one at a time they took hours.
- The load's quality report is written next to the warehouse, on the same
  disk (`DQ_REPORT_PATH`), and `/admin/data_quality` serves it.
- The warehouse is built under a temporary name and renamed only when the load
  succeeds: a first load that fails (wrong keys, bucket unreachable, a quality
  gate) or is killed half way (a cancelled deploy, out of memory) leaves nothing
  a later boot could serve, and the next boot loads again.
- For the full dataset, set `INGEST_ARGS="--profile serving"` and give the container ~2 GB.
- Without `DEMO_IDP_SECRET` every login is refused (fails closed).
- Without `ADMIN_API_KEY`, `/admin/*` returns 503.
- The app runs as a non-root user. The container starts as root only so the
  entrypoint can hand `/app/data` to that user (a platform may mount the disk
  owned by root), then drops to it with `setpriv`.
- The healthcheck is `/health`: the data as-of date, the configured LLM
  providers, whether the daily model budget is exhausted and whether the
  classifier loaded.
- Without the organizer's S3 access, `INGEST_ARGS="--profile serving --source
  local --raw-dir /app/tests/fixtures/raw"` loads the hand-made fixture (5
  customers) that ships in the image.

CI builds this image on every push, boots it the way Render does (a disk
mounted owned by root, its own `PORT`), runs `ops/container_smoke.py`, checks
that the app runs unprivileged and owns its data, restarts it and checks the
disk kept the warehouse and its quality report. It also boots it with a load
that fails and checks nothing was left on the disk, then leaves what a killed
boot would (a partial build, a stale WAL) and checks the next boot loads again.

## Deploy on Render (the jury demo)

`render.yaml` is the Blueprint: one Docker web service on a paid instance
(`0.5c-512mb`; the free one sleeps and has no disk), a 1 GB disk at
`/app/data/warehouse`, `DEMO_MODE=1`, generated secrets for the test IdP and the
admin key, and the caps below.
1. In Render: New > Blueprint, pick the repository and branch. When asked, fill
   `ANTHROPIC_API_KEY` (a key with a spend limit set at the provider), optionally
   `GROQ_API_KEY`, and the organizer's `AWS_*` and `DATASET_BUCKET`. Without those
   three, change `INGEST_ARGS` to the fixture line above.
2. First boot ingests the 5,000-customer sample (about 20 s of load after the
   download) and then passes `/health`. The disk keeps it: later deploys and
   restarts do not re-ingest, even if the bucket closes after the deadline. If
   that first load fails, the deploy fails with the reason in the logs and no
   warehouse is left on the disk: fix the variable and deploy again.
3. Later changes deploy by hand (Manual Deploy in the dashboard): the Blueprint
   turns auto-deploy off, so a push never restarts the instance, and with it the
   sessions, the day's budget count and the demo's fault flags, while the jury
   is using it.
4. Check it from any machine: `python ops/container_smoke.py https://<service>.onrender.com`.
   With the admin key (Render dashboard > Environment), `/admin/llm_budget`
   shows today's model spend.

Two settings exist because of how Render works:
- **The client's address.** Render's proxy is the peer of every request and it
  sends no `X-Forwarded-For`; the real address arrives in `CF-Connecting-IP`,
  set by its Cloudflare edge, which no client can forge (measured on a Render
  service, 2026-09-27). `CLIENT_IP_HEADER=CF-Connecting-IP` makes the per-client
  login limit use it. Leave it unset anywhere that header is not set by a
  trusted edge, or any client could pick its own address.
- **The daily model budget.** `LLM_DAILY_BUDGET_USD` (UTC day). Past it, the
  assistant runs as if the model were down: plain balance questions are still
  answered from verified data, the rest goes to a person. It lives in memory,
  so the spend limit on the provider key stays the hard ceiling.

## Public repository (the submission)

The submission is a public repository; this one keeps what must not be
public. `ops/export_public.py` makes the public copy from a fresh clone:

```bash
pip install git-filter-repo
python ops/export_public.py . ../factored-hackathon-2026-<team> <redactions-file>
```

- It removes from every commit the organizer's row-level data, by pattern so a
  new file is covered too: every case file under `eval/workload/` (the
  generated workloads, regenerated with `make workload`, and any other set,
  such as the human one, which belongs there) and every per-case eval JSON
  (`eval/reports/system_eval*.json`, regenerated with `make eval`). It also
  removes the v2 demo video, and replaces the strings in the redactions
  file (kept outside any repository): the organizer's bucket name and
  account id, which early commits carried.
- It scans every blob of every commit by shape (keys, tokens, JWTs, private
  keys, credential assignments, literal fallbacks of environment variables,
  S3 URIs, 12-digit numbers, real dataset ids) and fails if a redacted value
  survives. A person reads the listed hits before publishing.
- Publish the result as a **new** repository: a force-push over an old one
  leaves the old blobs reachable by their commit ids.

## Capacity

| Layer | Measured / known limit | Notes |
|---|---|---|
| Deterministic layers (policy, tools, rendering, tracing) | 58–80 turns/s on 1 thread, 170–191 turns/s on 8 threads, p95 27–33 ms / 63–73 ms | `make loadtest` on the full 4.4M-transaction warehouse, LLM excluded; design v3, four runs on a 16-thread laptop. Not re-run since: the full warehouse is not on the machine that measured the rest of this section |
| The same layers on the fixture warehouse, with this branch's traces, stage timing and retries | 557–566 turns/s on 1 thread (p50 1.6 ms, p95 2.0 ms), 565–573 turns/s on 8 threads (p50 11 ms, p95 14–17 ms) | `make loadtest-fixture PY=.venv/bin/python`, two runs each, Apple M5 Pro (18 threads), the model scripted. The fixture holds 5 customers, so this is the Python overhead per turn (about 1.6 ms), not warehouse query cost; 8 threads share one GIL, so they add latency and no throughput |
| HTTP surface, model answering | 17.4 chats/s at saturation with 32 slots and a model at 1.8 s (32 / 1.8 s = 17.8 ideal); up to 32 concurrent clients served at 1.8 s p50; 64 clients wait for a slot (p50 3.6 s); 128–256 clients: 256 served per level at p50 5.4 s (the 5 s queue wait plus the model), the rest refused with 503 + `Retry-After` in 1.6 ms (p95) | `make loadtest-http PY=.venv/bin/python`, report in `eval/reports/LOADTEST_HTTP.md`: the real API on uvicorn, fixture warehouse, **model simulated at the measured 1.8 s p50**, closed-loop clients that wait out `Retry-After`, load generator on the same machine and process |
| HTTP surface, model down | every turn falls back to a handoff: 330–420 turns/s and p95 22–212 ms with 8–64 clients; 106–140 turns/s and p95 2.3–3.8 s with 128–256 clients | same report. The knee at 128 clients is the load generator and the server sharing one process (GIL) and one 128-slot accept queue on this laptop, not a limit of the service; a clean number needs a separate load host |
| Clients that ignore `Retry-After` | same 17.2–17.3 chats/s served, 288–640 refusals per level answered in 157 ms–1.5 s (p95), no errors | `eval/reports/LOADTEST_HTTP_NO_BACKOFF.md` (the second command of `make loadtest-http`): refusing costs almost nothing, so a hammering client does not slow the ones being served |
| Per-session rate limit | 20/min: 30 back-to-back messages gave 20 answers and 10 refusals with 429 | same report |
| LLM calls per turn | at most 1 (design v3); turns decided by the pre-LLM checks make none | 0.80 per case with Sonnet 5 on the held-out sample (`llm_calls_per_case`) |
| LLM latency and cost | Claude Sonnet 5 (effort low): 1.8 s p50 / 3.9 s p95 per case, USD 0.0014 per case (0.0029 per safe resolution); Haiku 4.5: 1.2 / 3.8 s, USD 0.0023 per case | `make eval-live`, 132 held-out cases, `eval/reports/SYSTEM_EVAL_LIVE.md`; the tools + rules prefix is prompt-cached (≈1.7K of ≈2.1K input tokens in the smoke run on prompt 3.0.0, `eval/reports/LIVE_SMOKE.md`) |
| LLM provider | the real ceiling: provider rate limits (per key, per minute), **not measured here**: the live evaluation sends one conversation at a time | scale with paid tiers, multiple keys, or a smaller model for tool routing |
| Local model (`local`, Ollama) | throughput is that of the hardware running it, **not measured**: Ollama was not installed on the machine that built this branch; the provider is tested against a fake server (`tests/test_local_llm.py`) | costs 0 per token. A CPU-only model is slow and its first call loads it: raise `LLM_TIMEOUT_SECONDS`, `LLM_TOTAL_BUDGET_SECONDS` and `TURN_BUDGET_SECONDS` (`.env.example`) |
| DuckDB | single writer; many readers (the API opens read-only) | ingestion and serving can run side by side |
| In-memory state | sessions ≤ 50k, conversations ≤ 10k × 8 messages | per process; multi-replica needs Redis |

What a saturated service does, by design (the limits themselves are in "Capacity limits" below): it never queues without
bound. A chat that finds all 32 slots busy waits in a queue of at most 64 for at most 5 s; anything past that, or that
waits longer, is refused at once with 503 and `Retry-After: 3`. Rate-limited callers get 429 with the seconds until they
may try again. The simulated model in the load test is the only part not measured: the provider's own limits still are.

Scaling path:
1. More uvicorn workers or replicas (stateless apart from the session and
   conversation stores); every in-memory limit then needs a shared store.
2. Move sessions and conversations to Redis.
3. Serve reads from a replicated store instead of a local DuckDB file.
4. Queue and back off on provider 429s; the circuit breaker already stops hammering a failing provider.

## Resilience and traces

Four things make the runtime credible under failure. Each has code, a hermetic test and a command that reproduces
its evidence. The full suite is `make test PY=.venv/bin/python`; the files below are the ones that pin each point.

| Point | What is guaranteed | Code | Test | Command |
|---|---|---|---|---|
| Traces | one id per turn from the HTTP request to the ticket; time and outcome per stage; logs without customer data | `api/middleware.py`, `agent/observability.py`, `agent/core/orchestrator.py` | `tests/test_tracing.py` (13) | `pytest tests/test_tracing.py -q` |
| Bounded retries | capped attempts, jittered capped backoff, one time budget per turn, retryable errors only, no unkeyed repeat of a write | `agent/resilience.py`, `agent/llm/client.py`, `agent/tools/traces.py`, `agent/policy/escalation.py` | `tests/test_retry.py` (13), `tests/test_resilience.py` (24), `tests/test_local_llm.py` (11) | `pytest tests/test_retry.py tests/test_resilience.py tests/test_local_llm.py -q` |
| Safe fallback | every failure ends in a fixed reply or a handoff: never an invented answer, never a half-done action | `agent/core/orchestrator.py`, `agent/policy/router.py` | `tests/test_resilience.py` | `pytest tests/test_resilience.py -q` |
| Capacity limits | body size, concurrency with a queue and 503, rate limits with 429, per-session and daily cost caps, prompt and output caps | `api/middleware.py`, `api/main.py`, `agent/llm/budget.py`, `agent/core/orchestrator.py` | `tests/test_capacity.py` (21) | `pytest tests/test_capacity.py -q`; `make loadtest-http PY=.venv/bin/python` |

All four run in the hermetic target `make test-resilience` (82 tests, about 9 s, no S3, no keys, no network beyond 127.0.0.1).

### Traces: what one turn leaves behind

The API gives every request a trace id (32 lowercase hex, the size of a W3C trace id) and the turn adopts it. The
same id is in every place a person or a tool will look:

| Where | Field |
|---|---|
| response headers (every response, errors and refusals included) | `X-Request-ID`, and `traceparent: 00-<trace id>-<span id>-01` |
| `/chat` body | `trace_id` |
| trace record (`traces.jsonl`, `/admin/traces/{id}`) | `trace_id`, plus `span_id` (the request's root span) |
| tool audit (`audit_log.jsonl`) and audit events such as `operator_auth_failed` | `trace_id` |
| escalation ticket | `trace_id` (and the 8-character code the customer is given when a handoff could not be filed) |
| every log line of the turn | `trace_id` |

A caller's own ids are kept next to ours, never in place of them: a valid incoming `traceparent` becomes
`upstream_trace_id` (and `upstream_span_id`), a valid `X-Request-ID` (1-64 of `A-Za-z0-9._-`) becomes
`client_request_id`; anything else is dropped. A client therefore cannot choose our id, two turns never share one, and
a lookup by id finds one turn.

Each turn's trace record also has `stages`: one span-shaped entry per step, with a start offset, a duration and an
outcome (`ok`, or the exception type when the step failed):

```json
{"stage": "llm", "span_id": "9c1f0d7e2b4a6c35", "start_ms": 4.1, "ms": 1834.6, "outcome": "ok", "provider": "anthropic", "model": "claude-sonnet-5", "route": "primary"}
```

The stages are `session`, `pre_llm`, `ownership_check`, `catalog`, `llm`, `tool:<name>`, `render`, `ticket` (the handoff
write and its read-back) and `trace_service` (with the number of `attempts`). `turn_budget_left_ms` says how much of the
turn's clock remained. The shape maps one to one to OpenTelemetry spans (`trace_id`, `span_id`, name, start, duration,
status), so an OTLP exporter can be added without changing what is recorded. None is wired: nothing here imports
OpenTelemetry, and the alerts in Monitoring read the JSONL as before (LIMITATIONS.md, Operations).

Logs use the standard `logging` module. `LOG_FORMAT=json` writes one JSON object per line (`ts`, `level`, `logger`,
`trace_id`, `msg` and the turn's fields); the default is text with the id in brackets; `LOG_LEVEL` sets the level. The
turn line (`cecilai.turn`) carries the disposition, category, rule, latency, model calls, cost, ticket id and the
milliseconds per stage. It never carries what the customer wrote, a reply, a figure or a customer id, and an exception is
logged by type only, because its message can quote data (`test_the_turn_log_line_has_the_id_and_the_outcome_and_nothing_the_customer_wrote`).
The trace record itself does hold the reply text and the masked request, as before: it is customer data and follows
Data retention.

### Bounded retries

`agent/resilience.py` holds the one rule set; each caller states only what it knows about its own call.

| Call | Attempts | Backoff | Budget | Retried | Repeat safety |
|---|---|---|---|---|---|
| model (`LLMClient`: `anthropic`, `groq`, `together`, and `local` for Ollama or any OpenAI-compatible server, in `LLM_PROVIDERS` order) | 2 per provider, then the next provider | 0.5 s doubling, capped at 4 s, half fixed and half random | `min(LLM_TOTAL_BUDGET_SECONDS=25, what the turn has left)`; a wait longer than what remains is not started | timeouts, connection errors, 429, 5xx; auth, bad request and refusals go straight to the next provider; a `Retry-After` on the error is never undercut (and if it is longer than what the turn has left, the wait is not started) | a call that only proposes tools: nothing is written |
| model circuit | opens after 2 consecutive failures for 30 s, then one probe | | | a provider whose circuit just opened gets no more attempts in that turn | |
| tracing service (`open_verified`) | 3 | 0.1 s doubling, capped at 0.5 s | the turn's deadline | `OSError`, `Transient` | write with an idempotency key: the trace id derives from customer and movement and `open` returns the request it already made, so a write that landed but was not confirmed is not repeated |
| ticket queue (`enqueue`) | 3 | 0.1 s doubling, capped at 0.5 s | the turn's deadline | `OSError` | the ticket id is the key: a retry first looks for the ticket, so a write that landed is not filed twice |
| read tools (`run_tool`) | 2 | 0.05 s doubling, capped at 0.25 s | the turn's deadline | `OSError`, `TimeoutError`, `ConnectionError`, DuckDB I/O and connection errors | reads; a `ToolError` (not yours, no data, bad argument) is an answer and is never retried |

The turn has one clock (`TURN_BUDGET_SECONDS`, default 30, in `agent/resilience.py`) that the orchestrator starts and
the model client and every retry draw on. The first attempt of any call always runs, even past the deadline: a handoff
must be tried. A write with neither `idempotent=True` nor an idempotency key is attempted once, whatever the error.
`tests/test_retry.py` proves each bound with injected faults (attempt caps, the backoff range, no sleep after the last
attempt, no wait past the deadline, permanent errors not retried, the write rule).

### Safe fallback

One test per way a turn can fail (`tests/test_resilience.py`). In every row the reply is a fixed template or a handoff
(`verified_facts` is empty and the text is one of `render.MSG`), and the ticket carries the turn's trace id.

| Failure | What the customer gets | Trace `policy_rule` / ticket category |
|---|---|---|
| every provider fails transiently (503, 429, timeout, connection) | a handoff, after at most 2 attempts per provider | `llm_unavailable` |
| permanent model error (auth, bad request) | a handoff, one attempt | `llm_unavailable` |
| circuit open | a handoff; the provider is not called | `llm_unavailable` (attempt `circuit_open`) |
| the circuit's cooldown ends | one probe goes out; success closes it, failure opens it again | |
| the model runs out the turn's time budget | a handoff, no hang | `llm_unavailable` (attempt `turn_budget_exhausted`) |
| the daily model budget is spent | a plain balance question is answered from data; out of scope gets an abstain; the rest a handoff | `degraded:*` or `llm_unavailable` |
| this session spent its own budget | the same, for that session only | attempt `session_budget_exhausted` |
| the model answers with prose or an unknown tool | prose is never shown (clarify or abstain by template); an unknown tool is a handoff | `tool_failure` |
| the turn's time ran out after the model answered | nothing is looked up; a handoff | `turn_timeout` |
| a tool is down | 2 attempts, then a handoff; a `ToolError` that is an answer is not retried | `tool_failure` / `data_unavailable` |
| the tracing service fails once | the retry opens exactly one request and it is read back | `action:trace_opened` |
| the tracing service stays down | 3 attempts; the customer is never told a trace exists | `action:trace_unverified` (handoff) |
| the ticket write lands but reports failure | not filed twice | `escalate` |
| the queue cannot be written | 3 attempts; the customer is told nothing was registered and gets the 8-character code | `…|handoff_unverified` |
| our own code raises (any exception in a turn) | a handoff if a ticket can be filed and read back, otherwise the unverified message with the code; the exception text is never kept | `tool_failure` (trace rule `unexpected_failure`, `error_type`) |
| the state store cannot save the conversation | the reply is still returned | |
| an exception outside a turn | HTTP 500 that says only `internal error` and carries the request id | |

### Capacity limits

All refusals are counted at `GET /admin/capacity` (`X-Admin-Key`), together with the limits in force and the peak
concurrency, so a limit that is too tight or a flood shows up without reading logs.

| Limit | Default | Setting | Refusal |
|---|---|---|---|
| request body | 16 KiB (a message is at most 1,000 characters) | `MAX_REQUEST_BYTES` | 413, by `Content-Length` or by counting |
| message | 1-1,000 characters | `ChatRequest` | 422 |
| body not finished within | 10 s | `REQUEST_BODY_TIMEOUT_SECONDS` | 408 |
| chats running at once | 32 (under the 40 threads of the server's pool) | `MAX_CONCURRENT_CHATS` | queue, then 503 |
| chats waiting for a slot | 64, at most 5 s | `CHAT_QUEUE_MAX`, `CHAT_QUEUE_WAIT_SECONDS` | 503 + `Retry-After` (`CHAT_RETRY_AFTER_SECONDS`, 3) |
| chat rate per session | 20/min | `CHAT_RATE_PER_MIN` | 429 + `Retry-After` |
| chat rate per customer, across sessions | 40/min | `CHAT_CUSTOMER_RATE_PER_MIN` | 429 + `Retry-After` |
| chat rate per client address | 120/min (see below) | `CHAT_IP_RATE_PER_MIN` | 429 + `Retry-After` |
| login rate per client address | 10/min | `LOGIN_RATE_PER_MIN` | 429 + `Retry-After` |
| turn time | 30 s | `TURN_BUDGET_SECONDS` | handoff |
| model output per call | 4,096 tokens | `LLM_MAX_OUTPUT_TOKENS` | a cut-off answer is never acted on |
| prompt | 24,000 characters (about 6K tokens; the fixed part is about 2.1K tokens and the worst real turn is under 16,000 characters) | `LLM_MAX_PROMPT_CHARS` | the oldest history is dropped first |
| model spend per session | USD 0.25 | `LLM_SESSION_BUDGET_USD` (0 = off) | degraded mode for that session |
| model spend per UTC day | unset | `LLM_DAILY_BUDGET_USD` | degraded mode for everyone |
| connection idle | 5 s keep-alive; 20 s to drain on shutdown | uvicorn `--timeout-keep-alive`, `--timeout-graceful-shutdown` (`make serve`, the container entrypoint) | |

The rate limiters, the model budgets, the circuit breakers and the concurrency gate live in memory of one process: they
reset on restart and are not shared between replicas, so several replicas multiply every limit (a shared store such as
Redis is the next step). The limiters are bounded (idle keys are swept, at most 100,000 kept). Behind the web BFF the
address is the end user's only when `CLIENT_IP_HEADER` names the header the BFF sets; without it every user shares the
BFF's address, which is why the per-address chat default is generous. The server has no timeout for reading request
headers: a slow-headers client has to be stopped by the edge (Render's proxy does), and the body timeout above covers
the rest.

### Runbook: what to do when

- **A customer quotes a code or a trace id:** `GET /admin/traces/{id}` (the full id or the 8-character code) returns the
  turn's record with its `stages` and the tool audit; the same id is in the ticket and in every log line, so
  `grep <id>` (or the log shipper) finds the rest.
- **503 with `Retry-After` in the API's answers:** the concurrency gate is full. `GET /admin/capacity` shows
  `inflight_peak`, `waiting_peak` and `rejected.busy`. If the model is slow, look at the `llm` stage in recent traces
  before raising `MAX_CONCURRENT_CHATS` (keep it under the thread pool's 40); if the model is fine, add replicas.
- **429s:** per session, customer or address. `rate_limiter_keys` in `/admin/capacity` shows how many keys each limiter
  holds. Behind the BFF without `CLIENT_IP_HEADER`, every user is one address: set the header before lowering
  `CHAT_IP_RATE_PER_MIN`.
- **Handoffs with `llm_unavailable`:** read the attempts in the trace: `circuit_open` (a provider failed twice in a row and
  is skipped for 30 s), `turn_budget_exhausted` (the model was too slow for the turn) or
  `session_budget_exhausted` / `daily_budget_exhausted` (a spend cap, see `/admin/llm_budget`).
- **`handoff_unverified` or `unexpected_failure` in the trace rule:** the ticket queue or our own code failed; the customer got a code.
  The trace has `error_type` (never the message); the log line `turn failed (<type>)` carries the same trace id.
- **`trace_unverified`:** the tracing service did not confirm after 3 attempts (`trace_service` stage, `attempts`); a person
  opens the trace by hand.

## Monitoring

Every turn writes a trace (`traces.jsonl`) with the disposition, the policy
rule, LLM attempts, token usage (including cached tokens), latency and cost. Every
tool call writes an audit record. Signals to alert on, from those records:

| Signal | Why | Starting threshold |
|---|---|---|
| `category=security` escalations/hour | injection or enumeration attempts | > 5/h per customer, or any spike |
| `handoff_unverified` in `policy_rule` | a ticket that did not read back: the customer was told to call | any |
| `reference_to_foreign_product` escalations | explicit attempts to read another customer's product | any spike |
| CLARIFY rate and `MissingSlot`/`InvalidArgument` share | drift in how well the model understands requests | ±50% week over week |
| model refusals (`ModelRefusal` in LLM attempts) | provider safety classifiers declining banking requests | any sustained |
| `llm_unavailable` + `circuit_open` attempts | provider outage | any sustained |
| escalation rate by category | drift in data quality (e.g. `data_unavailable`) or demand | ±50% week over week |
| p95 turn latency | UX and budget | > 8 s |
| cost per safe resolution | unit economics | budget-dependent |
| `_dq_results` failed errors, `_ingestion_log` failures | pipeline health | any |

Production would ship these to a metrics stack (e.g. OpenTelemetry → Grafana)
instead of reading JSONL. The field names are already stable for that.

While the demo is live, `GET /admin/ops` (with `X-Admin-Key`) summarizes the
last 1,000 turns (`?limit=` up to 5,000): dispositions, escalations by
category, the top rules, degraded-mode turns, `llm_unavailable`,
`handoff_unverified`, traces opened, model calls, cost and unpriced turns,
p50/p95 latency, the models that answered and the day's model budget. Check
it once a day during the judging window, alongside `/health`.
`GET /admin/trace_log` returns the turns' trace records themselves, oldest
first (`?limit=`, default 500, up to 5,000), which is what the red-team
report is built from (`docs/red_team.md`).

## Access control

| Surface | Control |
|---|---|
| `/auth/session` | customer_id + test PIN (HMAC under a server secret), lockout after 5 failures per 15 min, 10 req/min per client address by default (30 in the Render Blueprint, where every guided scenario opens a session; `CLIENT_IP_HEADER` behind Render), generic error messages |
| model spend | `LLM_DAILY_BUDGET_USD` per UTC day, then degraded mode; plus the spend limit on the provider key |
| `/chat` | bearer session token (15 min TTL), 20 msgs/min per session, 1,000 chars max |
| customer data | ownership enforced in every tool against the session's customer; account numbers leave the tool layer as last-4 only |
| `/admin/*` | `X-Admin-Key` (constant-time compare), disabled if unset |
| tickets / traces | carry `session_ref` (hash), never the token |
| secrets | `.env` / platform secret store; `.env` is git-ignored; nothing is baked into the image |

## Data retention

| Data | Retention | Mechanism |
|---|---|---|
| session tokens | 15 min TTL, memory only | `SessionStore` |
| conversation history | memory only, LRU, last 8 messages | `ConversationStore` |
| traces, tool audit log | 30 days | `make retention` (`ops/retention.py`), run daily |
| escalation tickets (local queue) | 90 days here | in production they live in the bank's case system under its regulatory schedule |
| warehouse | replaced on each full ingestion; lineage kept in `_ingestion_log` | pipeline |

The records contain customer data, so PII redaction before export and
encryption at rest remain to be done (LIMITATIONS.md).

## Runbook (short)

- **LLM provider down:** nothing to do immediately. The circuit breaker opens,
  plain balance questions are answered deterministically, clear out-of-scope
  requests get an abstain, and the rest escalate with `category=llm_unavailable`.
  Check `/health` and the provider status.
- **Pipeline failed a quality gate:** the load rolled back, so serving is on the
  previous data (on a first boot there is none: the container exits and loads
  again on the next one). Read `failure` and the failed checks in the report
  (`--report`; in the container, `DQ_REPORT_PATH` next to the warehouse, also at
  `/admin/data_quality`) and `_quarantine_<table>`. Decide
  whether it is a source defect (tell the provider) or a contract change
  (bump `CONTRACT_VERSION`, document it in `CONTRACT_DEVIATIONS`).
- **Security escalation spike:** pull traces by `session_ref` at
  `/admin/traces/{id}` and revoke sessions.
- **Daily model budget exhausted** (`/health` says so): the demo keeps working
  in degraded mode until 00:00 UTC. Check `/admin/llm_budget` and the traces
  for abuse; raise `LLM_DAILY_BUDGET_USD` only if the traffic is legitimate.
