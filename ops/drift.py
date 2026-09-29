"""Drift del tráfico real: compara lo que llega hoy contra una foto de referencia, con PSI.

El drift de esquema de los datos ya se controla en la ingesta (`data/quality.py`). Esto mira el otro lado: si el tráfico
que recibe el asistente cambió (más portugués, otras intenciones, el clasificador menos seguro, más escalaciones) sin
que nadie lo haya decidido. Ese cambio es la señal de que la evaluación offline dejó de describir lo que pasa.

- Señales, todas salidas del registro de trazas: idioma, disposición, categoría, intención leída y confianza del
  clasificador en tres tramos.
- La referencia es una foto de los conteos (`python -m ops.drift --snapshot`, o POST /admin/drift/snapshot en Render, que
  no tiene shell). No se guardan trazas ni datos de clientes, solo conteos.
- PSI < 0.10 estable, < 0.25 moderado, >= 0.25 significativo (los cortes habituales). Con menos de MIN_N turnos en
  cualquiera de los dos lados no se opina: el PSI con pocos datos es ruido.

Un PSI alto dice que algo cambió, no qué está mal: ni el modelo ni el tráfico son "culpables" hasta mirar las trazas.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from agent.tools.audit import default_trace_log

MIN_N = 50
EPS = 1e-4  # a value that appears on one side only must not send the log to infinity


def _confidence(row: dict) -> str | None:
    p = (row.get("intent_reading") or {}).get("p_intent")
    if p is None:
        return None
    return "low(<0.6)" if p < 0.6 else "mid(0.6-0.85)" if p < 0.85 else "high(>=0.85)"


SIGNALS: dict[str, Callable[[dict], Any]] = {
    "language": lambda r: r.get("language"),
    "disposition": lambda r: r.get("disposition"),
    "category": lambda r: r.get("category"),
    "intent": lambda r: (r.get("intent_reading") or {}).get("intent"),
    "confidence": _confidence,
}


def baseline_path() -> Path:
    p = Path(os.environ.get("DRIFT_BASELINE_PATH", "data/warehouse/traffic_baseline.json"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def counts(rows: list[dict]) -> dict[str, dict[str, int]]:
    return {name: dict(Counter(str(v) for v in map(fn, rows) if v is not None)) for name, fn in SIGNALS.items()}


def psi(expected: dict[str, int], actual: dict[str, int]) -> float:
    """Population stability index between two count tables over the same categories."""
    e_total, a_total = sum(expected.values()) or 1, sum(actual.values()) or 1
    total = 0.0
    for k in set(expected) | set(actual):
        e, a = max(expected.get(k, 0) / e_total, EPS), max(actual.get(k, 0) / a_total, EPS)
        total += (a - e) * math.log(a / e)
    return total


def status_of(value: float) -> str:
    return "stable" if value < 0.10 else "moderate" if value < 0.25 else "significant"


def snapshot(rows: list[dict]) -> dict:
    return {"created_at": time.time(), "n": len(rows), "signals": counts(rows)}


def compare(baseline: dict, recent: list[dict]) -> dict:
    if baseline["n"] < MIN_N or len(recent) < MIN_N:
        return {"status": "insufficient_data", "baseline_n": baseline["n"], "recent_n": len(recent), "min_n": MIN_N}
    now, signals = counts(recent), {}
    for name in SIGNALS:
        value = round(psi(baseline["signals"].get(name, {}), now.get(name, {})), 4)
        signals[name] = {"psi": value, "status": status_of(value), "baseline": baseline["signals"].get(name, {}), "recent": now.get(name, {})}
    worst = max(signals.values(), key=lambda s: s["psi"])["status"]
    return {"status": worst, "baseline_n": baseline["n"], "recent_n": len(recent), "signals": signals}


def load_baseline() -> dict | None:
    path = baseline_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_baseline(rows: list[dict]) -> dict:
    snap = snapshot(rows)
    baseline_path().write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return snap


def recent_rows(limit: int = 500) -> list[dict]:
    path = default_trace_log.path
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[-limit:] if line.strip()]


def report(limit: int = 500) -> dict:
    baseline = load_baseline()
    if baseline is None:
        return {"status": "no_baseline", "hint": "take one with POST /admin/drift/snapshot once the traffic looks normal"}
    return compare(baseline, recent_rows(limit))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", action="store_true", help="freeze the last --limit turns as the reference")
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()
    if args.snapshot:
        snap = save_baseline(recent_rows(args.limit))
        print(f"referencia guardada: {snap['n']} turnos en {baseline_path()}")
    else:
        print(json.dumps(report(args.limit), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
