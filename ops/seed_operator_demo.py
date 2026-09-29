"""Un entorno local para probar la consola de operador sin claves de modelo ni datos reales.

Construye el warehouse mínimo de `tests/fixtures/raw`, genera claves de lectura y de dos operadores, y llena la cola
y el registro de trazas usando la propia API (turnos de chat reales, sin modelo: el asistente escala). Escribe todo en
`--dir` y deja ahí `operator-demo.env`, que se carga antes de levantar la API:

    python -m ops.seed_operator_demo --dir /tmp/cecilai-operator-demo
    set -a; . /tmp/cecilai-operator-demo/operator-demo.env; set +a
    python -m uvicorn api.main:app --port 8000

Las claves salen de `secrets` en cada corrida y no se guardan en el repositorio. Los datos son sintéticos.
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "raw"
SERVING = ["branches", "daily_exchange_rates", "customers", "products", "transactions"]

# (cliente, mensaje): lo que dispara cada reglas de política sin llamar a un modelo.
TURNS = [
    ("CLI-FIX0001", "me robaron la tarjeta, necesito bloquearla ya"),
    ("CLI-FIX0002", "no reconozco un cargo en mi tarjeta, creo que es un fraude"),
    ("CLI-FIX0005", "¿cuál es mi saldo?"),
    ("CLI-FIX0001", "¿cuánto debo en mi préstamo personal?"),
    ("CLI-FIX0003", "¿cuál es el tipo de cambio de hoy?"),
]
TRACE_REVIEWS = [
    ("CLI-FIX0004", "PRD-FIX0010", "TXN-FIX0006", "older_than_review_threshold", 100, "no me llegó la transferencia de hace unos meses"),
]


def seed(target: Path) -> dict[str, str]:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    keys = {"ADMIN_API_KEY": "admin-" + secrets.token_urlsafe(24), "ana": "ana-" + secrets.token_urlsafe(24),
            "beto": "beto-" + secrets.token_urlsafe(24)}
    env = {
        "DUCKDB_PATH": str(target / "bank.duckdb"), "AUDIT_LOG_PATH": str(target / "audit_log.jsonl"),
        "HUMAN_QUEUE_PATH": str(target / "human_queue.jsonl"), "HUMAN_DESK_PATH": str(target / "ticket_events.jsonl"),
        "TRACE_LOG_PATH": str(target / "traces.jsonl"), "TRACE_REQUESTS_PATH": str(target / "trace_requests.jsonl"),
        "DRIFT_BASELINE_PATH": str(target / "traffic_baseline.json"), "DEMO_IDP_SECRET": "demo-" + secrets.token_urlsafe(16),
        "ADMIN_API_KEY": keys["ADMIN_API_KEY"], "OPERATOR_KEYS": f"ana={keys['ana']},beto={keys['beto']}",
        "ANTHROPIC_API_KEY": "", "GROQ_API_KEY": "", "TOGETHER_API_KEY": "", "CLIENT_IP_HEADER": "X-Client-IP",
    }
    os.environ.update(env)

    from fastapi.testclient import TestClient

    from agent.policy import router
    from agent.policy.escalation import escalate
    from agent.session.identity import derive_test_pin
    from agent.tools import db
    from api import main
    from data.pipeline import RunConfig, run_pipeline

    run_pipeline(SERVING, RunConfig(source="local", raw_dir=FIXTURES))
    db.close_all()
    client = TestClient(main.app)
    for customer, text in TURNS:
        token = client.post("/auth/session", json={"customer_id": customer, "pin": derive_test_pin(customer)}).json()["token"]
        client.post("/chat", json={"session_token": token, "message": text})
    for customer, product, txn, why, age, text in TRACE_REVIEWS:
        action = {"tool": "request_trace", "transaction_id": txn, "product_id": product, "review_reason": why, "age_days": age,
                  "movement": {"transaction_type": "Transfer", "amount": 40, "currency": "USD"}}
        escalate(router.trace_review(why), customer, "demo-ref", text, "es", [], [], [], {"segment": "Student", "country": "México"},
                 None, action)

    lines = [f"export {k}='{v}'" for k, v in env.items()]
    (target / "operator-demo.env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return keys


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default="/tmp/cecilai-operator-demo", type=Path)
    args = ap.parse_args()
    keys = seed(args.dir)
    print(f"entorno en {args.dir}; cargalo con: set -a; . {args.dir}/operator-demo.env; set +a")
    print(f"clave de lectura (admin): {keys['ADMIN_API_KEY']}")
    print(f"clave de operador ana: {keys['ana']}\nclave de operador beto: {keys['beto']}")


if __name__ == "__main__":
    main()
