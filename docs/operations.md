# Operations: running, capacity, monitoring, access, retention

## Local development

### One command: `make up`

Needs Docker with Compose v2 and Python 3 (only to write `.env`). No account, no S3 bucket and no model key:

```bash
make up          # writes .env with fresh secrets if there is none, builds both images, starts API + web, waits until healthy
# web: http://127.0.0.1:3000   API and the chat page: http://127.0.0.1:8000   (DEMO_MODE=1, the fixture warehouse)
make down        # stops it (its volumes stay); `make clean-volumes` also deletes them, after asking
```

`make env` (run by `make up`) copies `.env.example` to `.env` with a random `DEMO_IDP_SECRET`, `ADMIN_API_KEY`,
`METRICS_TOKEN`, `GRAFANA_ADMIN_PASSWORD` and an `OPERATOR_KEYS` entry, the fixture warehouse (`tests/fixtures/raw`, 5
customers, no bucket) and `DEMO_MODE=1` so the guided scenarios and test PINs work. An existing `.env` is left alone, which is
right for your edits but means an old one can lack settings added since, or carry an `INGEST_ARGS` copied from the example (it has
no `--source local`, so the first boot would read the organizer's bucket). So `make up` (and the other `up-*` targets) also runs
`make env-check`: a warning, never an error, that lists the names `.env.example` has and `.env` lacks (names only, no value is
ever printed) and says if `INGEST_ARGS` would use S3. `make env-fill` appends the missing ones, secrets generated, and changes
nothing that is already there. With no model key the assistant runs in degraded mode: plain balances from verified data, everything else goes to a person, and no
model is called. Every setting of `.env.example` reaches the API container as written there (a test fails if the compose file stops passing one the
code reads; `make compose-e2e` checks that `SECURITY_HSTS`, `FRESHNESS_SLO_HOURS` and `RETENTION_*_DAYS` take effect inside it).
Ports are published on `127.0.0.1` only.

**The web in Docker runs in production mode**, so the operator console (`/operador`) refuses every form post unless the web
knows the origin the browser sees. The compose passes `WEB_PUBLIC_ORIGIN`, by default `http://127.0.0.1:${WEB_PORT}` and `http://localhost:${WEB_PORT}` (a comma-separated list of exact origins, no wildcards; right for
`make up`; set it in `.env` if you reach the web by another name), and the other settings the web reads: `TRUSTED_CLIENT_IP_HEADER`
(leave empty locally), `OPERATOR_IDLE_SECONDS` (to try the idle expiry without waiting 30 minutes) and `UI_GALLERY` (`1`
publishes the UI kit gallery at `/dev/ui`; `0`, the default, is a 404 as on a real deploy). `tests/test_setup.py` fails if the web
reads a setting the compose does not pass. In the browser: `http://127.0.0.1:3000/login` with a test PIN from the chat page
(`DEMO_MODE=1`) for the customer, and `/operador/login` with `ADMIN_API_KEY` and the key in `OPERATOR_KEYS` for the console (both
in `.env`; `grep` them there yourself, nothing prints them). The session cookies follow the origin, not `NODE_ENV`: with an `http://` `WEB_PUBLIC_ORIGIN`
(the default here) they are plain `httpOnly` cookies without `Secure` or the `__Host-` prefix, so Safari and Chromium both keep them;
behind an `https://` origin they are `Secure` `__Host-` cookies (docs/integracion.md).

Everything the stack needs runs in it. The cloud services the project can use are options, never requirements, and each has
a local equivalent:

| Optional cloud service | Local equivalent in the compose stack | Command |
|---|---|---|
| The organizer's S3 bucket | The fixture warehouse (default), or your own CSVs mounted read-only and ingested at first boot | `make up` · `make up-dataset RAW_DIR=/path/to/data/raw` |
| A model provider's API (Anthropic, Groq, Together) | No key: degraded mode. Or a local model through Ollama (OpenAI-compatible) | `make up-llm-local` · `make up-llm-host` |
| A metrics SaaS | Prometheus with the alert rules, and Grafana with a provisioned dashboard | `make monitoring-up` |
| Render | The same images, from the same compose file | `make up` |

**Your local dataset.** `make up-dataset RAW_DIR=/path/to/data/raw` mounts that folder read-only at `/app/data/raw` (it needs
`branches.csv`, `customers.csv`, `daily_exchange_rates.csv`, `products.csv`, `transactions/` and, optionally, `complaints/`),
ingests it on the first boot with `--source local` (by default the 5,000-customer, 12-month sample the Render deploy uses;
`INGEST_ARGS="--profile serving"` in the environment loads everything, with `DUCKDB_MEMORY_LIMIT=2GB` and about 2 GB for the
container) and keeps the warehouse in the volume, so later boots do not ingest again. To switch datasets run `make clean-volumes`
first (it asks, then deletes the volumes). Measured here with the fixture folder as `RAW_DIR`: a read-only mount, one ingestion, and no second
one after `docker compose restart api`. The 900 MB dataset itself was not run in this checkout.

**Monitoring.** `make monitoring-up` adds Prometheus (`http://127.0.0.1:9090`, scraping `/metrics` with `METRICS_TOKEN`, loading
`ops/alerts.yml`) and Grafana (`http://127.0.0.1:3001`, login `admin` and `GRAFANA_ADMIN_PASSWORD` from `.env`, the
"cecilai: the assistant in production" dashboard already provisioned; Grafana's telemetry and update checks are off).

**A local model.** Two ways, both through the API's `local` provider (`LLM_PROVIDERS=local`, `LOCAL_LLM_BASE_URL`,
`LOCAL_LLM_MODEL`; the provider's code is the resilience branch's, this stack only wires it):

| Variant | Command | When | Notes |
|---|---|---|---|
| (a) Ollama in the compose stack | `make up-llm-local` (`GPU=1` on Linux with an NVIDIA GPU) | Linux/GPU, or patience | A one-shot `ollama-pull` downloads `LOCAL_LLM_MODEL` into the `ollama` volume; follow it with `docker compose -f ops/docker-compose.yml --profile llm-local logs -f ollama-pull`. **On macOS Docker runs on CPU only, with no Metal: `gpt-oss:20b` would be very slow.** |
| (b) Ollama on the host | `ollama serve`, then `make up-llm-host` | macOS (Metal) or any host that already has Ollama | The API reaches it at `http://host.docker.internal:11434/v1` (`extra_hosts: host-gateway` makes that work on Linux too; there Ollama must listen beyond loopback: `OLLAMA_HOST=0.0.0.0`) |

Memory and disk, as Ollama publishes them and **not measured here** (check each model's page before relying on a number):

| `LOCAL_LLM_MODEL` | Download | Memory to run it | Use |
|---|---|---|---|
| `gpt-oss:20b` (the default) | about 14 GB | about 16 GB free RAM or VRAM | the closest to the hosted models; the Docker image adds about 5 GB |
| `qwen3:8b`, `llama3.1:8b` | about 5 GB | about 8 GB | a laptop with 16-24 GB of RAM; both take tools |
| `qwen3:4b`, `llama3.2:3b` | about 2-2.5 GB | about 4 GB | a small machine; tool calling is weaker, expect more escalations |

A model must support tool calling: the assistant only asks it to pick one of the read-only tools. Any answer it gets wrong falls
to the same checks as a hosted model's, and a model that does not answer at all falls to degraded mode.
What was verified in this checkout: the profile boots, `ollama-pull` downloads a model (tested with `qwen3:0.6b`, 0.5 GB), the
API container reaches `http://ollama:11434/v1/models` and has `LLM_PROVIDERS=local` and `LOCAL_LLM_*` set; `docker compose
config` resolves every profile. Chatting through the `local` provider waits for that provider's code. The heavy profile is not
started in CI.

**Checked end to end.** `make compose-e2e` builds both images in its own throwaway compose project (`cecilai-e2e-<random>`, its own settings file and free ports: it never touches the stack of `make up`), starts API + web + Prometheus + Grafana on the fixture,
runs the smoke test, checks that the web reaches the API and, through the web as a browser uses it, a customer's login (a wrong
PIN is refused, the right one sets an httpOnly session cookie, plain over the compose's http origin) and a chat turn, an operator's login on the plain form (refused
without an `Origin` or from another one, with a notice on the login page; accepted from either configured origin, `127.0.0.1` or `localhost`) and the queue behind it;
then it restarts the web behind an `https://` origin and repeats the web checks, which now expect `Secure` `__Host-` cookies with the tickets the stack
filed, and that `/dev/ui` answers 404; then the security headers, the access checks, `/metrics` (with and without
its token), that Prometheus scrapes the API and loaded every alert rule, that Grafana holds the dashboard and its 20 queries are
valid, and that the container's retention loop ran and audited itself; then it removes the stack. The same script is the CI job
`compose`. Without `WEB_PUBLIC_ORIGIN` in the compose the operator-login check fails (tried on purpose). Measured on a 2026-09
laptop (Docker with OrbStack, fast network): `docker compose build --no-cache` of both images
42 s; stack healthy in about 10 s after that; the whole script 24 s on a warm cache. Pulling the base images is not included.

### Setup, reproducibly

| Point | Code | Test | Command |
|---|---|---|---|
| Python dependencies pinned to exact versions, every wheel checked by sha256 | `requirements.in` / `requirements-tracking.in` compiled to `requirements.txt` / `requirements-tracking.txt` (`uv pip compile --universal --generate-hashes`), installed with `pip install --require-hashes` | `tests/test_setup.py` (locks match their pins, drift and a missing hash are caught) | `make lock` · `make lock-check` · `make setup` |
| Runtime versions declared once | `.python-version` (3.11), `.node-version` (24), `web/package.json` (`engines`, `packageManager` pnpm 10.33.2); the Dockerfiles use the same | `tests/test_setup.py` (they agree) | `cat .python-version .node-version` |
| Node dependencies | `web/pnpm-lock.yaml`, `pnpm install --frozen-lockfile` | CI job `web` | `make web-setup` |
| `.env.example` lists every setting the code reads | `.env.example` | `tests/test_setup.py` scans the code for `os.environ` reads and fails on a missing one; an empty `X_PATH=` that would replace a default is rejected | `pytest tests/test_setup.py` |
| One command for the whole stack | `Makefile` (`up`, `env-check`, `env-fill`), `ops/docker-compose.yml`, `ops/bootstrap_env.py`, `ops/env_check.py`, `ops/Dockerfile`, `ops/Dockerfile.web` | `tests/test_setup.py` (compose structure, defaults, ports on 127.0.0.1, images unprivileged, the settings the API and the web read all reach their container, `env-check`/`env-fill`); `ops/compose_e2e.sh` | `make up` · `make env-check` · `make compose-e2e` |
| CI validates it | `.github/workflows/ci.yml` (on every pull request, on each push to `main` and by hand): parallel jobs `python`, `web` (typecheck, build and `pnpm test:all`), `alerts`, `container`, `web-image`, `compose` | `tests/test_setup.py` (the jobs, their limits, the hash-checked install, that the gate and the resilience tests are covered) | the same commands, locally |

Measured on the same laptop: a fresh virtualenv with `pip install --require-hashes -r requirements-tracking.txt` (serving
lock plus mlflow, 2,918 lines of lock) took 32 s; the serving lock alone is what the API image installs. The hermetic suite
(`make test`: 945 passed, 1 skipped) takes 80 s. The Docker base images (`python:3.11-slim`, `node:24-slim`) are tags, not digests, so a rebuild
can pick up a newer patch release of them (LIMITATIONS.md).

**CI triggers.** A push to `main`, every pull request (any base branch) and `workflow_dispatch` for a branch without a PR. A branch with
an open PR runs once. A pull request has one concurrency group (`ci-pr-<number>`) and a new push to it cancels the run in progress. Any
other run (a push to `main`, a manual run) gets a group of its own (`ci-<run_id>`), so nothing cancels or replaces it: every commit of
`main` is verified, even two merges in a row, and a manual run never displaces a push. A shared group would not be enough: it keeps one
running and one pending run, and a third one cancels the pending one.

**CI hooks.** Other branches add checks without rewriting the workflow: `make gate` runs whatever `eval.gate` checks (per-category
floors included) and then `make validate-data-ml`; `make test` runs the whole `tests/` folder, `make test-resilience`'s files
included. `ops/ci_optional.sh <target>` (runs a Makefile target only if this checkout defines it) is still there for a target a
branch adds later. The `web` job also runs `pnpm test:all` (node:test, vitest on the DOM, and the HTTP tests against the production build).

**Verifying does not write.** `make gate` and `make validate-data-ml` only check: they leave every versioned file as it was, and the
`python` job fails if any step rewrote one (`git status --porcelain`, its last step). The classifier evaluation
(`python -m eval.evaluate_intent_classifier --out-dir DIR`) writes its model and report to a temporary directory in CI; `make train-eval`
without `--out-dir` is what regenerates the versioned ones. The evidence in `docs/evidence/` is regenerated
on purpose with `make evidence` (its date and commit are those of the run), and the evaluation reports with `make eval
eval-adversarial eval-failures`. `validate-data-ml` warns, without failing, when the committed `data_ml_validation.json` lists
different tests than the ones that ran: that is when to run `make evidence`.

### Without Docker

Python stays at the repository root. `web/` is a separate TanStack Start package with its own pnpm lockfile. Use Python 3.11,
Node 24 and pnpm 10.33.2. `make setup` installs the locked Python dependencies; `make web-setup` installs the frontend's.
Activate `.venv` or pass `PY=.venv/bin/python` to each Make command.

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

The web frontend holds the customer's sign-in and chat and the operator console. `ops/Dockerfile.web` builds it into an image
(locked install, build, then a runtime with only its production dependencies, unprivileged, served by `web/serve.mjs`;
`AGENT_API_URL` is read at run time), the compose stack runs it, and the Render Blueprint below runs it as a second service.

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
- **On a 512 MB instance** (the Render Blueprint) the load runs with `DUCKDB_THREADS=1` and `DUCKDB_MEMORY_LIMIT=192MB`.
  The process holds about 170 MB of its own on top of DuckDB's cap, and every DuckDB thread keeps its own CSV buffers
  (about 30 MB each), so the thread count, not only the cap, decides whether reading the year's 366 daily files fits. With
  the image's 400MB and every core, the first boot on Render was killed for memory (2026-09-29). Measured on the same
  sample (Windows working set, peak): 567 MB with 400MB and every core (and DuckDB itself ran out reading the daily files),
  432 MB with one thread and 256MB, 362 MB with one thread and 192MB; the last two load the same rows and checks.
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
- Without `ADMIN_API_KEY`, `/admin/*` returns 503; without `OPERATOR_KEYS`, acting on a ticket does; without `METRICS_TOKEN` and
  `ADMIN_API_KEY`, `/metrics` does.
- The sandbox's test credentials (`DEMO_PUBLIC_CUSTOMERS`, `/demo/*`, `/admin/demo_pin`) exist only with `DEMO_MODE=1`; the
  entrypoint picks the sandbox customers only then. `DEMO_PUBLIC_CUSTOMERS` is the one list of public accounts: the login list,
  the guided scenarios and the trace reset read it, and a scenario whose customer is not on it is not offered (unset, none is). Outside
  the container, with `DEMO_MODE=1`, set it yourself: `DEMO_PUBLIC_CUSTOMERS="$(python -m ops.demo_customers)"`.
- The demo's console (`/demo/desk/*`, `api/demo_desk.py`) needs `DEMO_MODE=1` **and** `DEMO_CONSOLE=1`, each exactly `1`:
  any other value, unset included, is the 404 of a route that does not exist. A visitor signed in as a public sandbox account
  resolves, as the bank, the cases that same session filed; there is no operator key and no operator session. See "Access
  control", "The demo's console".
- A retention loop runs beside the API (`python -m ops.retention --loop`, every `RETENTION_INTERVAL_HOURS`, 24 by default,
  0 = off): see "Data retention".
- The app runs as a non-root user. The container starts as root only so the
  entrypoint can hand `/app/data` to that user (a platform may mount the disk
  owned by root), then drops to it with `setpriv`.
- The healthcheck is `/readyz`: the warehouse, the state store and the data directory all answer (yes/no only). `/livez` is
  the bare process check, and `/health` keeps reporting the data as-of date, the configured LLM providers, whether the daily
  model budget is exhausted and whether the classifier loaded.
- Without the organizer's S3 access, `INGEST_ARGS="--profile serving --source
  local --raw-dir /app/tests/fixtures/raw"` loads the hand-made fixture (5
  customers) that ships in the image.

CI builds this image on every pull request and every push to `main`, boots it the way Render does (a disk
mounted owned by root, its own `PORT`), runs `ops/container_smoke.py`, checks
that the app runs unprivileged and owns its data, restarts it and checks the
disk kept the warehouse and its quality report. It also boots it with a load
that fails and checks nothing was left on the disk, then leaves what a killed
boot would (a partial build, a stale WAL) and checks the next boot loads again.

## Deploy on Render (the jury demo)

`render.yaml` is the Blueprint, with two Docker web services. Render is one place to run the images, not a requirement:
`make up` runs the same images locally.
- **The API** (`x-payments-agent`): a paid instance (`0.5c-512mb`; the free one sleeps and has no disk), a 1 GB disk at
  `/app/data/warehouse`, `DEMO_MODE=1` and `DEMO_CONSOLE=1`, generated secrets for the test IdP, the admin key and the metrics token, its health
  check on `/readyz`, HSTS on, one DuckDB thread and a 192MB cap for the first boot's load (see "Deploy (container)"), and the
  caps below.
- **The web** (`cecil-ai`): `ops/Dockerfile.web` with `web/` as its context, the same instance type, its health check on
  `/_healthz`. It calls the API at its public URL (`AGENT_API_URL`) and `WEB_PUBLIC_ORIGIN` is its own public URL: both are
  fixed in `render.yaml` (neither is a secret), so renaming either service means updating them. It also gets `DEMO_MODE=1`
  and `DEMO_CONSOLE=1`, the API's values, so that its own demo checks can demand `1` instead of relying on the API's 404. Its users reach the API
  from the web's address; the web forwards each user's address with `BFF_CLIENT_IP_SECRET` (the `bff-client-ip` group,
  on both services), so the API's per-client limits (logins, failed keys) count them one by one. Without that secret on
  both, they count them together.
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
4. Check it from any machine: `python ops/container_smoke.py https://<service>.onrender.com` for the API, then `/login` and
   `/operador/login` on the web.
   With the admin key (Render dashboard > Environment), `/admin/llm_budget`
   shows today's model spend.

Two settings exist because of how Render works:
- **The client's address.** Render's proxy is the peer of every request and it
  sends no `X-Forwarded-For`; the real address arrives in `CF-Connecting-IP`,
  set by its Cloudflare edge, which no client can forge (measured on a Render
  service, 2026-09-27). `CLIENT_IP_HEADER=CF-Connecting-IP` makes the per-client
  login limit use it. Leave it unset anywhere that header is not set by a
  trusted edge, or any client could pick its own address. For a call from the
  web service that edge shows the web's own address, so the web forwards the
  user's in `X-Client-IP` together with `BFF_CLIENT_IP_SECRET` (header
  `X-BFF-Secret`), and the API believes an `X-Client-IP` only on a call that carries
  that secret. The Blueprint puts the secret in the environment group
  `bff-client-ip` (`generateValue`, so Render creates it and both services read the
  same value; it is not in the repository). If you create the services by hand, set
  the same value, 16 characters or more, on both (`openssl rand -base64 32`). Without it
  on either side the web's users share one address, as before.
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
  removes the v2 demo video and `CLAVES_CONSOLA.md` (the team's keys for the
  live console), and replaces the strings in the redactions file (kept
  outside any repository): the organizer's bucket name and account id,
  which early commits carried, and the same console keys.
