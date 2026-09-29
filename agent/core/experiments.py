"""Shadow y canary: probar un modelo candidato con tráfico real sin poner en riesgo al cliente. Apagados por defecto.

- **Shadow** (`SHADOW_MODEL=provider:modelo`): después de que el modelo de siempre responde, el candidato recibe *los
  mismos mensajes ya enmascarados* y propone sus llamadas a herramientas en un hilo aparte. No ejecuta nada, no
  cambia la respuesta ni suma latencia al turno; solo deja un registro para comparar (`SHADOW_LOG_PATH`). Ve exactamente
  lo que ya ve el modelo principal, así que no expone datos nuevos. Cuesta tokens: `SHADOW_SAMPLE_PERCENT` lo acota.
- **Canary** (`CANARY_MODEL=provider:modelo`, `CANARY_PERCENT=0-100`): un porcentaje de sesiones, elegido de forma
  determinística por el hash de su `session_ref` (una sesión no cambia de modelo a mitad de conversación), usa el
  candidato como modelo principal. Si el candidato falla, el turno se rehace con el modelo de siempre: el cliente nunca
  paga por un candidato roto. Cada traza guarda el grupo asignado en `cohort`, incluso sin llamar al modelo, y
  `model_route` indica si respondió el candidato, el principal o hubo fallback. `cohorts()` compara los grupos asignados.

Lo que las políticas en código deciden (escalar, pedir confirmación, autorizar) no depende del modelo: un candidato solo
puede cambiar qué herramienta propone, y el orquestador la valida igual (ADR-001).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from agent.llm.client import LLMUnavailable, candidate_client

logger = logging.getLogger(__name__)


def bucket(key: str) -> int:
    """A stable 0-99 for a key: the same session or trace always lands in the same place."""
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 100


def _calls(resp) -> list[dict]:
    """The tool calls a response proposes, arguments parsed and with empty slots dropped (as the orchestrator does)."""
    out = []
    for c in resp.tool_calls:
        try:
            args = json.loads(c["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}
        out.append({"name": c["name"], "args": {k: v for k, v in (args if isinstance(args, dict) else {}).items() if v not in (None, "")}})
    return out


class Experiments:
    def __init__(self, shadow: Callable[[], Any] | None = None, canary: Callable[[], Any] | None = None,
                 canary_percent: int = 0, shadow_percent: int = 100, log_path: str | None = None):
        self._shadow, self._canary = shadow, canary
        self.canary_percent, self.shadow_percent = canary_percent, shadow_percent
        self._log_path = log_path
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shadow")
        self._pending: list[Future] = []
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "Experiments":
        def lazily(var: str):
            spec = os.environ.get(var, "").strip()
            cached: list = []

            def factory():
                if not cached:
                    cached.append(candidate_client(spec))
                return cached[0]
            return factory if spec else None

        pct = lambda var, default: max(0, min(100, int(os.environ.get(var, default) or default)))  # noqa: E731
        return cls(lazily("SHADOW_MODEL"), lazily("CANARY_MODEL"), pct("CANARY_PERCENT", 0), pct("SHADOW_SAMPLE_PERCENT", 100))

    @property
    def shadow_enabled(self) -> bool:
        return self._shadow is not None

    @property
    def canary_enabled(self) -> bool:
        return self._canary is not None

    @property
    def log_path(self) -> Path:
        p = Path(self._log_path or os.environ.get("SHADOW_LOG_PATH", "data/warehouse/shadow_log.jsonl"))
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def cohort_for(self, session_ref: str) -> str:
        """Assignment is independent of whether a turn needs a model or the candidate succeeds."""
        return "canary" if self._canary and bucket(session_ref) < self.canary_percent else "primary"

    def chat(self, session_ref: str, primary: Callable[[], Any], messages: list[dict], tools: list[dict]):
        """The model response and serving route. A canary that fails is replaced by the usual model."""
        if self.cohort_for(session_ref) == "canary":
            try:
                return self._canary().chat(messages, tools=tools), "canary"
            except LLMUnavailable:
                route = "canary_fallback"
            except Exception:  # noqa: BLE001 - a broken candidate must never reach the customer
                logger.exception("canary model failed; answering with the usual model")
                route = "canary_fallback"
            return primary().chat(messages, tools=tools), route
        return primary().chat(messages, tools=tools), "primary"

    def shadow(self, trace_id: str, session_ref: str, messages: list[dict], tools: list[dict], resp, route: str) -> None:
        """Ask the candidate the same thing in the background and log how it differs. Never raises, never blocks."""
        if not self._shadow or route != "primary" or bucket(trace_id) >= self.shadow_percent:
            return
        job = self._pool.submit(self._run_shadow, trace_id, session_ref, list(messages), tools, resp)
        with self._lock:
            self._pending = [f for f in self._pending if not f.done()] + [job]

    def drain(self, timeout: float = 30) -> None:
        """Wait for the shadow calls in flight (tests, and a clean shutdown)."""
        with self._lock:
            pending = list(self._pending)
        for f in pending:
            f.result(timeout=timeout)

    def _run_shadow(self, trace_id, session_ref, messages, tools, resp) -> None:
        primary = {"provider": resp.provider, "model": resp.model, "latency_ms": round(resp.latency_ms, 1), "calls": _calls(resp)}
        record: dict[str, Any] = {"ts": time.time(), "trace_id": trace_id, "session_ref": session_ref, "primary": primary}
        try:
            other = self._shadow().chat(messages, tools=tools)
            shadow = {"provider": other.provider, "model": other.model, "latency_ms": round(other.latency_ms, 1),
                      "calls": _calls(other), "usage": {"prompt": other.usage.prompt_tokens, "completion": other.usage.completion_tokens}}
            record.update(shadow=shadow, same_tools=[c["name"] for c in primary["calls"]] == [c["name"] for c in shadow["calls"]],
                          same_args=primary["calls"] == shadow["calls"])
        except Exception as exc:  # noqa: BLE001 - the candidate failing is a finding, not a problem for the customer
            record.update(shadow={"error": type(exc).__name__}, same_tools=None, same_args=None)
        try:
            with self._lock, open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("could not write the shadow log")


def read_log(path: Path, limit: int = 1000) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[-limit:] if line.strip()]


def summarize_shadow(rows: list[dict]) -> dict:
    """How often the candidate proposes what the usual model proposes, and what it costs in time."""
    ok = [r for r in rows if r.get("same_tools") is not None]
    rate = lambda key: round(sum(bool(r[key]) for r in ok) / len(ok), 3) if ok else None  # noqa: E731
    p50 = lambda vals: sorted(vals)[len(vals) // 2] if vals else None  # noqa: E731
    return {"turns": len(rows), "candidate_errors": len(rows) - len(ok), "same_tools_rate": rate("same_tools"),
            "same_args_rate": rate("same_args"),
            "latency_ms_p50": {"primary": p50([r["primary"]["latency_ms"] for r in ok]),
                               "candidate": p50([r["shadow"]["latency_ms"] for r in ok])},
            "disagreements": [{"trace_id": r["trace_id"], "primary": r["primary"]["calls"], "candidate": r["shadow"]["calls"]}
                              for r in ok if not r["same_tools"]][:5],
            "note": "agreement is not accuracy: two models can agree and both be wrong; judge disagreements against the trace"}


def cohorts(trace_rows: list[dict]) -> dict:
    """Outcomes by assigned group, including policy-only turns and failures. Missing assignments remain unknown."""
    groups: dict[str, list[dict]] = {}
    for r in trace_rows:
        name = r.get("cohort") or "unassigned"
        if name == "canary_fallback":  # older traces recorded the serving route as their cohort
            name = "canary"
        groups.setdefault(name, []).append(r)
    out = {}
    for name, rows in groups.items():
        n = len(rows)
        lat = sorted(float(r.get("latency_ms") or 0) for r in rows)
        out[name] = {"turns": n, "escalation_rate": round(sum(r.get("disposition") == "ESCALATE" for r in rows) / n, 3),
                     "auto_resolve_rate": round(sum(r.get("disposition") == "AUTO_RESOLVE" for r in rows) / n, 3),
                     "latency_ms_p50": round(lat[n // 2], 1),
                     "cost_usd": round(sum(float(r["cost_usd"]) for r in rows if r.get("cost_usd") is not None), 6)}
    return out
