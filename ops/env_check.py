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
import shlex
import sys
from pathlib import Path

from ops.bootstrap_env import ROOT, SECRETS, local_values

# `[export] NAME [spaces] = value`, as Compose's dotenv reads a line: a comment line or a blank one matches nothing
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*)$")
ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\", "$": "$"}
# Settings that fail closed when they are empty: worth a warning even when the name is there
NEEDS_A_VALUE = (*SECRETS, "OPERATOR_KEYS")


def _value(rest: str, more: list[str]) -> str:
    """The value that follows `=`: a quoted one runs to its closing quote (a double-quoted one may span lines, and reads
    \\n \\" \\\\ escapes; a single-quoted one is literal except for `\\'`, which Compose reads as a quote) and what follows the quote is dropped; an unquoted one ends at the first ` #` and loses its trailing
    spaces. `more` holds the lines after this one and is consumed by a quoted value that continues on them."""
    if rest[:1] in ("'", '"'):
        quote, out, i, line = rest[0], [], 1, rest
        while True:
            while i < len(line):
                ch = line[i]
                if ch == quote:
                    return "".join(out)
                if quote == '"' and ch == "\\" and i + 1 < len(line):
                    out.append(ESCAPES.get(line[i + 1], "\\" + line[i + 1]))
                    i += 2
                    continue
                if quote == "'" and ch == "\\" and line[i + 1:i + 2] == "'":
                    out.append("'")
                    i += 2
                    continue
                out.append(ch)
                i += 1
            if not more:  # never closed: what there is
                return "".join(out)
            out.append("\n")
            line, i = more.pop(0), 0
    return re.split(r"\s#", rest, maxsplit=1)[0].strip()


def assignments(text: str) -> list[tuple[str, str, str]]:
    """(name, value, the text as written) for every assignment, in order; a multi-line quoted value keeps all its lines."""
    found = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = ASSIGNMENT.match(lines[i])
        if not m:
            i += 1
            continue
        rest = lines[i + 1:]
        value = _value(m.group(2), rest)
        used = len(lines) - i - 1 - len(rest)  # the lines a quoted value went on to consume
        found.append((m.group(1), value, "\n".join(lines[i:i + 1 + used])))
        i += 1 + used
    return found


def parse(text: str) -> dict[str, str]:
    """NAME -> value of every assignment, read as Compose's dotenv does (the last one wins, as there)."""
    return {name: value for name, value, _ in assignments(text)}


def missing(example: str, env: str) -> list[str]:
    have = parse(env)
    return [name for name in parse(example) if name not in have]


def empty_secrets(env: str) -> list[str]:
    have = parse(env)
    return [name for name in NEEDS_A_VALUE if name in have and not have[name].strip()]


def ingests_from_s3(env: str) -> bool:
    """INGEST_ARGS is set and its last effective `--source` is not `local` (or it has none: the loader's default is the bucket).
    Read as Compose reads it (a comment after the value is not part of it) and as argparse reads it (the last one wins)."""
    args = parse(env).get("INGEST_ARGS")
    if not args:
        return False
    try:
        words = shlex.split(args)
    except ValueError:
        words = args.split()
    source = "s3"
    for i, word in enumerate(words):
        if word == "--source" and i + 1 < len(words):
            source = words[i + 1]
        elif word.startswith("--source="):
            source = word.split("=", 1)[1]
    return source != "local"


def _written(value: str) -> str:
    """`value` as one dotenv line holds it: bare when that reads back the same, quoted when a ` #`, a quote, a `$` (Compose interpolates it) or an edge space would not."""
    if not value or not (re.search(r"\s#|['\"$]|^\s|\s$", value) or "\n" in value):
        return value
    if "'" not in value and "\n" not in value:
        return f"'{value}'"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("$", "\\$") + '"'


def fill(example: str, env: str) -> tuple[str, list[str]]:
    """`env` plus each setting it lacks, appended: generated secrets and the local sandbox choices `make env` makes (serialized
    here), else the example's own line, verbatim. Nothing already in `env` changes."""
    names = missing(example, env)
    if not names:
        return env, []
    written = {name: raw for name, _, raw in assignments(example)}  # a default from the example is copied as it is written there:
    generated = local_values()                                       # ${X:-y} and $$ keep meaning what they mean to Compose
    block = "".join(f"{name}={_written(generated[name])}\n" if name in generated else f"{written[name]}\n" for name in names)
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
    values = parse(env)
    if values.get("DEMO_CONSOLE") == "1" and values.get("DEMO_MODE") != "1":
        lines.append("DEMO_CONSOLE=1 without DEMO_MODE=1: the demo's console stays off (both must be exactly 1)")
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
