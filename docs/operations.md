# Operations: running, capacity, monitoring, access, retention

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
| Deterministic layers (policy, tools, rendering, tracing) | 58–80 turns/s on 1 thread, 170–191 turns/s on 8 threads, p95 27–33 ms / 63–73 ms | `make loadtest` on the full 4.4M-transaction warehouse, LLM excluded; design v3, four runs on a 16-thread laptop |
| LLM calls per turn | at most 1 (design v3); turns decided by the pre-LLM checks make none | 0.80 per case with Sonnet 5 on the held-out sample (`llm_calls_per_case`) |
| LLM latency and cost | Claude Sonnet 5 (effort low): 1.8 s p50 / 3.9 s p95 per case, USD 0.0014 per case (0.0029 per safe resolution); Haiku 4.5: 1.2 / 3.8 s, USD 0.0023 per case | `make eval-live`, 132 held-out cases, `eval/reports/SYSTEM_EVAL_LIVE.md`; the tools + rules prefix is prompt-cached (≈1.7K of ≈2.1K input tokens in the smoke run on prompt 3.0.0, `eval/reports/LIVE_SMOKE.md`) |
| LLM provider | the real ceiling: provider rate limits (per key, per minute), **not measured here**: the live evaluation sends one conversation at a time | scale with paid tiers, multiple keys, or a smaller model for tool routing |
| DuckDB | single writer; many readers (the API opens read-only) | ingestion and serving can run side by side |
| In-memory state | sessions ≤ 50k, conversations ≤ 10k × 8 messages | per process; multi-replica needs Redis |

Scaling path:
1. More uvicorn workers or replicas (stateless apart from the session and
   conversation stores).
2. Move sessions and conversations to Redis.
3. Serve reads from a replicated store instead of a local DuckDB file.
4. Queue and back off on provider 429s; the circuit breaker already stops hammering a failing provider.

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