- It removes every PDF from every commit. The organizer's documents were
  committed once, and the complete data dictionary carries their AWS keys as
  compressed text, which a scan by shape cannot read; a PDF that survives
  fails the export. `.gitignore` keeps new ones out.
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
| HTTP surface, model down: degraded resolution | a plain balance question is answered without the model: 293–394 turns/s and p95 23–278 ms with 8–64 clients; 251 turns/s (p95 0.85 s) with 128; 114 turns/s with 256 | same report; every 200 is checked to be `AUTO_RESOLVE` / `resolved` with no ticket (`wrong_outcome` 0) |
| HTTP surface, model down: handoff | a request that needs the model goes to a person and a ticket is written: 216–228 turns/s and p95 49–391 ms with 8–64 clients; 52–90 turns/s with 128–256 clients (p95 2.7–9.6 s) | same report; every 200 is checked to be `ESCALATE` / `llm_unavailable` with a ticket id, and the ticket is looked up on disk (`tickets_written` equals the answers in every row). The knee at 128 is the load generator and the server sharing one process (GIL) and one 128-slot accept queue on this laptop, and the linear scan of the ticket file, not a limit found in the service; a clean number needs a separate load host |
| Clients that ignore `Retry-After` | same 17.2–17.3 chats/s served, 288–640 refusals per level answered in 123 ms–2.0 s (p95), no errors | `eval/reports/LOADTEST_HTTP_NO_BACKOFF.md` (the second command of `make loadtest-http`): refusing costs almost nothing, so a hammering client does not slow the ones being served |
| Per-session rate limit | 20/min: 30 back-to-back messages gave 20 answers and 10 refusals with 429 | same report |
| LLM calls per turn | at most 1 primary response (design v3), which the client may retry or send to another provider; turns decided by the pre-LLM checks make none | 0.81 per case with Sonnet 5 on the held-out sample (`llm_calls_per_case`) |
| LLM latency and cost | Claude Sonnet 5 (effort low): 1.4 s p50 / 3.0 s p95 per case, USD 0.0016 per case (0.0034 per safe resolution); Haiku 4.5: 1.1 / 4.0 s, USD 0.0033 per case | `make eval-live`, the 548 held-out cases (2026-10-04), `eval/reports/SYSTEM_EVAL_LIVE.md`; the tools + rules prefix is prompt-cached (≈1.7K of ≈2.1K input tokens in the smoke run on prompt 3.0.0, `eval/reports/LIVE_SMOKE.md`) |
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
| Traces | one id per turn from the HTTP request to the ticket; time and outcome per stage; logs without customer data | `api/middleware.py`, `agent/observability.py`, `agent/core/orchestrator.py` | `tests/test_tracing.py` (13), `tests/test_record_failures.py` (7), `tests/test_llm_error_privacy.py` (9) | `pytest tests/test_tracing.py tests/test_record_failures.py tests/test_llm_error_privacy.py -q` |
| Bounded retries | capped attempts, jittered capped backoff, one time budget per turn, retryable errors only, no unkeyed repeat of a write | `agent/resilience.py`, `agent/llm/client.py`, `agent/tools/traces.py`, `agent/policy/escalation.py` | `tests/test_retry.py` (13), `tests/test_resilience.py` (24), `tests/test_turn_deadline.py` (7), `tests/test_call_cancellation.py` (7), `tests/test_handoff_budget.py` (7), `tests/test_handoff_lock.py` (5), `tests/test_late_handoff.py` (3), `tests/test_bounded_ops.py` (4), `tests/test_call_pool_limit.py` (1), `tests/test_local_llm.py` (11) | `pytest tests/test_retry.py tests/test_resilience.py tests/test_turn_deadline.py tests/test_call_cancellation.py tests/test_handoff_budget.py tests/test_handoff_lock.py tests/test_late_handoff.py tests/test_bounded_ops.py tests/test_call_pool_limit.py tests/test_local_llm.py -q` |
| Safe fallback | every failure ends in a fixed reply or a handoff: never an invented answer, never a half-done action | `agent/core/orchestrator.py`, `agent/policy/router.py` | `tests/test_resilience.py` | `pytest tests/test_resilience.py -q` |
| Capacity limits | body size, concurrency with a queue and 503, rate limits with 429, per-session and daily cost caps, prompt and output caps | `api/middleware.py`, `api/main.py`, `agent/llm/budget.py`, `agent/core/orchestrator.py` | `tests/test_capacity.py` (21) | `pytest tests/test_capacity.py -q`; `make loadtest-http PY=.venv/bin/python` |

