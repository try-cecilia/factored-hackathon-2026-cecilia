# Operations: running, capacity, monitoring, access, retention

## Deploy (container)

```bash
make docker-build
docker run -p 8000:8000 \
  -e AWS_ACCESS_KEY_ID=... -e AWS_SECRET_ACCESS_KEY=... \
  -e GROQ_API_KEY=... -e TOGETHER_API_KEY=... \
  -e DEMO_IDP_SECRET=$(openssl rand -hex 24) -e ADMIN_API_KEY=$(openssl rand -hex 24) \
  -v warehouse:/app/data/warehouse latam-bank-agent
```

First boot ingests `INGEST_ARGS`. The default is a deterministic 5,000-customer
sample with the last 12 months of transactions: about 14 MB, 20 s of load
after download, DuckDB capped at 400 MB. It picks sandbox demo customers,
then serves on `$PORT`.
- For the full dataset, set `INGEST_ARGS="--profile serving"` and give the container ~2 GB.
- Without `DEMO_IDP_SECRET` every login is refused (fails closed).
- Without `ADMIN_API_KEY`, `/admin/*` returns 503.
- The runtime user is non-root. The healthcheck is `/health`, which reports the
  data as-of date, the configured LLM providers and whether the classifier loaded.

Free-tier hosts (Render, Fly.io, Railway) run this image as-is; mount a volume
at `/app/data/warehouse` so restarts don't re-ingest.

## Capacity

| Layer | Measured / known limit | Notes |
|---|---|---|
| Deterministic layers (policy, tools, grounding, tracing) | 71.7 turns/s on 1 thread, 99.7 turns/s on 8 threads, p95 39 ms / 128 ms | `make loadtest` on the full 4.4M-transaction warehouse, LLM excluded; GIL-bound |
| LLM calls per case | 1.33 on the test workload (2 per resolved turn: tool choice + phrasing; up to 4 with multi-step) | scripted run, `llm_calls_per_case` |
| LLM provider | the real ceiling: provider rate limits (per key, per minute) and per-call latency, **not measured here** | measure with `make eval-live`; scale with paid tiers, multiple keys, or the smaller 8B model for tool routing |
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
rule, LLM attempts, token usage, grounding result, latency and cost. Every
tool call writes an audit record. Signals to alert on, from those records:

| Signal | Why | Starting threshold |
|---|---|---|
| `category=security` escalations/hour | injection or enumeration attempts | > 5/h per customer, or any spike |
| grounding `fallback_used` rate | the model stating unverified figures | > 5% of AUTO_RESOLVE |
| `llm_unavailable` + `circuit_open` attempts | provider outage | any sustained |
| escalation rate by category | drift in data quality (e.g. `data_unavailable`) or demand | ±50% week over week |
| p95 turn latency | UX and budget | > 8 s |
| cost per safe resolution | unit economics | budget-dependent |
| `_dq_results` failed errors, `_ingestion_log` failures | pipeline health | any |

Production would ship these to a metrics stack (e.g. OpenTelemetry → Grafana)
instead of reading JSONL. The field names are already stable for that.

## Access control

| Surface | Control |
|---|---|
| `/auth/session` | customer_id + test PIN (HMAC under a server secret), lockout after 5 failures per 15 min, 10 req/min per IP, generic error messages |
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
  previous data. Read `failure` and the failed checks in
  `data/reports/quality_report.json` and `_quarantine_<table>`. Decide
  whether it is a source defect (tell the provider) or a contract change
  (bump `CONTRACT_VERSION`, document it in `CONTRACT_DEVIATIONS`).
- **Security escalation spike:** pull traces by `session_ref` at
  `/admin/traces/{id}` and revoke sessions.
