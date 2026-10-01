"""Reproducible setup: locked dependencies, declared versions, a complete .env.example, the one-command stack and the CI that runs it."""
from __future__ import annotations

import json
import os
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
NOT_SETTINGS = {"GIT_FILTER_REPO", "CLOUDFLARE_SECRETS", "PW_CHANNEL", "LLM_MODEL", "GIT_SHA", "PYTHON_DOTENV_DISABLED"}  # the last: python-dotenv's own switch, which the probe sets
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


def test_the_ci_runs_on_main_pushes_and_on_every_pull_request_and_only_cancels_pull_request_runs():
    triggers = WORKFLOW.get("on", WORKFLOW.get(True))  # PyYAML reads the bare key `on` as True
    assert triggers["push"] == {"branches": ["main"]}  # a branch with an open PR runs once (pull_request), not twice
    assert not triggers["pull_request"]  # no branch filter: any base branch
    assert "workflow_dispatch" in triggers  # by hand, on a branch without a PR
    # a second merge must not cancel the run that verifies the first one on main
    assert _compact(WORKFLOW["concurrency"]["cancel-in-progress"]) == "${{github.event_name=='pull_request'}}"


def _compact(expression):
    return "".join(str(expression).split())


def test_the_ci_groups_a_pull_request_by_its_number_and_gives_every_other_run_a_group_of_its_own():
    # a group keeps one active and one pending run and a third cancels the pending one, so a shared group for pushes to
    # main (or a manual run on main) would leave a commit unverified
    group = _compact(WORKFLOW["concurrency"]["group"])
    assert group.startswith("ci-${{") and group.endswith("}}")
    condition, _, otherwise = group[len("ci-${{"):-2].partition("||")
    assert condition == "github.event_name=='pull_request'&&format('pr-{0}',github.event.pull_request.number)"
    assert otherwise == "github.run_id"  # not github.ref: main's pushes and dispatches would share one group


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


def test_the_ci_python_job_ends_with_the_clean_tree_check_and_every_step_that_writes_writes_elsewhere():
    """A step that rewrites a versioned file must not run after the check that says none did: the evaluation of the classifier
    (it rewrites its report and its model) writes to a temporary directory, and the check is the last step."""
    runs = [str(step.get("run", "")) for step in WORKFLOW["jobs"]["python"]["steps"]]
    order = {key: next(i for i, run in enumerate(runs) if key in run) for key in ("make test", "make gate", "evaluate_intent_classifier")}
    assert order["make test"] < order["make gate"] and order["evaluate_intent_classifier"] < len(runs) - 1
    assert "git status --porcelain" in runs[-1]  # last: whatever ran before it left the tree as it found it
    for run in runs:
        for line in run.splitlines():
            if "eval.evaluate_intent_classifier" in line:
                assert "--out-dir" in line, line
            assert not re.search(r"\bmake (evidence|eval|eval-adversarial|eval-failures|train-eval|workload|analysis|ingest)\b", line), line


def test_the_classifier_evaluation_can_write_its_outputs_elsewhere_and_leaves_the_versioned_ones_alone(tmp_path, monkeypatch):
    from eval import evaluate_intent_classifier as eic

    watched = [eic.MODEL_OUT, eic.JSON_OUT, eic.META_OUT, eic.REPORT_JSON, eic.REPORT_MD]
    before = [p.read_bytes() for p in watched]
    monkeypatch.setattr(eic, "track", lambda report: None)
    for name in ("MODEL_OUT", "JSON_OUT", "META_OUT", "REPORT_JSON", "REPORT_MD"):  # main() repoints the module's paths: put them back afterwards
        monkeypatch.setattr(eic, name, getattr(eic, name))
    eic.main(["--out-dir", str(tmp_path)])
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(p.name for p in watched)
    assert [p.read_bytes() for p in watched] == before  # the committed model and reports are untouched
    report = json.loads((tmp_path / "intent_classifier.json").read_text(encoding="utf-8"))
    assert report["test"]["learned"]["accuracy"]["rate"] > report["test"]["baseline_keywords"]["accuracy"]["rate"]


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
    # follows the published port, by IP and by name
    assert origin == "WEB_PUBLIC_ORIGIN=${WEB_PUBLIC_ORIGIN:-http://127.0.0.1:${WEB_PORT:-3000},http://localhost:${WEB_PORT:-3000}}"
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