All four run in the hermetic target `make test-resilience` (132 tests, about 24 s, no S3, no keys, no network beyond 127.0.0.1).

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
A model error leaves only its type, its HTTP status and a code from a fixed list in the attempt log and the logs, never its
message or body: providers quote the input they reject (`tests/test_llm_error_privacy.py`).
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
the model client and every retry draw on. It is checked before every lookup and before the one action (opening a trace),
and after each lookup: what finishes after it is not used. A model call has a limit on its whole duration, not only on each
read, and it is cancelled for real: `DeadlineTransport` (`agent/llm/client.py`) is the transport of every SDK client and of the
local provider, and enforces the limit at the network layer, on every connect, read and write, so the connection, the headers
and the body are all covered (a server that dribbles its headers a few bytes at a time is cut like one that dribbles its body):
each wait is capped to what is left (including the wait for a free connection of the pool), and a read that returns after the limit raises and closes the connection. It runs on the
turn's own thread, so a cancelled call leaves no thread and no open connection (`tests/test_call_cancellation.py` counts both, for
the local provider, anthropic, groq and together, against servers that never stop and that dribble headers). The degraded balance
answer obeys the same clock as any lookup.

**The handoff has a budget of its own** (`HANDOFF_BUDGET_SECONDS`, 3 s) that covers all of it, each step with an effective limit:

