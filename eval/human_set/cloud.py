"""The collection form of the human-written test set, on Cloudflare (docs/human_set.md).

    python -m eval.human_set.cloud deploy           # D1 base and table, Worker upload (inert without a route)
    python -m eval.human_set.cloud deploy --route   # also connects marvaq.com/encuesta (the form goes live)
    python -m eval.human_set.cloud export           # the answers -> eval/workload/human_raw.jsonl

Uses the Cloudflare API with the token in CLOUDFLARE_SECRETS (a JSON file kept outside any repository, with
api_token, account_id and zone_id); the ids it creates are saved back in that file under "human_set". The
answers file lands in eval/workload/, which the public export removes from every commit.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
SECRETS = Path(os.environ.get("CLOUDFLARE_SECRETS", r"C:\dev\secrets\cloudflare-marvaq.json"))
WORKER_JS = Path(__file__).with_name("worker.js")
RAW = Path("eval/workload/human_raw.jsonl")
DEFAULTS = {"worker": "xpayments-encuesta", "d1_name": "xpayments-human-set", "route": "marvaq.com/encuesta*",
            "base": "/encuesta"}
SCHEMA = """CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  lang TEXT NOT NULL CHECK (lang IN ('es', 'pt')),
  country TEXT NOT NULL,
  saw_system INTEGER NOT NULL CHECK (saw_system IN (0, 1)),
  consent_version TEXT NOT NULL,
  answers TEXT NOT NULL
)"""


def _request(path: str, token: str, method: str = "GET", body: bytes | None = None,
             content_type: str = "application/json") -> dict:
    req = urllib.request.Request(f"{API}{path}", data=body, method=method,  # noqa: S310
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=120) as res:  # noqa: S310
            return json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as error:
        return json.loads(error.read() or b"{}")


def call(path: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    out = _request(path, token, method, json.dumps(body).encode() if body is not None else None)
    if not out.get("success"):
        raise SystemExit(f"{method} {path} failed: {out.get('errors')}")
    return out


def query(cfg: dict, sql: str, params: list | None = None) -> list[dict]:
    out = call(f"/accounts/{cfg['account_id']}/d1/database/{cfg['human_set']['d1_uuid']}/query", cfg["api_token"],
               "POST", {"sql": sql, "params": params or []})
    return (out.get("result") or [{}])[0].get("results") or []


def load() -> dict:
    cfg = json.loads(SECRETS.read_text(encoding="utf-8"))
    cfg["human_set"] = {**DEFAULTS, **cfg.get("human_set", {})}
    return cfg


def save(cfg: dict) -> None:
    SECRETS.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def deploy(route: bool) -> None:
    cfg = load()
    hs, token, account = cfg["human_set"], cfg["api_token"], cfg["account_id"]
    if not hs.get("d1_uuid"):
        hs["d1_uuid"] = call(f"/accounts/{account}/d1/database", token, "POST", {"name": hs["d1_name"]})["result"]["uuid"]
        save(cfg)
        print(f"D1 database {hs['d1_name']} created")
    query(cfg, SCHEMA)

    metadata = {"main_module": "worker.js", "compatibility_date": "2026-09-01", "observability": {"enabled": True},
                "bindings": [{"type": "d1", "name": "DB", "id": hs["d1_uuid"]},
                             {"type": "plain_text", "name": "BASE", "text": hs["base"]}]}
    boundary = uuid.uuid4().hex
    body = b""
    for name, ctype, content in (("metadata", "application/json", json.dumps(metadata).encode()),
                                 ("worker.js", "application/javascript+module", WORKER_JS.read_bytes())):
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{name}\"\r\n"
                 f"Content-Type: {ctype}\r\n\r\n").encode() + content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    out = _request(f"/accounts/{account}/workers/scripts/{hs['worker']}", token, "PUT", body,
                   f"multipart/form-data; boundary={boundary}")
    if not out.get("success"):
        raise SystemExit(f"worker upload failed: {out.get('errors')}")
    print(f"Worker {hs['worker']} uploaded")

    # One public address only: the route on marvaq.com, never a second one on workers.dev.
    call(f"/accounts/{account}/workers/scripts/{hs['worker']}/subdomain", token, "POST", {"enabled": False})
    routes = call(f"/zones/{cfg['zone_id']}/workers/routes", token)["result"]
    if any(r["pattern"] == hs["route"] for r in routes):
        print(f"route already connected: {hs['route']}")
    elif route:
        call(f"/zones/{cfg['zone_id']}/workers/routes", token, "POST", {"pattern": hs["route"], "script": hs["worker"]})
        print(f"route connected: {hs['route']} (the form is live)")
    else:
        print("route not connected (no --route): the Worker is uploaded but unreachable")
    save(cfg)


def export() -> None:
    rows = query(load(), "SELECT id, created_at, lang, country, saw_system, consent_version, answers FROM submissions ORDER BY id")
    RAW.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({**r, "answers": json.loads(r["answers"])}, ensure_ascii=False) + "\n")
    kept = [r for r in rows if not r["saw_system"]]
    messages = sum(len(json.loads(r["answers"])) for r in kept)
    print(f"{len(rows)} submissions ({len(rows) - len(kept)} excluded: saw the system) -> {RAW}")
    print(f"{messages} messages from {len(kept)} people; by country {dict(Counter(r['country'] for r in kept))}, "
          f"by language {dict(Counter(r['lang'] for r in kept))}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("deploy").add_argument("--route", action="store_true", help="connect the public route (goes live)")
    sub.add_parser("export")
    args = ap.parse_args()
    deploy(args.route) if args.cmd == "deploy" else export()
