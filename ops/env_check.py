"""Compares a `.env` with `.env.example`: which settings the example has and the file lacks, and what in it would reach for S3.

    python -m ops.env_check                  # lists the missing names (never a value) and warns; always exits 0: `make up` goes on
    python -m ops.env_check --strict         # exits 1 when something is missing or a warning applies
    python -m ops.env_check --fill           # appends the missing settings, with generated secrets; touches nothing that is there

A `.env` made by an older `make env` predates settings added since (METRICS_TOKEN, GRAFANA_ADMIN_PASSWORD, WEB_PUBLIC_ORIGIN...):
the stack still boots, because compose gives each a default, but a missing secret fails closed (metrics, Grafana, logins). And an
INGEST_ARGS copied from the example has no `--source local`, so the first boot would read the organizer's bucket. Only names are
printed, and never the value of anything: the file holds secrets. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ops.bootstrap_env import ROOT, SECRETS, local_values

DECLARED = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$", re.M)
# Settings that fail closed when they are empty: worth a warning even when the name is there
NEEDS_A_VALUE = (*SECRETS, "OPERATOR_KEYS")


def parse(text: str) -> dict[str, str]:
    """The uncommented `NAME=value` lines (the last one wins, as in a dotenv file)."""
    return {m.group(1): m.group(2).strip() for m in DECLARED.finditer(text)}


def missing(example: str, env: str) -> list[str]:
    have = parse(env)
    return [name for name in parse(example) if name not in have]


def empty_secrets(env: str) -> list[str]:
    have = parse(env)
    return [name for name in NEEDS_A_VALUE if name in have and not have[name].strip("'\"")]


def ingests_from_s3(env: str) -> bool:
    """INGEST_ARGS is set and does not say `--source local`: the loader's default source is the bucket."""
    args = parse(env).get("INGEST_ARGS")
    return bool(args) and not re.search(r"--source(?:\s+|=)local\b", args)


def fill(example: str, env: str) -> tuple[str, list[str]]:
    """`env` plus each setting it lacks, appended: generated secrets and the local sandbox choices `make env` makes, else the
    example's own value. Nothing already in `env` changes."""
    names = missing(example, env)
    if not names:
        return env, []
    values = {**parse(example), **local_values()}
    block = "".join(f"{name}={values[name]}\n" for name in names)
    sep = "" if env.endswith("\n") or not env else "\n"
    return f"{env}{sep}\n# added by `make env-fill`: settings .env.example gained after this file was made\n{block}", names


def report(example: str, env: str) -> list[str]:
    lines = []
    lack = missing(example, env)
    if lack:
        lines.append(f".env lacks {len(lack)} setting(s) that .env.example has (compose defaults cover them; `make env-fill` adds them):")
        lines += [f"  {name}" for name in lack]
    blank = empty_secrets(env)
    if blank:
        lines.append("empty, so they fail closed (make env-fill does not change what is there; set them or recreate with `make env`):")
        lines += [f"  {name}" for name in blank]
    if ingests_from_s3(env):
        lines.append("INGEST_ARGS has no `--source local`: the first boot would ingest from S3 and needs AWS_* and DATASET_BUCKET. "
                     "For the fixture warehouse use: --profile serving --source local --raw-dir /app/tests/fixtures/raw")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env", type=Path, default=ROOT / ".env")
    ap.add_argument("--example", type=Path, default=ROOT / ".env.example")
    ap.add_argument("--fill", action="store_true", help="append the missing settings")
    ap.add_argument("--strict", action="store_true", help="exit 1 when something is missing or a warning applies")
    args = ap.parse_args(argv)
    if not args.env.exists():
        print(f"{args.env.name} does not exist: `make env` creates it")
        return 1 if args.strict else 0
    example = args.example.read_text(encoding="utf-8")
    env = args.env.read_text(encoding="utf-8")
    if args.fill:
        text, names = fill(example, env)
        if names:
            args.env.write_text(text, encoding="utf-8")  # the file exists: its mode stays as it was
            print(f"added to {args.env.name}: {', '.join(names)}")
        else:
            print(f"{args.env.name} already has every setting of {args.example.name}")
        env = text
    lines = report(example, env)
    if lines:
        print("env-check:")
        print("\n".join(lines))
    else:
        print(f"env-check: {args.env.name} has every setting of {args.example.name}")
    return 1 if lines and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