| Step | Limit | Past the budget |
|---|---|---|
| evidence for the ticket (a read) | `run_bounded`, at most **half** of what is left (the write comes next); given up at that point and left to finish in the background | the ticket goes without evidence, with a note |
| the write lock (`agent/filelock.py`, between processes) | `locked(path, timeout=)`: a `flock` tried without blocking until the budget | no write begins: nothing lands late |
| the write | never cut off half way; if it has begun and outlasts the budget, `HandoffInFlight` (an explicit state: stage `ticket`, outcome `HandoffInFlight`) | the reply is `handoff_unverified` **without a ticket id**: only a confirmed ticket is named. The write finishes on its own and its outcome is recorded when it does: `handoff_late_landed` (log with the ticket id and the trace id) or `handoff_late_failed` (log by exception type, no id: nothing dangles) |
| the read-back | `run_bounded`, and the clock is checked again after it | a ticket that cannot be confirmed in time is not claimed and not named: `handoff_unverified` without id |

Whoever is quoted the 8-character code finds the ticket by its trace id (`GET /admin/traces/{code}`, and the ticket carries `trace_id`).

**Work left running is counted and limited.** Evidence and read-backs run on a daemon thread that their caller may give up on; a
ticket write may outlast its budget. Each takes a slot of a pool until the work really ends, not until the caller gave up:
`BOUNDED_OPS_LIMIT` (16) for reads and `HANDOFF_WRITE_LIMIT` (32) for writes. With no slot the work is refused at once, never
queued: evidence is skipped, a read-back is unconfirmed, a write is refused (the customer gets the unverified message with the
code). So a stuck dependency holds at most that many workers however many turns meet it (`tests/test_bounded_ops.py`). In use and
refused, per pool, at `/admin/capacity` (`bounded_ops`) and `/metrics` (`cecilai_bounded_ops_inflight`, `_limit`, `_rejected_total`);
the late outcomes at `failures` and `cecilai_record_failures_total{kind}`.

The customer of an unverified handoff is told nothing was registered and given the 8-character code. A turn out of time can
still hand over because the turn's budget and the handoff's are separate. `HumanQueue.enqueue` is not behind the unbounded
wrapper of `serialize_policy_writers` any more: it takes the lock itself, inside the budget (the desk's writer still is wrapped).

**One budget for the request.** Once a chat holds a slot it works for at most `TURN_BUDGET_SECONDS` + `HANDOFF_BUDGET_SECONDS`
(33 s by default; `request_budget_seconds()`, shown at `/admin/capacity`). Before that come the wait for a slot
(`CHAT_QUEUE_WAIT_SECONDS`, 5 s) and the read of the body (`REQUEST_BODY_TIMEOUT_SECONDS`, 10 s), each with its own limit.
The bound is checked with a slow model and a held lock (`tests/test_handoff_budget.py`). Two things are not cancelled: a local
DuckDB read already running (short; its result is discarded if the budget passed) and a ticket write that has already begun (it
is finished rather than cut in half, and the turn does not wait for it: see the handoff table). A write with neither `idempotent=True` nor an idempotency key is attempted once, whatever the error.
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
| a lookup finishes after the budget | its result is not used; a handoff | `turn_timeout` |
| the model is down and the budget is spent, or the degraded lookup ends after it | the degraded balance is neither run nor used; a handoff | `llm_unavailable` (trace `degraded_skipped`) |
| the handoff's own budget is spent (a held lock, a `flock` held by another process, slow evidence or read-back) | nothing is written late; the customer is told nothing was registered, with the code | `…|handoff_unverified` |
| a ticket write that has begun outlasts the handoff's budget | the reply is `handoff_unverified` with the trace code and no ticket id; the write's outcome is recorded when it ends | `…|handoff_unverified`; `handoff_late_landed` / `handoff_late_failed` |
| the customer's yes arrives with the budget spent | no trace is opened; the handoff carries the proposal, so a person can approve it | `turn_timeout` (ticket with `pending_action`) |
| a provider dribbles its answer past the model's budget | cut off at the budget; the turn falls back like any model failure | `llm_unavailable` |
| a tool is down | 2 attempts, then a handoff; a `ToolError` that is an answer is not retried | `tool_failure` / `data_unavailable` |
| the tracing service fails once | the retry opens exactly one request and it is read back | `action:trace_opened` |
| the tracing service stays down | 3 attempts; the customer is never told a trace exists | `action:trace_unverified` (handoff) |
| the ticket write lands but reports failure | not filed twice | `escalate` |
| the queue cannot be written | 3 attempts; the customer is told nothing was registered and gets the 8-character code | `…|handoff_unverified` |
| our own code raises (any exception in a turn) | a handoff if a ticket can be filed and read back, otherwise the unverified message with the code; the exception text is never kept | `tool_failure` (trace rule `unexpected_failure`, `error_type`) |
| the case news cannot be read, the trace sink or the state store cannot write | the reply is still returned (a ticket already filed or a trace already opened is still told); the failure is logged by type and counted in `/admin/capacity` under `failures` (`trace_write`, `conversation_save`, `case_news`) | |
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
| demo console calls per visitor's session; for all visitors of one public account | 60/min; 300/min | `DEMO_DESK_RATE_PER_MIN`, `DEMO_DESK_CUSTOMER_RATE_PER_MIN` | 429 + `Retry-After` |
| turn time | 30 s | `TURN_BUDGET_SECONDS` | handoff |
| handoff time (evidence, lock, write, read-back) | 3 s | `HANDOFF_BUDGET_SECONDS` | unverified message with a code |
| model output per call | 4,096 tokens | `LLM_MAX_OUTPUT_TOKENS` | a cut-off answer is never acted on |
| prompt | 24,000 characters (about 6K tokens; the fixed part is about 2.1K tokens and the worst real turn is under 16,000 characters) | `LLM_MAX_PROMPT_CHARS` | the oldest history is dropped first |
| model spend per session | USD 0.25 | `LLM_SESSION_BUDGET_USD` (0 = off) | degraded mode for that session |
| model spend per UTC day | unset | `LLM_DAILY_BUDGET_USD` | degraded mode for everyone |
| connection idle | 5 s keep-alive; 20 s to drain on shutdown | uvicorn `--timeout-keep-alive`, `--timeout-graceful-shutdown` (`make serve`, the container entrypoint) | |

The rate limiters, the model budgets, the circuit breakers and the concurrency gate live in memory of one process: they
reset on restart and are not shared between replicas, so several replicas multiply every limit (a shared store such as
Redis is the next step). The limiters are bounded (idle keys are swept, at most 100,000 kept). Behind the web BFF the
address is the end user's only when the call carries `BFF_CLIENT_IP_SECRET` (or `CLIENT_IP_HEADER` names the header the BFF
sets on a private API); without it every user shares the BFF's address, which is why the per-address chat default is generous. The server has no timeout for reading request
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
  holds. Behind the BFF without `BFF_CLIENT_IP_SECRET` (or a private API with `CLIENT_IP_HEADER=X-Client-IP`), every user is
  one address: set it before lowering `CHAT_IP_RATE_PER_MIN`.
