"""Creates the root .env for a local run from .env.example, with freshly generated secrets.

    python -m ops.bootstrap_env            # writes .env, or leaves an existing one alone
    python -m ops.bootstrap_env --force    # replaces it
    python -m ops.bootstrap_env --out /tmp/x.env --free-ports   # a throwaway settings file on ports nothing is using (the e2e check)

Local settings, not production ones: the fixture warehouse (no bucket needed) and DEMO_MODE=1, so the guided
scenarios and the test PINs work. Every secret is random per machine and never printed. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import secrets
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_INGEST = "--profile serving --source local --raw-dir /app/tests/fixtures/raw"
SECRETS = ("DEMO_IDP_SECRET", "ADMIN_API_KEY", "METRICS_TOKEN", "GRAFANA_ADMIN_PASSWORD", "BFF_CLIENT_IP_SECRET")


PORTS = ("API_PORT", "WEB_PORT", "PROMETHEUS_PORT", "GRAFANA_PORT", "OLLAMA_PORT")


def free_ports(n: int) -> list[int]:
    """n distinct ports that nothing is listening on right now (all held open together, so they differ)."""
    sockets = [socket.socket() for _ in range(n)]
    try:
        for sock in sockets:
            sock.bind(("127.0.0.1", 0))
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def local_values(use_free_ports: bool = False) -> dict[str, str]:
    values = {**{name: secrets.token_urlsafe(32) for name in SECRETS},
              "OPERATOR_KEYS": f"operator1={secrets.token_urlsafe(32)}",
              "DEMO_MODE": "1", "INGEST_ARGS": FIXTURE_INGEST}
    if use_free_ports:
        values.update({name: str(port) for name, port in zip(PORTS, free_ports(len(PORTS)))})
    return values


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
    ap.add_argument("--out", type=Path, help="write here instead of ROOT/.env (always replaces)")
    ap.add_argument("--free-ports", action="store_true", help="choose ports nothing is using for every published service")
    args = ap.parse_args(argv)
    target = args.out or args.root / ".env"
    if target.exists() and not args.force and not args.out:
        print(".env already exists: left as it is (use --force to replace it)")
        return 0
    target.write_text(render((args.root / ".env.example").read_text(encoding="utf-8"), local_values(args.free_ports)), encoding="utf-8")
    target.chmod(0o600)
    print(f"wrote {target.name} with generated secrets (local sandbox: fixture warehouse, DEMO_MODE=1)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
