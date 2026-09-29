"""The end-to-end check must never touch the stack a person runs with `make up` (project cecilai-local), and no make target
may delete that stack's volumes unless asked to by name."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
E2E = (ROOT / "ops" / "compose_e2e.sh").read_text(encoding="utf-8")
CODE = "\n".join(line for line in E2E.splitlines() if not line.lstrip().startswith("#"))
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
USER_PROJECT = "cecilai-local"


def dry_run() -> dict[str, str]:
    assert "COMPOSE_E2E_DRY_RUN" in E2E, "the script needs a dry-run mode that prints its isolation and starts nothing"
    out = subprocess.run(["sh", str(ROOT / "ops" / "compose_e2e.sh")], cwd=ROOT, capture_output=True, text=True, timeout=60,
                         env={**os.environ, "COMPOSE_E2E_DRY_RUN": "1"})
    assert out.returncode == 0, out.stderr
    return dict(line.split("=", 1) for line in out.stdout.splitlines() if re.match(r"^(project|env_file|ports)=", line))


def test_each_run_gets_its_own_random_project_apart_from_the_users():
    first, second = dry_run(), dry_run()
    for run in (first, second):
        assert re.fullmatch(r"cecilai-e2e-[a-z0-9]{6,}", run["project"])
        assert not run["project"].startswith(USER_PROJECT)
    assert first["project"] != second["project"]


def test_it_uses_its_own_temporary_settings_and_free_ports_never_the_repository_env():
    before = (ROOT / ".env").stat().st_mtime_ns if (ROOT / ".env").exists() else None
    run = dry_run()
    env_file = Path(run["env_file"])
    assert ROOT not in env_file.resolve().parents  # a temporary file outside the repository
    assert not env_file.exists()  # a dry run removes what it made
    ports = [int(p) for p in run["ports"].split(",")]
    assert len(set(ports)) == len(ports) >= 4 and 8000 not in ports and 3000 not in ports
    after = (ROOT / ".env").stat().st_mtime_ns if (ROOT / ".env").exists() else None
    assert before == after


def test_every_compose_call_of_the_script_names_its_own_project_and_only_its_cleanup_removes_anything():
    assert USER_PROJECT not in CODE and "--env-file .env" not in CODE
    assert not re.search(r"^\s*python3 ops/bootstrap_env.py\s*$", E2E, re.M)  # it would write the repository's .env
    calls = re.findall(r"docker compose[^\n]*", E2E)
    assert calls and all("-p $PROJECT" in c or "$COMPOSE" in c for c in calls)
    assert 'COMPOSE="docker compose -p $PROJECT ' in E2E
    downs = [line for line in E2E.splitlines() if re.search(r"\bdown\b", line) and "$COMPOSE" in line]
    cleanup = E2E.split("cleanup() {", 1)[1].split("\n}", 1)[0]
    assert len(downs) == 1 and downs[0].strip() in cleanup  # the one removal is inside the cleanup that has the guard
    assert 'case "$PROJECT" in cecilai-e2e-*)' in E2E  # a guard: it refuses to clean up a project that is not its own


def test_only_the_explicit_target_drops_the_volumes_of_the_users_stack():
    targets = {}
    current = None
    for line in MAKEFILE.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):", line)
        if m:
            current = m.group(1)
            targets[current] = []
        elif current and line.startswith("\t"):
            targets[current].append(line)
    deleting = {t for t, body in targets.items() if any(re.search(r"\bdown\b.*\s-v\b|--volumes|volume rm", line) for line in body)}
    assert deleting == {"clean-volumes"}, deleting
    assert "clean-volumes" in targets and "down" in targets
    assert "name: cecilai-local" in (ROOT / "ops" / "docker-compose.yml").read_text(encoding="utf-8")


def test_a_failing_run_exits_nonzero_and_only_ever_calls_docker_for_its_own_project(tmp_path):
    """With a stand-in `docker` that fails to start the stack: the script fails (the cleanup keeps its exit status) and every
    docker call, the cleanup's included, names the e2e project."""
    log = tmp_path / "calls.log"
    fake = tmp_path / "bin" / "docker"
    fake.parent.mkdir()
    fake.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\ncase "$*" in *" up "*) exit 1 ;; esac\nexit 0\n')
    fake.chmod(0o755)
    out = subprocess.run(["sh", str(ROOT / "ops" / "compose_e2e.sh")], cwd=ROOT, capture_output=True, text=True, timeout=60,
                         env={**os.environ, "PATH": f"{fake.parent}:{os.environ['PATH']}"})
    assert out.returncode != 0
    calls = log.read_text().splitlines()
    assert calls and all(re.match(r"compose -p cecilai-e2e-[a-z0-9]+ ", c) for c in calls), calls
    assert not any(USER_PROJECT in c for c in calls)
    assert sum(" down -v " in c for c in calls) == 1