def test_the_web_server_does_not_send_no_referrer_because_a_browser_then_posts_origin_null_and_the_console_login_is_refused():
    """Found in Chromium: under Referrer-Policy: no-referrer a form post carries `Origin: null` and no Referer, and the operator
    forms' origin check (web/src/server/origin-check.ts, which rightly refuses `null`) turned every login into a 403."""
    serve = (ROOT / "web" / "serve.mjs").read_text(encoding="utf-8")
    assert "'referrer-policy': 'same-origin'" in serve and "'referrer-policy': 'no-referrer'" not in serve


# --- .env syntax as Compose reads it (dotenv: export, spaces around =, quotes, comments) -----------------------------------------

DOTENV = """\
# a comment, then a blank line

export ADMIN_API_KEY=exported-value
METRICS_TOKEN = spaced-value
GRAFANA_ADMIN_PASSWORD="double # quoted"
DEMO_IDP_SECRET='single quoted' # trailing comment
OPERATOR_KEYS=operator1=abc#not-a-comment
  export   SESSION_TTL_SECONDS  =  60  # indented, exported, spaced
"""


def test_env_check_parses_the_dotenv_syntax_compose_accepts():
    got = env_check.parse(DOTENV)
    assert got["ADMIN_API_KEY"] == "exported-value" and got["METRICS_TOKEN"] == "spaced-value"
    assert got["GRAFANA_ADMIN_PASSWORD"] == "double # quoted" and got["DEMO_IDP_SECRET"] == "single quoted"
    assert got["OPERATOR_KEYS"] == "operator1=abc#not-a-comment"  # a # with no space before it is part of the value
    assert got["SESSION_TTL_SECONDS"] == "60"
    assert "a" not in got and len(got) == 6


def test_env_check_does_not_call_missing_what_export_or_spaces_declare_and_env_fill_never_doubles_a_key(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE)
    env = tmp_path / ".env"
    env.write_text(DOTENV)
    listed = "\n".join(env_check.report(EXAMPLE, DOTENV))
    for name in ("ADMIN_API_KEY", "METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD", "DEMO_IDP_SECRET", "OPERATOR_KEYS", "SESSION_TTL_SECONDS"):
        assert f"  {name}\n" not in listed + "\n", name
        assert name not in env_check.missing(EXAMPLE, DOTENV)
    assert env_check.main(["--env", str(env), "--example", str(tmp_path / ".env.example"), "--fill"]) == 0
    text = env.read_text()
    assert text.startswith(DOTENV)  # what was there is untouched
    for name in ("ADMIN_API_KEY", "METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD", "DEMO_IDP_SECRET", "OPERATOR_KEYS", "SESSION_TTL_SECONDS"):
        assert len(re.findall(rf"^\s*(?:export\s+)?{name}\s*=", text, re.M)) == 1, name  # a second assignment would override the first
    assert env_check.parse(text)["ADMIN_API_KEY"] == "exported-value" and env_check.parse(text)["METRICS_TOKEN"] == "spaced-value"


def test_env_fill_keeps_every_existing_value_whatever_the_syntax(tmp_path):
    (tmp_path / ".env.example").write_text(EXAMPLE)
    env = tmp_path / ".env"
    env.write_text(DOTENV + "LOG_LEVEL=DEBUG\n")
    before = env_check.parse(env.read_text())
    assert env_check.main(["--env", str(env), "--example", str(tmp_path / ".env.example"), "--fill"]) == 0
    after = env_check.parse(env.read_text())
    assert {k: after[k] for k in before} == before
    assert env_check.main(["--env", str(env), "--example", str(tmp_path / ".env.example"), "--fill"]) == 0
    assert env_check.parse(env.read_text()) == after  # and a second fill adds nothing


def test_env_fill_writes_a_value_that_dotenv_reads_back_as_written():
    for value in ("plain", "--profile serving --source local", "has # hash", "it's", 'say "hi" # x', " edge", "a\nb", "$HOME", ""):
        assert env_check.parse(f"K={env_check._written(value)}\n") == {"K": value}, value