- **Handoffs with `llm_unavailable`:** read the attempts in the trace: `circuit_open` (a provider failed twice in a row and
  is skipped for 30 s), `turn_budget_exhausted` (the model was too slow for the turn) or
  `session_budget_exhausted` / `daily_budget_exhausted` (a spend cap, see `/admin/llm_budget`).
- **`handoff_unverified` or `unexpected_failure` in the trace rule:** the ticket queue or our own code failed; the customer got a code.
  The trace has `error_type` (never the message); the log line `turn failed (<type>)` carries the same trace id.
- **`trace_unverified`:** the tracing service did not confirm after 3 attempts (`trace_service` stage, `attempts`); a person
  opens the trace by hand.

## Monitoring

Every turn writes a trace (`traces.jsonl`) with the disposition, the policy rule, LLM attempts, token usage (including cached
tokens), latency and cost; every tool call writes an audit record. Both feed `GET /metrics`, a Prometheus endpoint, and
`ops/alerts.yml` turns the thresholds below into alert rules. Nothing here has run against production traffic: the thresholds
are starting points, not tuned values.

| Endpoint | Answers | Access |
|---|---|---|
| `/livez` | the process is up (no dependency is checked, so a broken warehouse gets no restart loop) | anyone |
| `/readyz` | ready or not, with a yes/no per dependency, read fresh on every probe with a 2 s limit and one in-flight probe per dependency (a hung one is refused at once, not stacked): `warehouse` (the file exists and a new read-only connection answers a query: a deleted or corrupt file is 503 at once), `state_store`, `data_dir_writable`. 503 when any fails; the reason stays in the logs | anyone; the Docker and Render health check |
| `/health` | the data as-of date, the configured providers, whether the daily model budget is spent, whether the classifier loaded | anyone |
| `/metrics` | Prometheus text (below) | `Authorization: Bearer <METRICS_TOKEN>`, or the admin key (as a bearer or `X-Admin-Key`). The token opens nothing else. 503 with neither configured |
| `/admin/ops`, `/admin/trace_log`, `/admin/drift`... | summaries and the records themselves, for a person | admin key |

**What `/metrics` exposes** (`agent/metrics.py`). Events are counted where they happen; state is read at scrape time, and a state
source that cannot be read is skipped and counted in `cecilai_scrape_errors_total{source}`, so a scrape never fails because one
does. Labels are bounded (no customer, session, ticket or message ever becomes a label; a test scans a scrape for them).

| Metric | What it tells you |
|---|---|
| `cecilai_turns_total{disposition,category}`, `cecilai_escalations_total{category}` | outcomes and escalations |
| `cecilai_turn_latency_seconds`, `cecilai_stage_latency_seconds{stage}` (`llm`, `tools`, `policy_render`), `cecilai_tool_call_seconds{tool}` | latency, whole and by stage. The stages come from the trace's own `stages` spans when the orchestrator records them; otherwise from the model steps' latency, and for a chain where every provider failed from the sum of its attempts' durations, which leaves out the backoff waits between them (nothing records those): only with the spans is an outage's whole chain model time (`tests/test_metrics.py` runs the real client, its retries and waits, through the orchestrator) |
| `cecilai_tool_calls_total{tool,outcome,error_type}` | tool calls, and why they failed (`MissingSlot`, `InvalidArgument`...) |
| `cecilai_llm_attempts_total{provider,outcome,reason}`, `cecilai_model_refusals_total`, `cecilai_llm_unavailable_turns_total`, `cecilai_degraded_turns_total` | model errors, skips, refusals and the fallback |
| `cecilai_llm_circuit_open{provider}`, `cecilai_llm_consecutive_failures{provider}`, `cecilai_llm_provider_configured{provider}` | circuit-breaker state |
| `cecilai_llm_tokens_total{provider,model,kind}`, `cecilai_llm_cost_usd_total`, `cecilai_llm_unpriced_calls_total`, `cecilai_llm_budget_*` | tokens, cost and the daily budget |
| `cecilai_rate_limit_hits_total{limiter}`, `cecilai_logins_total{result}` | limits that fired (`chat`, `login`, `auth_failures`) and login outcomes |
| `cecilai_http_requests_total{method,route,status}`, `cecilai_http_request_seconds{route}` | HTTP, by route template (never the concrete path) |
| `cecilai_data_age_hours`, `cecilai_data_freshness_slo_hours`, `cecilai_data_freshness_enforced`, `cecilai_data_as_of_timestamp_seconds` | the age of the data against its SLO |
| `cecilai_dq_failed_error_checks`, `cecilai_ingestion_failed_tables` | pipeline health, from `_dq_results` and `_ingestion_log` |
| `cecilai_retention_*` | when the last purge ran, what it dropped, what failed |
| `cecilai_handoff_unverified_total`, `cecilai_foreign_product_references_total` | the two runbook signals that are single events |

**Signals, alerts and starting thresholds.** One rule per row, in `ops/alerts.yml`; `tests/test_alerts.py` fails if this
table and the file list different alerts.

