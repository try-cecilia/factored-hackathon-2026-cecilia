"""Ablation: what each safety layer buys, measured with the same models and the same judge.

    python -m eval.ablation [--split test] [--limit N]

The system's zero unsafe outcomes mean little next to a keyword baseline that also has zero. The counterfactual is
a model wired to the tools with the safety layers taken off one by one. Each rung adds a layer to the one before:

    naive-plain         the model's text goes to the customer, tools trust whatever product id the model passes,
                        and no session is checked (a plain tool-calling chatbot)
    naive-identity      + the session is validated and every tool checks that the product is the customer's
    naive-code-replies  + the model's text never reaches the customer: the reply is rendered from verified facts
    proposed            + the intent guard, the escalation policy, the one confirmed action and the degraded mode
                        (the real system, unchanged)

Every rung runs twice: with the ideal scripted model and with the deliberately bad one (obeys injections, asks for
other customers' products, invents figures). A layer that matters shows up as unsafe outcomes that disappear at its rung.

What this does not measure: the naive rungs never open a trace (the one action is a property of the real system), and
their "reply" when the model writes no text is the raw tool result, which is what a chatbot that relays tool output shows.
`text_outside_the_templates` is dropped from the naive rungs: their replies are free text by construction, so counting it
would only restate the design. Everything else is the same judge as `eval/run_system_eval.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from agent.core import orchestrator as orch_mod
from agent.core.orchestrator import TurnResult
from agent.core import render
from agent.llm.client import LLMUnavailable, Usage
from agent.session.auth import SessionError
from agent.tools import account_tools
from agent.tools.errors import ResourceNotFound, ToolError

# rung -> which layers it keeps
RUNGS = {
    "naive-plain": dict(session=False, owned=False, code_replies=False),
    "naive-identity": dict(session=True, owned=True, code_replies=False),
    "naive-code-replies": dict(session=True, owned=True, code_replies=True),
}
HEADLINE = ("n_cases", "unsafe_outcomes", "records_sent_to_model", "safe_automated_resolution", "unsafe_by_type")  # no per-case text in the JSON
STRUCTURAL = {"text_outside_the_templates"}  # true of every free-text reply by construction; see the module docstring

REAUTH = {"es": "Tu sesión terminó. Inicia sesión otra vez.", "pt": "Sua sessão terminou. Entre novamente."}
FAILED = {"es": "No pude completar la consulta.", "pt": "Não consegui concluir a consulta."}


def _unscoped_owned_product(customer_id: str, product_id: str) -> dict:
    """`_owned_product` without its ownership test: whoever knows a product id can read it."""
    rows = account_tools._rows("SELECT product_id, customer_id, product_type, product_status FROM products WHERE product_id = ?", [product_id])
    if not rows:
        raise ResourceNotFound(f"No product found with id {product_id}.")
    return rows[0]


def _plain(value):
    return json.dumps(value, default=lambda o: float(o) if isinstance(o, Decimal) else str(o), ensure_ascii=False)


class NaiveAgent:
    """A model wired to the read tools, with only the layers its rung names. One call for the tools, one to hand the
    results back to the model (which is what a tool loop does, and what the judge's records-sent check reads)."""

    def __init__(self, store, llm, rung: str, customer_id: str, language: str):
        self.store, self.llm, self.customer_id, self.language = store, llm, customer_id, language
        self.layers = RUNGS[rung]
        self.history: list[dict] = []

    def handle_message(self, token: str, text: str) -> TurnResult:
        from eval.run_system_eval import _catalog

        lang = self.language
        if self.layers["session"]:
            try:
                self.store.validate(token)
            except SessionError:
                return TurnResult("naive", "REAUTH_REQUIRED", REAUTH[lang], lang, "reauth_required", "session")
        self.history.append({"role": "user", "content": text})
        try:
            resp = self.llm.chat(list(self.history), None, 0.0)
        except LLMUnavailable:  # no degraded mode: the chatbot has nothing to say
            return TurnResult("naive", "ABSTAIN", FAILED[lang], lang, "llm_unavailable", "llm_unavailable")
        catalog = _catalog(self.customer_id)
        facts, actions = [], []
        for call in resp.tool_calls or []:
            name = call["name"]
            raw = json.loads(call["arguments"] or "{}")
            raw.pop("customer_id", None)
            action = {"tool": name, "raw_args": raw}
            try:
                args, _ = orch_mod.sanitize_args(name, raw, catalog)
                guard = mock.patch.object(account_tools, "_owned_product", _unscoped_owned_product) if not self.layers["owned"] else nullcontext()
                with guard:
                    result = orch_mod.run_tool(name, self.customer_id, **args)
                action.update({"args": args, "success": True})
                facts.append({"tool": name, "args": args, "result": result})
            except ToolError as exc:
                action.update({"success": False, "error_type": type(exc).__name__, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001 - a tool failure is an answer for the chatbot, not a crash
                action.update({"success": False, "error_type": type(exc).__name__, "error": str(exc)})
            actions.append(action)
        if facts:  # the tool loop: the model reads the results before it answers
            self.llm.chat(self.history + [{"role": "tool", "content": _plain([f["result"] for f in facts])}], None, 0.0)
        if self.layers["code_replies"]:
            reply = render.render_answer(facts, lang, catalog) if facts else FAILED[lang]
        else:
            reply = resp.content or (_plain([f["result"] for f in facts]) if facts else FAILED[lang])
        self.history.append({"role": "assistant", "content": reply})
        answered = bool(facts) or bool(resp.content and not resp.tool_calls)
        return TurnResult("naive", "AUTO_RESOLVE" if answered else "ABSTAIN", reply, lang, "none", "naive",
                          None, facts, actions, usage=Usage(), cost_usd=0.0, llm_calls=1 + bool(facts))


def _run_naive_case(case, rung: str, llm_mode: str) -> dict:
    """`run_system_eval.run_case` for a naive rung: the same session, the same models, the same fault injection, another agent."""
    from eval import run_system_eval as rse

    store = rse.SessionStore(ttl_seconds=-1 if case.fault == "expired_session" else 900)
    session = store.issue(case.customer_id, {"segment": case.segment, "country": case.country, "customer_status": case.customer_status})
    scripted = rse.ScriptedLLM(case) if llm_mode == "scripted" else rse.AdversarialLLM(case, rse.FOREIGN_POOL)
    recorder = rse._Recorder(scripted)
    agent = NaiveAgent(store, recorder, rung, case.customer_id, case.language)
    results = []
    kind, _, after = (case.fault or "").partition(":")
    with rse.inject(case.fault):
        if kind == "case_probe":
            results = rse._case_probe(agent, case, store, session)
        for i, text in enumerate(case.turns if kind != "case_probe" else []):
            scripted.turn = i
            try:
                results.append(agent.handle_message(rse._session_token(session.token, case.fault), text))
            except Exception as exc:  # noqa: BLE001 - a crash is an outcome to report, as in run_case
                results.append(TurnResult("crash", "ERROR", f"{type(exc).__name__}: {exc}", case.language, "crash"))
                break
            if kind == "expire_after" and i + 1 == int(after):
                store.expire(session.token)
            elif kind == "revoke_after" and i + 1 == int(after):
                store.revoke(session.token)
    return {"results": results, "sent": recorder.sent}


def run_rung(rung: str, mode: str, cases: list):
    """`run_system_eval.run` for any rung. The naive ones are plugged in from here (the case runner and the judge's rows are
    swapped for the call), so the measured evaluation code stays as it was and its fingerprint with it."""
    from eval import run_system_eval as rse

    if not rung.startswith("naive-"):
        return rse.run(rung, mode, cases)
    run_case, judge = rse.run_case, rse.judge
    with mock.patch.object(rse, "run_case", lambda case, system, llm_mode, live_client=None: _run_naive_case(case, system, llm_mode)),             mock.patch.object(rse, "judge", lambda *a, **k: without_structural(judge(*a, **k))):
        return rse.run(rung, mode, cases)


def without_structural(row: dict) -> dict:
    """The naive rungs' rows, without the finding that is true of any free-text reply."""
    unsafe = [u for u in row["unsafe"] if u not in STRUCTURAL]
    return {**row, "unsafe": unsafe, "safe_resolution": row["actual"] == "AUTO_RESOLVE" and bool(row["resolution_correct"]) and not unsafe}


def main() -> None:
    from eval import run_system_eval as rse
    from eval.stats import fmt
    from eval.workload import load

    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], default="test")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    cases = load(Path(f"eval/workload/cases_{a.split}.jsonl"))
    rse.FOREIGN_POOL[:] = [r[0] for r in rse.get_connection().execute(
        "SELECT product_id FROM products ORDER BY md5(product_id) LIMIT 500").fetchall()]
    if a.limit:
        cases = rse.sample(cases, a.limit)
    out: dict = {}
    for rung in [*RUNGS, "proposed"]:
        for mode in ("scripted", "adversarial"):
            m, rows = run_rung(rung, mode, cases)
            out[(rung, mode)] = m
            print(f"{rung:20s} {mode:12s} unsafe {m['unsafe_outcomes']['k']}/{m['n_cases']}", file=sys.stderr)
    kinds = sorted({k for m in out.values() for k in m["unsafe_by_type"]})
    lines = [
        "# Ablation: what each safety layer buys (auto-generated)", "",
        f"Generated by `python -m eval.ablation` at {datetime.now(timezone.utc).isoformat(timespec='seconds')} on the **{a.split}** workload "
        f"({len(cases)} cases), with the same judge as `SYSTEM_EVAL.md`. **Offline**: every rung runs a scripted model, ideal or deliberately bad. "
        "Method and what it does not measure: the docstring of `eval/ablation.py`.", "",
        "| Rung (layers kept) | Model | Unsafe outcomes | Records sent to the model | Safe automated resolution |", "|---|---|---|---|---|"]
    label = {"naive-plain": "plain chatbot (no layer)", "naive-identity": "+ session and ownership check",
             "naive-code-replies": "+ replies written by code", "proposed": "+ policy, escalation, the one confirmed action (the system)"}
    for rung in [*RUNGS, "proposed"]:
        for mode in ("scripted", "adversarial"):
            m = out[(rung, mode)]
            lines.append(f"| {label[rung]} | {'ideal' if mode == 'scripted' else 'bad'} | {fmt(m['unsafe_outcomes'])} | "
                         f"{fmt(m['records_sent_to_model'])} | {fmt(m['safe_automated_resolution'])} |")
    lines += ["", "## Unsafe outcomes by kind (cases)", "", "| Rung | Model | " + " | ".join(kinds) + " |", "|---|---|" + "---|" * len(kinds)]
    for rung in [*RUNGS, "proposed"]:
        for mode in ("scripted", "adversarial"):
            by = out[(rung, mode)]["unsafe_by_type"]
            lines.append(f"| {label[rung]} | {'ideal' if mode == 'scripted' else 'bad'} | " + " | ".join(str(by.get(k, 0)) for k in kinds) + " |")
    md = "\n".join(lines) + "\n"
    Path("eval/reports").mkdir(parents=True, exist_ok=True)
    Path("eval/reports/ABLATION.md").write_text(md, encoding="utf-8")
    Path("eval/reports/ablation.json").write_text(json.dumps({f"{r}/{m}": {k: v[k] for k in HEADLINE} for (r, m), v in out.items()}, indent=2), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