def test_env_check_reads_ingest_args_the_way_dotenv_and_argparse_do():
    read = lambda value: env_check.ingests_from_s3(f"INGEST_ARGS={value}\n")
    assert read("--profile serving # --source local")  # the comment is dropped: no source, so S3
    assert not read("--profile serving --source local # the fixture")
    assert read("--source local --source s3")  # the last one wins
    assert not read("--source s3 --source=local")
    assert read('--profile serving --source local --source=s3')
    assert not read('"--profile serving --source local"')  # quoted as a whole: still the same arguments
    assert not env_check.ingests_from_s3("export INGEST_ARGS = --source local\n")
    assert env_check.ingests_from_s3("export INGEST_ARGS = --profile serving\n")
    assert not env_check.ingests_from_s3("INGEST_ARGS=\n")  # empty: compose falls back to its fixture default


# --- dotenv, checked against Compose itself (skipped without Docker) --------------------------------------------------------------

needs_compose = pytest.mark.skipif(shutil.which("docker") is None or subprocess.run(["docker", "compose", "version"], capture_output=True).returncode != 0,
                                   reason="needs docker compose")


def compose_reads(env_text: str, names: list[str]) -> dict[str, str]:
    """What `docker compose --env-file` makes of each name: one service whose environment is `${NAME-}` for each."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "env").write_text(env_text, encoding="utf-8")
        compose = {"services": {"probe": {"image": "probe", "environment": {n: "${%s-}" % n for n in names}}}}
        (Path(tmp) / "c.yml").write_text(json.dumps(compose), encoding="utf-8")
        done = subprocess.run(["docker", "compose", "-f", str(Path(tmp) / "c.yml"), "--env-file", str(Path(tmp) / "env"), "config", "--format", "json"],
                              capture_output=True, text=True, env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "")})
        assert done.returncode == 0, done.stderr
        return {k: v.replace("$$", "$") for k, v in json.loads(done.stdout)["services"]["probe"]["environment"].items()}  # config prints $ as $$


@needs_compose
def test_env_fill_copies_an_example_default_so_that_compose_resolves_it_as_it_resolves_the_example(tmp_path):
    example = ("PROBE=${SYNTHETIC_UNSET:-fallback}\nQUOTED=\"it's $$SYNTHETIC_UNSET\"\nSINGLE='no $interpolation here'\n"
               "PLAIN=plain # with a comment\nGENERATED_SECRET=\nMETRICS_TOKEN=\n")
    text, names = env_check.fill(example, "")
    assert set(names) == {"PROBE", "QUOTED", "SINGLE", "PLAIN", "GENERATED_SECRET", "METRICS_TOKEN"}
    wanted = ["PROBE", "QUOTED", "SINGLE", "PLAIN"]
    assert compose_reads(text, wanted) == compose_reads(example, wanted) == {
        "PROBE": "fallback", "QUOTED": "it's $SYNTHETIC_UNSET", "SINGLE": "no $interpolation here", "PLAIN": "plain"}
    assert "PROBE=${SYNTHETIC_UNSET:-fallback}\n" in text and "QUOTED=\"it's $$SYNTHETIC_UNSET\"\n" in text  # copied as written
    assert len(env_check.parse(text)["METRICS_TOKEN"]) >= 32  # a generated secret is serialized by us, not copied


VALUES = ["plain", "it's", "has # hash", 'say "hi"', "back\\slash", "$HOME", "a b  c", " edge", "x'y\"z"]


@needs_compose
def test_env_check_reads_quoted_values_as_compose_does_including_the_escaped_single_quote():
    lines = {"A": r"'it\'s'", "B": r"'back\\slash'", "C": r"'a\nb'", "D": r'"q\"r"', "E": r"'x\'y' # comment", "F": "'plain'   # c", "G": '"it\'s"'}
    text = "".join(f"{k}={v}\n" for k, v in lines.items())
    assert env_check.parse(text) == compose_reads(text, list(lines))


@needs_compose
def test_a_value_env_fill_serializes_is_read_back_by_compose_and_by_env_check_as_it_was():
    text = "".join(f"K{i}={env_check._written(v)}\n" for i, v in enumerate(VALUES))
    names = [f"K{i}" for i in range(len(VALUES))]
    assert compose_reads(text, names) == {n: v for n, v in zip(names, VALUES)}
    assert env_check.parse(text) == {n: v for n, v in zip(names, VALUES)}


def test_env_fill_copies_a_multi_line_quoted_default_whole():
    example = 'BANNER="first\nsecond # kept"\nAFTER=1\n'
    text, names = env_check.fill(example, "")
    assert names == ["BANNER", "AFTER"] and 'BANNER="first\nsecond # kept"\nAFTER=1\n' in text
    assert env_check.parse(text) == {"BANNER": "first\nsecond # kept", "AFTER": "1"}