| Signal | Why | Alert | Starting threshold |
|---|---|---|---|
| `category=security` escalations | injection or enumeration attempts | `CecilaiSecurityEscalations` | more than 5 in an hour, in total (a label per customer would be unbounded: find the customer in the traces) |
| `handoff_unverified` in `policy_rule` | a ticket that did not read back: the customer was told to call | `CecilaiHandoffUnverified` | any, in 15 minutes |
| `reference_to_foreign_product` escalations | explicit attempts to read another customer's product | `CecilaiForeignProductReferences` | more than 3 in an hour |
| CLARIFY rate | drift in how well the model understands requests | `CecilaiClarifyRateShifted` | ±50% against the same day last week, over 100 turns, for 1 h |
| `MissingSlot`/`InvalidArgument` share of tool calls | the same, seen from the tools | `CecilaiToolArgumentErrorsShifted` | ±50% week over week, for 1 h |
| model refusals | provider safety classifiers declining banking requests | `CecilaiModelRefusals` | any, for 30 minutes |
| no provider answers | provider outage | `CecilaiLlmUnavailable` | any `llm_unavailable` turn for 10 minutes |
| circuit breaker open | a provider is being skipped | `CecilaiCircuitOpen` | open for 5 minutes, for a provider with a key |
| escalation rate by category | drift in data quality (`data_unavailable`) or demand | `CecilaiEscalationRateShifted` | ±50% week over week per category, over 20 escalations a day |
| p95 turn latency | UX and budget | `CecilaiTurnLatencyP95High` | above 8 s for 10 minutes |
| cost per safe resolution | unit economics | `CecilaiCostPerSafeResolutionHigh` | above USD 0.01 (about 3x the measured 0.0034); set your own |
| daily model budget | degraded mode is coming or here | `CecilaiLlmBudgetNearlyGone`, `CecilaiLlmBudgetExhausted` | 80% spent; exhausted |
| `_dq_results` failed errors, `_ingestion_log` failures | pipeline health | `CecilaiQualityChecksFailing`, `CecilaiIngestionFailed` | any, for 10 minutes |
| data older than its SLO | stale answers | `CecilaiDataStale` | age above `FRESHNESS_SLO_HOURS` for 15 minutes, only with `FRESHNESS_ENFORCE=1` (the static dataset never fires it) |
| the API stops answering | availability | `CecilaiDown`, `CecilaiServerErrors` | no scrape for 2 minutes; more than 5% 5xx for 10 minutes |
| a gauge's source is broken | the alerts on it cannot fire | `CecilaiScrapeSourceFailing` | any, for 15 minutes |
| retention stopped | expired records pile up | `CecilaiRetentionNotRunning`, `CecilaiRetentionFailing` | no purge in twice the interval; a store that could not be pruned |
| someone guessing keys | brute force on admin, metrics or operator keys | `CecilaiKeyGuessing`, `CecilaiLoginLockouts` | any address over its failed-attempt limit; more than 10 customer lockouts in 15 minutes |

**Table: point, code, test, command.**

| Point | Code | Test | Command |
|---|---|---|---|
| Prometheus metrics, latency by stage, breakers, budget, freshness | `agent/metrics.py`, the hooks in `agent/tools/audit.py`, `GET /metrics` in `api/main.py` | `tests/test_metrics.py` (a real turn is counted; state gauges; a failing source; no PII in labels; access) | `curl -H "Authorization: Bearer $METRICS_TOKEN" http://127.0.0.1:8000/metrics` |
| Liveness apart from readiness | `api/observability.py`, `/livez`, `/readyz` | `tests/test_metrics.py` (readiness names the failing dependency and leaks no reason; liveness stays up) | `curl http://127.0.0.1:8000/readyz` |
| Alert rules for the thresholds above | `ops/alerts.yml` | `tests/test_alerts.py` (well formed, only exposed metrics and labels, runbook anchors exist, same list as this table); `ops/alerts_test.yml` (promtool unit tests: 9 scenarios, including the labels and annotations each alert carries) | `make alerts-check` |
| A scraper and a dashboard, locally | `ops/prometheus.yml`, `ops/grafana/`, the `monitoring` profile | `tests/test_alerts.py` (the dashboard queries only exposed metrics); `ops/compose_e2e.sh` (Prometheus sees the API up, loaded every rule, Grafana holds the dashboard, its 20 queries are accepted) | `make monitoring-up` · `make compose-e2e` |

What is not covered: the week-over-week rules need eight days of series, so they are checked for syntax and metric names but not
unit-tested; alerts go nowhere until an Alertmanager or a webhook is added (Prometheus only evaluates them here); and the
records still contain customer data, so redaction before exporting them anywhere remains to be done (LIMITATIONS.md).

Besides the Prometheus rules, `python -m ops.alerts` checks the signals that need no history (unverified handoffs,
`llm_unavailable`, p95 latency, security escalations, exhausted model budget, data-quality errors) against a running
service through the admin endpoints, with no Prometheus: it prints one `ALERT` line each, posts them to
`ALERT_WEBHOOK_URL` if set, and exits 1 if any fired (`ALERT_BASE_URL` and `ADMIN_API_KEY` are required;
`tests/test_ops_alerts_check.py`). Nothing schedules it: run it from a cron job or CI on the cadence you want.

While the demo is live, `GET /admin/ops` (with `X-Admin-Key`) summarizes the
last 1,000 turns (`?limit=` up to 5,000): dispositions, escalations by
category, the top rules, degraded-mode turns, `llm_unavailable`,
`handoff_unverified`, traces opened, model calls, cost and unpriced turns,
p50/p95 latency, the models that answered and the day's model budget. Check
it once a day during the judging window, alongside `/readyz`.
`GET /admin/trace_log` returns the turns' trace records themselves, oldest
first (`?limit=`, default 500, up to 5,000), which is what the red-team
report is built from (`docs/red_team.md`).

## Access control

Four roles, by the credential presented: **anonymous** (nothing), **customer** (a session token from `/auth/session`),
**operator** (an operator key: the only role that may act on a ticket) and **admin** (the admin key: reads queues, traces,
audit and metrics, never acts). They are separate credentials, not a ladder: the admin key does not open `/chat`, an operator key
does not read the audit log, and a session token is neither.

The matrix below is `api/access.py` (`python -m api.access` prints it; a test keeps this table equal to it). The service
**refuses to start** if a route has no row, a row has no route, or a route declared as needing a key does not depend on it.
`tests/test_access_matrix.py` then calls every row as each of the four roles, each with only its own credential, and compares
whether the door held with the row; it fails the moment a route is added without a policy.

| Endpoint | anonymous | customer | operator | admin | Notes |
|---|---|---|---|---|---|
| `GET /` | yes | yes | yes | yes | the chat page; it holds no data |
| `GET /health` | yes | yes | yes | yes | data as-of date, configured providers, budget flag, classifier loaded |
| `GET /livez` | yes | yes | yes | yes | the process is up |
| `GET /readyz` | yes | yes | yes | yes | the warehouse, the state store and the data directory answer; yes/no only |
| `POST /auth/session` | yes | yes | yes | yes | customer id + PIN; limited per client address, locked after 5 failures |
| `DELETE /auth/session` | yes | yes | yes | yes | logout: always 204, an unknown token is a no-op |
| `GET /auth/session` | - | yes | - | - |  |
| `POST /chat` | - | yes | - | - | the session token is in the body; a dead one gets REAUTH_REQUIRED |
| `GET /chat/history` | - | yes | - | - | the live session's own conversation, as rendered; nothing after the session ends |
| `GET /case/{ticket_id}` | - | yes | - | - | only the session's own tickets |
| `POST /admin/tickets/{ticket_id}/{action}` | - | - | yes | - | claim, approve, reject, release, resolve; the actor is the key's name |
| `GET /admin/operator/me` | - | - | yes | - | the operator key's name, touching no ticket (the web BFF's login check) |
| `GET /metrics` | - | - | - | yes | admin key, or the METRICS_TOKEN a scraper holds (which opens only this) |
| `GET /admin/human_queue` | - | - | - | yes | the latest `limit` tickets (at most 200) plus every ticket still open or claimed that the file still holds, however old (the 90-day retention removes it); approved, rejected, handed-back, stale and resolved ones are cut by age |
| `GET /admin/tickets/{ticket_id}` | - | - | - | yes |  |
| `GET /admin/tickets/{ticket_id}/customer_context` | - | - | - | yes | the case's customer, read-only: products (last four digits only), latest and pending movements, the customer's other cases and trace requests; the warehouse being down is a 200 that says so |
| `GET /admin/audit_log` | - | - | - | yes |  |
| `GET /admin/trace_log` | - | - | - | yes |  |
| `GET /admin/traces/{trace_id}` | - | - | - | yes |  |
| `GET /admin/ops` | - | - | - | yes |  |
| `GET /admin/drift` | - | - | - | yes |  |
| `POST /admin/drift/snapshot` | - | - | - | yes |  |
| `GET /admin/experiments` | - | - | - | yes |  |
| `GET /admin/llm_budget` | - | - | - | yes |  |
| `GET /admin/data_quality` | - | - | - | yes |  |
| `GET /admin/capacity` | - | - | - | yes | limits in force and how often they refused |
| `GET /demo/customers` | yes | yes | yes | yes | demo only. publishes test PINs for the sandbox accounts |
| `GET /demo/scenarios` | yes | yes | yes | yes | demo only. guided scenarios, with test PINs |
| `GET /demo/data_quality` | yes | yes | yes | yes | demo only. aggregates only |
| `POST /demo/fault` | - | yes | - | - | demo only. acts on the caller's own session |
| `POST /demo/tickets` | - | yes | - | - | demo only. the session's own tickets |
| `POST /demo/traces` | - | yes | - | - | demo only. the session's own trace requests |
| `GET /admin/demo_pin/{customer_id}` | - | - | - | yes | demo only. derives any customer's test PIN |
| `GET /demo/desk/tickets` | - | yes | - | - | demo console only (DEMO_CONSOLE=1). a public sandbox account only; the session's own tickets, with their desk state |
| `GET /demo/desk/tickets/{ticket_id}` | - | yes | - | - | demo console only (DEMO_CONSOLE=1). the session's own ticket; anyone else's is the same 404 as none |
| `GET /demo/desk/tickets/{ticket_id}/customer_context` | - | yes | - | - | demo console only (DEMO_CONSOLE=1). as the admin's, with the other cases and traces of this session only |
| `POST /demo/desk/tickets/{ticket_id}/{action}` | - | yes | - | - | demo console only (DEMO_CONSOLE=1). claim, approve, reject, release, resolve on the session's own ticket; the actor is always `demo` |
| `GET /openapi.json` | yes | yes | yes | yes | with EXPOSE_API_DOCS=1. EXPOSE_API_DOCS=1 |
| `GET /docs` | yes | yes | yes | yes | with EXPOSE_API_DOCS=1. EXPOSE_API_DOCS=1 |
| `GET /docs/oauth2-redirect` | yes | yes | yes | yes | with EXPOSE_API_DOCS=1. EXPOSE_API_DOCS=1 |
| `GET /redoc` | yes | yes | yes | yes | with EXPOSE_API_DOCS=1. EXPOSE_API_DOCS=1 |

