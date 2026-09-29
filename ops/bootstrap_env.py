"""Creates the root .env for a local run from .env.example, with freshly generated secrets.

    python -m ops.bootstrap_env            # writes .env, or leaves an existing one alone
    python -m ops.bootstrap_env --force    # replaces it

Local settings, not production ones: the fixture warehouse (no bucket needed) and DEMO_MODE=1, so the guided
scenarios and the test PINs work. Every secret is random per machine and never printed. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_INGEST = "--profile serving --source local --raw-dir /app/tests/fixtures/raw"
SECRETS = ("DEMO_IDP_SECRET", "ADMIN_API_KEY", "METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD")


def local_values() -> dict[str, str]:
    return {**{name: secrets.token_urlsafe(32) for name in SECRETS},
            "OPERATOR_KEYS": f"operator1={secrets.token_urlsafe(32)}",
            "DEMO_MODE": "1", "INGEST_ARGS": FIXTURE_INGEST}


def render(example: str, values: dict[str, str]) -> str:
    """The example with each named setting replaced by its value, comments and order untouched."""
    out = []
    for line in example.splitlines():
        m = re.match(r"([A-Z][A-Z0-9_]*)=", line)
        out.append(f"{m.group(1)}={values[m.group(1)]}" if m and m.group(1) in values else line)
    missing = [k for k in values if not re.search(rf"^{k}=", example, re.M)]
    if missing:
        raise ValueError(f".env.example does not declare: {', '.join(missing)}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="replace an existing .env")
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args(argv)
    target = args.root / ".env"
    if target.exists() and not args.force:
        print(".env already exists: left as it is (use --force to replace it)")
        return 0
    target.write_text(render((args.root / ".env.example").read_text(encoding="utf-8"), local_values()), encoding="utf-8")
    target.chmod(0o600)
    print("wrote .env with generated secrets (local sandbox: fixture warehouse, DEMO_MODE=1)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
