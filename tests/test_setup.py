"""Reproducible setup: locked dependencies, declared versions, a complete .env.example, the one-command stack and the CI that runs it."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ops import bootstrap_env, check_locks

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
# Read by developer tooling or by libraries (boto3 reads AWS_*), not settings a deployment chooses
NOT_SETTINGS = {"GIT_FILTER_REPO", "CLOUDFLARE_SECRETS", "PW_CHANNEL", "LLM_MODEL", "GIT_SHA"}
SCANNED = ["agent", "api", "ops", "data"]
SKIPPED_FILES = {"export_public.py", "record_demo.py"}


def settings_read_by_the_code() -> set[str]:
    found = set()
    for folder in SCANNED:
        for path in (ROOT / folder).rglob("*.py"):
            if path.name in SKIPPED_FILES:
                continue
            text = path.read_text(encoding="utf-8")
            found |= set(re.findall(r'environ(?:\.get\(|\[)\s*"([A-Z][A-Z0-9_]+)"', text))
            found |= set(re.findall(r'getenv\(\s*"([A-Z][A-Z0-9_]+)"', text))
            found |= set(re.findall(r'_JsonlSink\(\s*"([A-Z][A-Z0-9_]+)"', text))  # the log paths are read through the sink
            found |= set(re.findall(r'_wh\(\s*"([A-Z][A-Z0-9_]+)"', text))  # and retention's own path table
            found |= set(re.findall(r'_days\(\s*"([A-Z][A-Z0-9_]+)"', text))  # and its retention periods
    return found - NOT_SETTINGS


def test_every_setting_the_code_reads_is_in_env_example():
    declared = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", EXAMPLE, re.M))
    missing = settings_read_by_the_code() - declared
    assert not missing, f".env.example does not list: {sorted(missing)}"


def test_env_example_has_no_empty_path_that_would_replace_a_default():
    """Copied to .env (the documented setup), an empty `X_PATH=` would be read as the path "" instead of as unset."""
    empty = re.findall(r"^([A-Z][A-Z0-9_]*(?:_PATH|_DIR|_URI))=\s*$", EXAMPLE, re.M)
    # STATE_DB_PATH empty means "no durable state" (the code tests for a falsy value); RAW_DIR is read by compose, where empty is unset
    assert set(empty) <= {"STATE_DB_PATH", "RAW_DIR"}, empty


def test_env_example_has_no_real_secret():
    for name in ("DEMO_IDP_SECRET", "ADMIN_API_KEY", "METRICS_TOKEN", "OPERATOR_KEYS", "ANTHROPIC_API_KEY", "GROQ_API_KEY",
                 "TOGETHER_API_KEY", "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID"):
        assert re.search(rf"^{name}=$", EXAMPLE, re.M), f"{name} must be empty in the example"


def test_the_lock_files_match_the_pins_they_were_compiled_from():
    assert check_locks.problems() == []


def test_the_lock_check_catches_a_drifted_pin_and_a_missing_hash(tmp_path):
    (tmp_path / "requirements.in").write_text("duckdb==1.5.5\nfastapi==0.141.1\n")
    (tmp_path / "requirements-tracking.in").write_text("mlflow==3.16.1\n")
    lock = "duckdb==1.5.5 \\\n    --hash=sha256:aa\nfastapi==0.100.0 \\\n    --hash=sha256:bb\nnaked==1.0\n"
    (tmp_path / "requirements.txt").write_text(lock)
    (tmp_path / "requirements-tracking.txt").write_text(lock + "mlflow==3.16.1 \\\n    --hash=sha256:cc\n")
    found = " | ".join(check_locks.problems(tmp_path))
    assert "fastapi is 0.100.0, requirements.in pins 0.141.1" in found and "naked has no hash" in found


def test_the_runtime_versions_are_declared_once_and_agree():
    python = (ROOT / ".python-version").read_text().strip()
    node = (ROOT / ".node-version").read_text().strip()
    package = json.loads((ROOT / "web" / "package.json").read_text())
    assert f"FROM python:{python}-slim" in (ROOT / "ops" / "Dockerfile").read_text()
    assert f"FROM node:{node}-slim" in (ROOT / "ops" / "Dockerfile.web").read_text()
    assert package["engines"]["node"] == f">={node} <{int(node) + 1}"
    pnpm = package["packageManager"].split("@")[1]
    assert f"pnpm@{pnpm}" in (ROOT / "ops" / "Dockerfile.web").read_text() and pnpm in (ROOT / "Makefile").read_text()
    assert f"--python-version {python}" in (ROOT / "Makefile").read_text()


def test_bootstrap_writes_an_env_with_fresh_secrets_and_leaves_an_existing_one(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE)
    assert bootstrap_env.main(["--root", str(tmp_path)]) == 0
    env = dict(re.findall(r"^([A-Z][A-Z0-9_]+)=(.*)$", (tmp_path / ".env").read_text(), re.M))
    assert (tmp_path / ".env").stat().st_mode & 0o077 == 0  # only its owner reads it
    secrets = [env[k] for k in ("DEMO_IDP_SECRET", "ADMIN_API_KEY", "METRICS_TOKEN")]
    assert all(len(s) >= 32 for s in secrets) and len(set(secrets)) == 3
    assert env["OPERATOR_KEYS"].startswith("operator1=") and len(env["OPERATOR_KEYS"].split("=", 1)[1]) >= 24
    assert env["DEMO_MODE"] == "1" and "tests/fixtures/raw" in env["INGEST_ARGS"]
    assert env["ANTHROPIC_API_KEY"] == "" and env["AWS_SECRET_ACCESS_KEY"] == ""  # nothing that needs an account
    # it is a valid configuration for the service: the operator key passes OPERATOR_KEYS' own checks
    from agent.session.operators import OperatorDirectory

    assert OperatorDirectory.parse(env["OPERATOR_KEYS"]).enabled
    first = (tmp_path / ".env").read_text()
    assert bootstrap_env.main(["--root", str(tmp_path)]) == 0 and (tmp_path / ".env").read_text() == first
    assert bootstrap_env.main(["--root", str(tmp_path), "--force"]) == 0 and (tmp_path / ".env").read_text() != first


def test_bootstrap_can_write_a_throwaway_file_with_free_ports_and_leaves_the_env_alone(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE)
    (tmp_path / ".env").write_text("KEEP=me\n")
    out = tmp_path / "e2e.env"
    assert bootstrap_env.main(["--root", str(tmp_path), "--out", str(out), "--free-ports"]) == 0
    assert (tmp_path / ".env").read_text() == "KEEP=me\n"
    env = dict(re.findall(r"^([A-Z][A-Z0-9_]+)=(.*)$", out.read_text(), re.M))
    ports = [int(env[k]) for k in bootstrap_env.PORTS]
    assert len(set(ports)) == len(ports) and all(p > 1024 for p in ports) and 8000 not in ports


def test_bootstrap_refuses_an_example_that_lost_a_setting_it_fills():
    with pytest.raises(ValueError, match="does not declare"):
        bootstrap_env.render("DEMO_MODE=0\n", {"DEMO_MODE": "1", "METRICS_TOKEN": "x"})


COMPOSE = yaml.safe_load((ROOT / "ops" / "docker-compose.yml").read_text())


def test_the_compose_stack_is_api_and_web_with_optional_monitoring_and_local_model_profiles():
    services = COMPOSE["services"]
    assert set(services) == {"api", "web", "prometheus", "grafana", "ollama", "ollama-pull"}
    assert {n for n, sv in services.items() if "profiles" not in sv} == {"api", "web"}  # the default stack is just these two
    assert services["prometheus"]["profiles"] == services["grafana"]["profiles"] == ["monitoring"]
    assert services["ollama"]["profiles"] == services["ollama-pull"]["profiles"] == ["llm-local"]
    assert services["web"]["depends_on"]["api"]["condition"] == "service_healthy"  # the web waits for a ready API
    assert services["ollama-pull"]["depends_on"]["ollama"]["condition"] == "service_healthy"
    assert "readyz" in " ".join(services["api"]["healthcheck"]["test"]) and services["ollama"]["healthcheck"]["test"][-1] == "list"
    assert services["web"]["environment"][0] == "AGENT_API_URL=http://api:8000"
    assert "ollama:/root/.ollama" in services["ollama"]["volumes"]  # models survive a restart
    assert COMPOSE["name"].startswith("cecilai-local")  # its volumes must not collide with an older setup's
    for name, service in services.items():
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:"), f"{name} publishes {port} beyond this machine"


def test_the_compose_defaults_boot_on_the_fixture_with_no_bucket_and_no_model_key():
    env = "\n".join(COMPOSE["services"]["api"]["environment"])
    assert "--source local --raw-dir /app/tests/fixtures/raw" in env
    assert "STATE_DB_PATH=/app/data/warehouse/state.sqlite" in env
    for secret in ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY", "AWS_SECRET_ACCESS_KEY", "DATASET_BUCKET",
                   "DEMO_IDP_SECRET", "ADMIN_API_KEY", "METRICS_TOKEN"):
        assert f"{secret}=${{{secret}:-}}" in env  # empty unless .env sets it: no default secret, no account needed


def test_the_local_dataset_and_the_local_model_are_reachable_without_any_cloud_service():
    api = COMPOSE["services"]["api"]
    assert "${RAW_DIR:-raw}:/app/data/raw:ro" in api["volumes"]  # your CSVs, read-only; unset it is an empty named volume
    assert "host.docker.internal:host-gateway" in api["extra_hosts"]  # a host Ollama, on Linux too
    env = "\n".join(api["environment"])
    assert "LOCAL_LLM_BASE_URL=${LOCAL_LLM_BASE_URL:-http://ollama:11434/v1}" in env
    assert "LOCAL_LLM_MODEL=${LOCAL_LLM_MODEL:-gpt-oss:20b}" in env
    assert "LLM_PROVIDERS=${LLM_PROVIDERS:-anthropic,groq,together}" in env  # no `local` unless asked: the default is degraded mode
    assert "ollama pull" in " ".join(COMPOSE["services"]["ollama-pull"]["command"])
    makefile = (ROOT / "Makefile").read_text()
    assert "LLM_PROVIDERS=local LOCAL_LLM_BASE_URL=http://ollama:11434/v1" in makefile
    assert "LLM_PROVIDERS=local LOCAL_LLM_BASE_URL=http://host.docker.internal:11434/v1" in makefile


def test_grafana_and_prometheus_send_nothing_off_the_machine():
    grafana = "\n".join(COMPOSE["services"]["grafana"]["environment"])
    for flag in ("GF_ANALYTICS_REPORTING_ENABLED=false", "GF_ANALYTICS_CHECK_FOR_UPDATES=false", "GF_AUTH_ANONYMOUS_ENABLED=false"):
        assert flag in grafana
    datasource = yaml.safe_load((ROOT / "ops" / "grafana" / "provisioning" / "datasources" / "prometheus.yml").read_text())
    assert datasource["datasources"][0]["url"] == "http://prometheus:9090"
    prom = yaml.safe_load((ROOT / "ops" / "prometheus.yml").read_text())
    assert prom["scrape_configs"][0]["static_configs"][0]["targets"] == ["api:8000"] and "remote_write" not in prom


def test_both_images_run_unprivileged():
    assert "useradd" in (ROOT / "ops" / "Dockerfile").read_text() and "setpriv" in (ROOT / "ops" / "entrypoint.sh").read_text()
    web = (ROOT / "ops" / "Dockerfile.web").read_text()
    assert re.search(r"^USER web$", web, re.M) and "--frozen-lockfile" in web and "AS runtime" in web


def test_the_entrypoint_schedules_retention_and_only_the_sandbox_publishes_test_credentials():
    entry = (ROOT / "ops" / "entrypoint.sh").read_text()
    assert "python -m ops.retention --loop" in entry and "RETENTION_INTERVAL_HOURS" in entry
    assert '[ "$DEMO_MODE" = "1" ]' in entry.split("ops.demo_customers")[0].rsplit("if", 1)[1]


WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())


def test_the_ci_runs_every_layer_in_parallel_jobs_with_a_time_limit():
    jobs = WORKFLOW["jobs"]
    assert {"python", "web", "alerts", "container", "web-image", "compose"} <= set(jobs)
    assert all("needs" not in job for job in jobs.values())  # parallel: none waits for another
    assert all(job.get("timeout-minutes") for job in jobs.values())
    runs = {name: " ".join(str(s.get("run", "")) for s in job["steps"]) for name, job in jobs.items()}
    assert "make lock-check" in runs["python"] and "make test" in runs["python"] and "make gate" in runs["python"]
    assert "pnpm install --frozen-lockfile" in runs["web"] and "pnpm typecheck" in runs["web"] and "pnpm build" in runs["web"]
    assert "pnpm test:all" in runs["web"]  # node:test, vitest on the DOM and the HTTP tests against the production build
    assert "make alerts-check" in runs["alerts"] and "make compose-e2e" in runs["compose"]
    assert "ops/container_smoke.py" in runs["container"]


def test_the_ci_python_job_covers_the_data_ml_validation_and_the_resilience_tests_and_checks_the_tree_stays_clean():
    """Neither has a step of its own because `make gate` runs the one and `make test` (the whole tests/ folder) the other."""
    makefile = (ROOT / "Makefile").read_text()
    gate = re.search(r"^gate:.*\n((?:\t.*\n)+)", makefile, re.M).group(1)
    assert "$(MAKE) validate-data-ml" in gate
    resilience = re.search(r"^test-resilience:.*\n\t\$\(PY\) -m pytest (.*) -q\n", makefile, re.M).group(1).split()
    assert resilience and all((ROOT / f).exists() and f.startswith("tests/") for f in resilience)
    assert re.search(r"^test:.*\n\t\$\(PY\) -m pytest tests/ -q\n", makefile, re.M)  # the whole folder, so the files above run
    steps = WORKFLOW["jobs"]["python"]["steps"]
    runs = [str(step.get("run", "")) for step in steps]
    order = {key: next(i for i, run in enumerate(runs) if key in run) for key in ("make test", "make gate", "git status --porcelain", "evaluate_intent_classifier")}
    assert order["make test"] < order["make gate"] < order["git status --porcelain"] < order["evaluate_intent_classifier"]


def test_the_ci_installs_from_the_hash_checked_lock():
    steps = " ".join(str(s.get("run", "")) for s in WORKFLOW["jobs"]["python"]["steps"])
    assert "pip install --require-hashes -r requirements-tracking.txt" in steps


@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
def test_optional_ci_targets_run_when_defined_skip_when_missing_and_fail_when_they_fail(tmp_path):
    (tmp_path / "Makefile").write_text("good:\n\t@echo ran-good\nbad:\n\t@exit 3\n")
    script = str(ROOT / "ops" / "ci_optional.sh")

    def run(*targets):
        return subprocess.run(["sh", script, *targets], cwd=tmp_path, capture_output=True, text=True)

    ok = run("absent", "good")
    assert ok.returncode == 0 and "skipped: this checkout has no 'make absent'" in ok.stdout and "ran-good" in ok.stdout
    assert run("bad").returncode != 0


# Settings the image or the compose file fixes on purpose, so a value in .env must not reach the container
FIXED_IN_THE_CONTAINER = {
    "DUCKDB_PATH": "the image puts the warehouse on its volume",
    "DQ_REPORT_PATH": "next to the warehouse, on the volume",
    "RAW_DATA_DIR": "the image's data directory (RAW_DIR mounts your CSVs there)",
    "RETENTION_STATUS_PATH": "on the volume, where /metrics reads it",
}


# Read by the web service (checked below against what the web's code reads), by compose itself (published ports, the Grafana
# login, the dataset mount), not by the API
WEB_SETTINGS = {"WEB_PUBLIC_ORIGIN", "TRUSTED_CLIENT_IP_HEADER", "OPERATOR_IDLE_SECONDS", "UI_GALLERY"}
COMPOSE_ONLY = {"API_PORT", "WEB_PORT", "PROMETHEUS_PORT", "GRAFANA_PORT", "OLLAMA_PORT", "GRAFANA_ADMIN_PASSWORD", "RAW_DIR"} | WEB_SETTINGS


def test_the_compose_passes_every_setting_the_code_reads_and_every_one_env_example_lists():
    """A setting in .env that never reached the container is a setting that silently does nothing."""
    passed = {entry.split("=", 1)[0] for entry in COMPOSE["services"]["api"]["environment"]}
    declared = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", EXAMPLE, re.M))
    wanted = (settings_read_by_the_code() | declared) - COMPOSE_ONLY - set(FIXED_IN_THE_CONTAINER)
    missing = wanted - passed
    assert not missing, f"ops/docker-compose.yml does not pass to the api: {sorted(missing)}"
    assert set(FIXED_IN_THE_CONTAINER) <= settings_read_by_the_code()  # an exclusion for a setting that is gone is stale
    assert COMPOSE_ONLY <= declared


# What the image or the runtime fixes for the web, so nothing has to pass it: the image sets NODE_ENV and PORT, HOST has a default
FIXED_FOR_THE_WEB = {"NODE_ENV", "PORT", "HOST"}


def settings_read_by_the_web() -> set[str]:
    found = set()
    for path in [ROOT / "web" / "serve.mjs", *(ROOT / "web" / "src").rglob("*.ts*")]:
        if ".test." in path.name:
            continue
        found |= set(re.findall(r"\benv\.([A-Z][A-Z0-9_]+)", path.read_text(encoding="utf-8")))
    return found - FIXED_FOR_THE_WEB


def test_the_compose_passes_every_setting_the_web_reads_and_a_working_origin_for_the_operator_console():
    """The web image runs in production, where the console refuses every form post without WEB_PUBLIC_ORIGIN: a setting the web
    reads and the compose does not pass is one that silently does nothing (or, for the origin, a console that cannot log in)."""
    passed = {entry.split("=", 1)[0] for entry in COMPOSE["services"]["web"]["environment"]}
    missing = settings_read_by_the_web() - passed
    assert not missing, f"ops/docker-compose.yml does not pass to the web: {sorted(missing)}"
    assert settings_read_by_the_web() >= WEB_SETTINGS  # a name that is no longer read is stale here and in .env.example
    declared = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", EXAMPLE, re.M))
    assert WEB_SETTINGS <= declared
    origin = next(e for e in COMPOSE["services"]["web"]["environment"] if e.startswith("WEB_PUBLIC_ORIGIN="))
    assert origin == "WEB_PUBLIC_ORIGIN=${WEB_PUBLIC_ORIGIN:-http://127.0.0.1:${WEB_PORT:-3000}}"  # follows the published port
    assert re.search(r"^WEB_PUBLIC_ORIGIN=$", EXAMPLE, re.M) and re.search(r"^UI_GALLERY=0$", EXAMPLE, re.M)  # gallery off by default


# --- make env-check / env-fill (ops/env_check.py) -----------------------------------------------------------------------------

from ops import env_check  # noqa: E402

OLD_ENV = "DEMO_IDP_SECRET=old-secret-value\nADMIN_API_KEY=old-admin-value\nINGEST_ARGS=--profile serving --sample-customers 5000\nAPI_PORT=8100\n"


def test_env_check_lists_the_missing_names_and_warns_about_s3_and_prints_no_value():
    lines = "\n".join(env_check.report(EXAMPLE, OLD_ENV))
    for name in ("METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD", "WEB_PUBLIC_ORIGIN", "UI_GALLERY"):
        assert f"  {name}" in lines
    assert "  DEMO_IDP_SECRET" not in lines and "  API_PORT" not in lines  # present: not missing
    assert "INGEST_ARGS has no `--source local`" in lines
    assert "old-secret-value" not in lines and "old-admin-value" not in lines and "8100" not in lines


def test_env_check_is_quiet_on_an_env_made_by_make_env_and_flags_only_a_secret_left_empty():
    made = bootstrap_env.render(EXAMPLE, bootstrap_env.local_values())
    assert env_check.report(EXAMPLE, made) == []
    assert not env_check.ingests_from_s3(made)
    blank = made.replace(re.search(r"^METRICS_TOKEN=.*$", made, re.M).group(0), "METRICS_TOKEN=")
    assert env_check.empty_secrets(blank) == ["METRICS_TOKEN"]


def test_env_check_ingest_args_reading():
    assert env_check.ingests_from_s3("INGEST_ARGS=--profile serving --since 2025-06-17\n")
    assert not env_check.ingests_from_s3("INGEST_ARGS=--profile serving --source local --raw-dir /x\n")
    assert not env_check.ingests_from_s3("INGEST_ARGS=--source=local\n")
    assert not env_check.ingests_from_s3("API_PORT=1\n")  # unset: the compose default is the fixture


def test_env_fill_appends_only_the_missing_with_generated_secrets_and_changes_nothing_else(tmp_path, capsys):
    (tmp_path / ".env.example").write_text(EXAMPLE)
    env = tmp_path / ".env"
    env.write_text(OLD_ENV.rstrip("\n"))  # no trailing newline: the fill must not glue its first line to the last one
    env.chmod(0o600)
    assert env_check.main(["--env", str(env), "--example", str(tmp_path / ".env.example"), "--fill"]) == 0
    out = capsys.readouterr().out
    text = env.read_text()
    assert text.startswith(OLD_ENV.rstrip("\n") + "\n")  # what was there is untouched, byte for byte
    assert env.stat().st_mode & 0o077 == 0
    filled = env_check.parse(text)
    assert env_check.missing(EXAMPLE, text) == []
    assert len(filled["METRICS_TOKEN"]) >= 32 and len(filled["GRAFANA_ADMIN_PASSWORD"]) >= 32
    assert filled["DEMO_IDP_SECRET"] == "old-secret-value" and filled["API_PORT"] == "8100" and filled["WEB_PORT"] == "3000"
    assert filled["INGEST_ARGS"].startswith("--profile serving --sample-customers 5000")  # an existing value is never replaced
    for value in (filled["METRICS_TOKEN"], filled["GRAFANA_ADMIN_PASSWORD"], "old-secret-value"):
        assert value not in out  # only names are printed
    assert "METRICS_TOKEN" in out
    again = env.read_text()
    assert env_check.main(["--env", str(env), "--example", str(tmp_path / ".env.example"), "--fill"]) == 0 and env.read_text() == again


def test_env_check_never_fails_the_make_up_unless_asked_and_a_missing_env_is_not_an_error(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE)
    (tmp_path / ".env").write_text(OLD_ENV)
    args = ["--env", str(tmp_path / ".env"), "--example", str(tmp_path / ".env.example")]
    assert env_check.main(args) == 0 and env_check.main([*args, "--strict"]) == 1
    assert env_check.main(["--env", str(tmp_path / "none"), "--example", str(tmp_path / ".env.example")]) == 0


def test_make_up_runs_the_env_check_as_a_warning_and_evidence_is_an_explicit_step():
    makefile = (ROOT / "Makefile").read_text()
    for target in ("up", "monitoring-up", "up-llm-local", "up-llm-host", "up-dataset"):
        assert re.search(rf"^{target}: env env-check\b", makefile, re.M), target
    assert "$(PY) -m ops.env_check --fill" in makefile
    # the gate and the CI verify without writing; only `make evidence` regenerates the versioned files
    assert re.search(r"^validate-data-ml:.*\n\t\$\(PY\) -m eval.validate_data_ml\n", makefile, re.M)
    assert re.search(r"^evidence:.*\n\t\$\(PY\) -m eval.validate_data_ml --out-dir docs/evidence\n", makefile, re.M)