Other controls:

| Surface | Control |
|---|---|
| `/auth/session` | customer_id + test PIN (HMAC under a server secret), lockout after 5 failures per 15 min, 10 req/min per client address by default (30 in the Render Blueprint, where every guided scenario opens a session; `CLIENT_IP_HEADER` behind Render), generic error messages |
| admin, metrics and operator keys | failed attempts count per client address (10 a minute, `OPERATOR_AUTH_FAILS_PER_MIN`): past that even the right key is refused with 429 until the window passes, and each failure is an audit event (`admin_auth_failed`, `metrics_auth_failed`, `operator_auth_failed`) |
| secrets | every comparison (admin key, metrics token, PIN) goes through one constant-time function (`agent/session/secure_compare.py`). The old `hmac.compare_digest` on `str` raised on non-ASCII input, so a header or a PIN of Unicode digits was a 500; both are a 401 now (tested) |
| demo surfaces | `/demo/*`, `/admin/demo_pin` and the sandbox's published test PINs exist only with `DEMO_MODE=1` (a 404 to every role otherwise, tested for every row); `/chat` shows no policy rule outside it; `/demo/tickets` and `/demo/traces` now require a live session |
| demo console | `/demo/desk/*` exist only with `DEMO_MODE=1` and `DEMO_CONSOLE=1`, each exactly `1` (tested for every row, role and nine other values); see "The demo's console" below |
| API schema | `/openapi.json`, `/docs` and `/redoc` are off unless `EXPOSE_API_DOCS=1` |
| headers | on every answer: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cache-Control: no-store`, a `Content-Security-Policy` (`default-src 'none'` for the API; the chat page may run only its own inline script, pinned by hash) and, with `SECURITY_HSTS=1` (Render), `Strict-Transport-Security` |
| CORS | none by default: the frontend calls the API from its server. `CORS_ALLOWED_ORIGINS` lists exact origins for GET, POST and DELETE with `X-Session-Token`; a wildcard or a loose value stops the service from starting; the admin and operator keys are never an allowed header |
| model spend | `LLM_DAILY_BUDGET_USD` per UTC day, then degraded mode; plus the spend limit on the provider key |
| `/chat` | bearer session token (15 min TTL), 20 msgs/min per session, 1,000 chars max |
| customer data | ownership enforced in every tool against the session's customer; account numbers leave the tool layer as last-4 only |
| tickets / traces | carry `session_ref` (hash), never the token |
| secrets at rest | `.env` / platform secret store; `.env` is git-ignored; nothing is baked into the image |

**Table: point, code, test, command.**

| Point | Code | Test | Command |
|---|---|---|---|
| Endpoint x role matrix, applied at startup | `api/access.py` (`POLICY`, `check_app`), called at the end of `api/main.py` | `tests/test_access_matrix.py`: one test per row and role, a scratch app proving a route without a row stops the service, the guard check, key separation | `pytest tests/test_access_matrix.py` |
| Demo surfaces off by default | `require_demo` in `api/demo.py`, the gates in `api/main.py`, the entrypoint | `test_demo_surfaces_do_not_exist_without_demo_mode` (every demo row, every role), `tests/test_security.py` | `pytest tests/test_security.py` |
| Demo console: both switches, own session's tickets only, actor `demo` | `api/demo_desk.py`, `demo_console` rows and `SWITCHES` in `api/access.py`, `_visible_to` in `agent/core/orchestrator.py` | `test_the_demo_console_exists_only_with_both_switches_exactly_1`, `tests/test_demo_desk.py`, `test_on_a_public_sandbox_account_a_case_is_news_only_to_the_session_that_filed_it` | `pytest tests/test_demo_desk.py` |
| CORS and security headers | `api/security.py` | `tests/test_security.py` (headers on success, refusal and unknown routes; CSP hash equals the page's script; CORS allows only listed origins and never the keys; loose origins refused) | `curl -sI http://127.0.0.1:8000/livez` |
| Constant-time comparison | `agent/session/secure_compare.py`, used by `require_admin`, `require_metrics` and `IdentityService.login` | `test_secrets_are_compared_with_a_constant_time_function`, the non-ASCII tests | `pytest tests/test_access_matrix.py -k secret` |
| Guessing limits | `_refuse_if_guessing` in `api/main.py` | `test_guessing_an_admin_key_is_limited_and_audited`, `tests/test_operator_auth.py` | `pytest tests/test_operator_auth.py` |

### The demo's console

A visitor of the jury sandbox signs in with one click as a public sandbox customer, talks to the assistant, and then
resolves that same case as the bank, without an operator key (`api/demo_desk.py`; the web's `/demo/banco`). What holds it:

- **Off unless both switches are exactly `1`.** `DEMO_MODE=1` and `DEMO_CONSOLE=1`; anything else is the same 404 as a route
  that does not exist, for any method and any body: a guard (`ConsoleSwitch`) answers under `/demo/desk` before routing and
  before the body is parsed. `api/access.py` refuses to start if a `demo_console` row's route lacks `require_demo` or
  `require_demo_console`.
- **The credential is the customer's session.** `X-Session-Token`, live (401 otherwise), of an account in
  `DEMO_PUBLIC_CUSTOMERS`, read again on every call (403 otherwise). There is no operator session or key on this path, so
  nothing in it can reach a real one; it ends when the customer's session ends (15 minutes from sign-in).
- **Isolation in the API.** The public accounts' PINs are published, so anyone can call these routes with curl: every ticket
  is looked up among the caller's session's own (`session_ref`), reading the whole queue every time, so another visitor's
  answers the same `404 {"detail":"ticket not found"}` as one that does not exist, in the same time. The customer's context beside a case lists that session's
  other cases and traces only. On a public account the chat's news of a case, and `/case/{id}`, reach only the session that
  filed it (`_visible_to` in `agent/core/orchestrator.py`); a real customer's still follow them from session to session.
- **The real desk, as `demo`.** Claim, approve, reject, release and resolve are `TicketDesk.act`, with its versions and its
  409s; the actor is always `demo`, set by the API (`extra="forbid"`: the body cannot name one), and `OPERATOR_KEYS` refuses a
  real operator by that name. A case a real operator holds is, for any move, `409 {"detail":"another person took this case"}`. Approving a trace opens it in the sandbox's tracing
  service once (idempotent per customer and movement), with the ticket's `session_ref`.
- **Resolving.** A predefined result of the ticket's family is required (`result_code`; the family comes from the ticket's
  category, `RESULTS` in `agent/policy/desk.py`), and a message of up to 500 characters may follow it. The customer reads the
  result's fixed template (`RESOLVE_RESULT` in `agent/core/render.py`) and, after it, the message in the fixed quote
  ("Mensaje del agente: «…»"), sanitized as the console's (one line, card numbers masked, no «»).
- **Limits.** 60 calls a minute per visitor's session and 300 for all the visitors of one public account
  (`DEMO_DESK_RATE_PER_MIN`, `DEMO_DESK_CUSTOMER_RATE_PER_MIN`); in memory, per process, like the other limiters.

What it does not hold: a visitor who signs in again gets a new session and no longer sees their earlier cases; the cases a
visitor claimed and left stay claimed by `demo` in the team's console until the retention purge; the trace reset of the
"pending transfer" scenario clears that test customer's traces for every visitor, as the guided scenario already does.

## Data retention

One policy table (`rules()` in `ops/retention.py`) covers everything the service writes to disk. Every period is an environment
variable (`RETENTION_*_DAYS`; 0 keeps forever).

| Data | Where | Kept for | Mechanism |
|---|---|---|---|
| traces | `traces.jsonl` (`TRACE_LOG_PATH`) | 30 days | records older than that are dropped |
| audit log, including each purge's own event | `audit_log.jsonl` | 30 days | same |
| shadow-model log | `shadow_log.jsonl` | 30 days | same |
| escalation tickets (local queue) | `human_queue.jsonl` | 90 days here | a stand-in: in production they live in the bank's case system under its regulatory schedule |
| a ticket's operator events | `ticket_events.jsonl` | with the ticket | all of a ticket's events go together, once it has left the queue and its last event is older than 90 days (dropping them one by one would change its state and version) |
| trace requests | `trace_requests.jsonl` | 90 days | dropped by their own age |
| sessions | `sessions` in `STATE_DB_PATH` (SQLite) | 15 minutes | expired ones are deleted at each purge (and on use, and when the store is full); only a hash of the token is stored |
| conversation history | `conversations` in SQLite | 1 day | older ones deleted at each purge (and at startup) |
| case notices | `case_notifications` in SQLite | with the ticket | deleted once their ticket is gone |
| leftovers of a killed process | `*.tmp`, `*.building` next to the data | 1 day | deleted |
| warehouse | `bank.duckdb` | replaced on each full ingestion | lineage kept in `_ingestion_log` |
| reports | `quality_report.json`, `traffic_baseline.json` | one file, overwritten each run | they hold aggregates and no customer data, so nothing accumulates; the eval reports are committed artifacts, not runtime data |

**How it runs.** `python -m ops.retention` applies the policy once (`--dry-run` counts and changes nothing); `--loop` applies it
now and then every `RETENTION_INTERVAL_HOURS`. The container's entrypoint starts the loop beside the API (24 h by default, 0 =
off), so the same schedule holds on Render (a Render cron job cannot mount the web service's disk, which is why it is not one),
in the compose stack and in any Docker run. `make retention` runs it by hand.
- **Idempotent.** A second run drops nothing and does not rewrite a file. A JSONL file is rewritten only when something in it
  expired, aside and swapped in whole, and the purge holds the file's cross-process lock (`agent/filelock.py`) from its read to the
  swap while every writer takes the same lock to append, so a record already confirmed to its writer is not lost. A line it cannot read (not JSON, no
  timestamp) is kept: retention never destroys what it cannot parse. One store failing does not stop the others.
- **Audited.** Each run appends a `retention_purge` event to the audit log with the counts dropped per data type, the stores that
  failed and the policy periods (no customer data), and writes `retention_status.json`, which `/metrics` reads
  (`cecilai_retention_last_run_timestamp_seconds`...). A loop that stopped is the alert `CecilaiRetentionNotRunning`.

The records contain customer data, so PII redaction before export and encryption at rest remain to be done (LIMITATIONS.md).

**Table: point, code, test, command.**

| Point | Code | Test | Command |
|---|---|---|---|
| Policy by data type | `rules()` in `ops/retention.py`, the `RETENTION_*` settings in `.env.example` | `tests/test_retention.py`: expired records go and current ones stay for every store (parametrized), a ticket's events go together, sessions, conversations and case notices, leftovers, periods from the environment, 0 keeps forever | `python -m ops.retention --dry-run` |
| Idempotent | `_rewrite_jsonl` | `test_second_run_drops_and_rewrites_nothing`, `test_a_line_it_cannot_read_is_kept`, `test_lines_appended_while_it_rewrites_are_carried_over` | `pytest tests/test_retention.py` |
| No record lost to a purge | `agent/filelock.py` (`locked`, `append_line`), used by the trace, audit, trace-request, shadow-log and queue/desk writers and by `_rewrite_jsonl` | `tests/test_filelock.py`: a write of each of the five stores lands exactly at the swap; a writer process races 1,500 records against repeated purges; the lock excludes another process; a guard fails on a new append-mode `open` without the lock | `pytest tests/test_filelock.py` |
| The purge is itself audited | `_record` | `test_the_purge_records_itself_in_the_audit_log_and_the_status_file`, `test_one_failing_store_does_not_stop_the_rest` | `curl -H "X-Admin-Key: $ADMIN_API_KEY" "http://127.0.0.1:8000/admin/audit_log?limit=500"` |
| Scheduled | `loop()`, `ops/entrypoint.sh`, `RETENTION_INTERVAL_HOURS` | `test_the_loop_runs_every_interval_and_survives_a_failed_cycle`; `tests/test_setup.py` (the entrypoint starts it); the CI jobs `container` and `compose` check that it ran and audited itself | `make retention` · `make compose-e2e` |

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
- **Not ready (`/readyz` 503):** the response says which dependency: `warehouse` (the DuckDB file is missing or corrupt: a first
  load that failed leaves none, and the next boot loads again), `state_store` (`STATE_DB_PATH`) or `data_dir_writable` (the disk
  is full or mounted read-only). The instance is kept out of rotation and not restarted (`/livez` stays up); read the logs for
  the reason, which the public answer does not give.
- **Someone guessing keys** (`CecilaiKeyGuessing`): the audit log has an `admin_auth_failed`, `metrics_auth_failed` or
  `operator_auth_failed` event per failure with the origin. Behind Render that is the address in `CF-Connecting-IP`. Rotate the
  key if it could have leaked; a guess at line speed is already stopped by the limit.
- **Retention not running:** `docker logs` for `retention` lines, then `python -m ops.retention --dry-run` on the container;
  `retention_status.json` and the last `retention_purge` audit event say when it last ran and what failed.
- **Daily model budget exhausted** (`/health` says so): the demo keeps working
  in degraded mode until 00:00 UTC. Check `/admin/llm_budget` and the traces
  for abuse; raise `LLM_DAILY_BUDGET_USD` only if the traffic is legitimate.
