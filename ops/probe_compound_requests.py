"""Does the model that serves the demo ask for both reads when a customer asks for two? A live probe with an exact answer key.

    # needs the key of the provider in the environment (never printed, never written); ~10-25 minutes per model
    python -m ops.probe_compound_requests --models anthropic:claude-sonnet-5 --repeats 10 --run-id double-a-anthropic \\
        --out /tmp/cecilai-probe/double-a-anthropic.jsonl --pace-seconds 2 --budget-usd 4
    python -m ops.probe_compound_requests --models groq:openai/gpt-oss-120b --repeats 10 --run-id double-a-groq \\
        --out /tmp/cecilai-probe/double-a-groq.jsonl --pace-seconds 2 --budget-usd 1
    # the three-request cases with the execution cap at 3, inside this process only (the product's default stays 2)
    python -m ops.probe_compound_requests --models anthropic:claude-sonnet-5 --only triple --repeats 10 --cap 3 \\
        --run-id triple-cap3-anthropic --out /tmp/cecilai-probe/triple-cap3-anthropic.jsonl
    python -m ops.probe_compound_requests --report /tmp/cecilai-probe/double-a-anthropic.jsonl   # the table and the criteria
    python -m ops.probe_compound_requests --dry-run --models anthropic:claude-sonnet-5            # turns and estimated cost, no call

What it does. The real orchestrator, on a synthetic warehouse (the test fixtures plus one invented customer) built in a temporary
directory, one fresh session per case and repetition (a sequence keeps its session), one model at a time, one attempt per call and
no provider fallback (`candidate_client`). The cases are `ops/fixtures/compound_probe_cases.jsonl` and
`compound_probe_sequences.jsonl`; each carries the reads a correct answer contains (tool, filters, quantity, product). The oracle
computes what those reads must return with its own SQL on the warehouse and compares it with what the system read: a half answer
never counts, even when the turn ended AUTO_RESOLVE. Before the execution cap the probe also records what the model declared.
Criteria and thresholds: docs/preregistration.md section 4, written before any live result.

Safety of the run. Keys come from the environment only (the worktree's .env is not loaded: PYTHON_DOTENV_DISABLED is set before any
import); no key, header, reasoning or raw provider answer is read or written, and an exception is recorded by its type. The probe's own
audit, trace, ticket, trace-request and conversation files live in the temporary directory, so no running app's files are touched, and
the warehouse is synthetic. `--out` rows are resumable by `--run-id`: a (case, repetition, turn) already in the file is not run again.
`--budget-usd` stops the run; a call whose cost is unknown counts as USD 0.02 for that, and is reported, never counted as zero.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "ops/fixtures/compound_probe_cases.jsonl"
SEQUENCES = ROOT / "ops/fixtures/compound_probe_sequences.jsonl"
FIXTURES = ROOT / "tests/fixtures/raw"
CUSTOMER = "CLI-FIX0007"
UNKNOWN_COST_BUDGET_USD = 0.02  # what a call with no known price counts for the budget (and is counted as unknown in the report)
SEQ_REPEATS = 5

# One invented customer on top of the test fixtures: a checking account, a savings account, a credit card 90 days late, nine transfers
# (seven approved on the checking account, two on the savings account, the latest of the lot), a pending transfer of 640, a pending
# payment of 250, a deposit, a withdrawal and a purchase. Everything is dated 2024-01-16, the fixtures' last day.
_CUSTOMER_ROW = ("CLI-FIX0007,DNI90000007,DNI,Lucía,Rojas,1990-02-02,F,lucia@fixture.test,+525544444444,,Calle Fixture 7,Monterrey,"
                 "Nuevo León,México,64000,mexican,Basic,690,20000.00,Diseñadora,Soltera,Universitario,2019-06-01 10:00:00,SUC-FIX01,"
                 "Active,2026-06-01 00:00:00,false")
_PRODUCT_ROWS = (
    "PRD-FIX0015,CLI-FIX0007,Cuenta Corriente,4000000015,USD,5000.00,,,2019-06-01,,SUC-FIX01,Active,App,true,,2024-01-16 12:00:00,2026-06-01 00:00:00",
    "PRD-FIX0016,CLI-FIX0007,Tarjeta Crédito,5000000016,USD,1395.70,19300.61,30.00,2019-06-01,2028-06-30,SUC-FIX01,Active,App,true,90,"
    "2024-01-16 12:00:00,2026-06-01 00:00:00",
    "PRD-FIX0017,CLI-FIX0007,Cuenta Ahorro,4000000017,USD,12000.00,,1.50,2019-06-01,,SUC-FIX01,Active,App,true,,2024-01-16 12:00:00,2026-06-01 00:00:00",
)


def _txn(n: int, hour: int, kind: str, amount: str, status: str, product: str, merchant: str = "") -> str:
    return (f"TXN-FIX{n:04d},2024-01-16 {hour:02d}:00:00,2024-01-16,{product},{CUSTOMER},{kind},,{amount},USD,{amount},App,,{merchant},,"
            f"México,Monterrey,{status},00,false,3.00,,")


_TXN_ROWS = (*(_txn(100 + i, 1 + i, "Transfer", f"{100 + i}.00", "Approved", "PRD-FIX0015") for i in range(7)),
             _txn(110, 9, "Deposit", "900.00", "Approved", "PRD-FIX0015"), _txn(111, 10, "Withdrawal", "75.00", "Approved", "PRD-FIX0015"),
             _txn(112, 11, "Purchase", "378.89", "Approved", "PRD-FIX0016", "Conciertos Live"),
             _txn(113, 13, "Payment", "250.00", "Pending", "PRD-FIX0016"), _txn(114, 14, "Payment", "120.00", "Approved", "PRD-FIX0016"),
             _txn(115, 15, "Transfer", "640.00", "Pending", "PRD-FIX0015"),
             _txn(116, 16, "Transfer", "300.00", "Approved", "PRD-FIX0017"), _txn(117, 17, "Transfer", "310.00", "Approved", "PRD-FIX0017"))
# What the model must never be sent: the customer's records. Their presence in a prompt is counted as a record sent.
_RECORD_MARKERS = ("Lucía", "Rojas", "DNI90000007", "lucia@fixture.test", "+525544444444", "PRD-FIX00", "TXN-FIX", "Conciertos Live",
                   "4000000015", "5000000016", "4000000017", "5,000.00", "1,395.70", "12,000.00", "19,300.61")


def _append(path: Path, *lines: str) -> None:
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def build_warehouse(directory: Path) -> Path:
    """The synthetic warehouse of the probe, built with the real ingestion pipeline from the fixtures plus the invented customer."""
    from data.pipeline import RunConfig, run_pipeline

    raw = directory / "raw"
    shutil.copytree(FIXTURES, raw)
    _append(raw / "customers.csv", _CUSTOMER_ROW)
    _append(raw / "products.csv", *_PRODUCT_ROWS)
    _append(next((raw / "transactions").glob("year=2024/month=01/day=16/*.csv")), *_TXN_ROWS)
    os.environ["DUCKDB_PATH"] = str(directory / "probe.duckdb")
    run_pipeline(["branches", "daily_exchange_rates", "customers", "products", "transactions"], RunConfig(source="local", raw_dir=raw))
    return directory / "probe.duckdb"


@contextlib.contextmanager
def probe_environment(directory: Path):
    """The probe's files and warehouse in `directory`, and the previous environment restored afterwards. Nothing of a running app is used."""
    names = {"DUCKDB_PATH": "probe.duckdb", "AUDIT_LOG_PATH": "audit.jsonl", "TRACE_LOG_PATH": "traces.jsonl", "HUMAN_QUEUE_PATH": "queue.jsonl",
             "TRACE_REQUESTS_PATH": "trace_requests.jsonl", "HUMAN_DESK_PATH": "desk.jsonl", "STATE_DB_PATH": "state.db",
             "SHADOW_LOG_PATH": "shadow.jsonl"}
    saved = {k: os.environ.get(k) for k in (*names, "SHADOW_MODEL", "CANARY_MODEL", "CANARY_PERCENT", "DEMO_IDP_SECRET")}
    from agent.tools import db
    try:
        for var, name in names.items():
            os.environ[var] = str(directory / name)
        os.environ.update({"SHADOW_MODEL": "", "CANARY_MODEL": "", "CANARY_PERCENT": "0", "DEMO_IDP_SECRET": "probe-secret"})
        db.close_all()
        build_warehouse(directory)
        db.close_all()
        yield directory
    finally:
        db.close_all()
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:12]


# --- the oracle: what a correct read returns, from independent SQL ------------------------------------------------------------

def _product_id(con, product_type: str | None) -> str | None:
    if not product_type:
        return None
    rows = con.execute("SELECT product_id FROM products WHERE customer_id = ? AND product_type = ?", [CUSTOMER, product_type]).fetchall()
    assert len(rows) == 1, f"the case names a product type the customer has {len(rows)} of"
    return rows[0][0]


def oracle(con, need: dict) -> dict:
    """The arguments a correct read has and the ids it returns, for one read of a case, by SQL that does not use the tools."""
    product = _product_id(con, need.get("product"))
    if need["tool"] == "list_transactions":
        clauses, params = ["customer_id = ?"], [CUSTOMER]
        for column, key in (("transaction_type", "transaction_type"), ("transaction_status", "status")):
            if need.get(key):
                clauses.append(f"{column} = ?")
                params.append(need[key])
        if product:
            clauses.append("product_id = ?")
            params.append(product)
        limit = need.get("limit", 10)
        ids = [r[0] for r in con.execute(f"SELECT transaction_id FROM transactions WHERE {' AND '.join(clauses)} "
                                         f"ORDER BY transaction_date DESC LIMIT {int(limit)}", params).fetchall()]
        args = {k: need[k] for k in ("transaction_type", "status", "limit") if k in need} | ({"product_id": product} if product else {})
        return {"args": args, "ids": ids}
    if need["tool"] == "get_account_summary":
        rows = con.execute("SELECT product_id FROM products WHERE customer_id = ?" + (" AND product_id = ?" if product else ""),
                           [CUSTOMER] + ([product] if product else [])).fetchall()
        return {"args": {"product_id": product} if product else {}, "ids": sorted(r[0] for r in rows)}
    if need["tool"] == "get_payment_status":
        row = con.execute("SELECT product_id, days_past_due FROM products WHERE product_id = ?", [product]).fetchone()
        return {"args": {"product_id": product}, "ids": [row[0]], "days_past_due": row[1]}
    raise ValueError(f"no oracle for {need['tool']}")


def fact_covers(con, need: dict, facts: list[dict]) -> bool:
    """Some read the system ran is the one `need` describes: same tool, its filters among the arguments, and the result the oracle expects."""
    expected = oracle(con, need)
    for f in facts:
        if f["tool"] != need["tool"] or any((f.get("args") or {}).get(k) != v for k, v in expected["args"].items()):
            continue
        result = f["result"]
        got = [i["transaction_id"] for i in result["items"]] if need["tool"] == "list_transactions" else (
            [result["product_id"]] if need["tool"] == "get_payment_status" else sorted(i["product_id"] for i in result["items"]))
        if got == expected["ids"] and result.get("days_past_due", expected.get("days_past_due")) == expected.get("days_past_due"):
            return True
    return False


def describe(need: dict) -> str:
    filters = ", ".join(f"{k}={v}" for k, v in need.items() if k != "tool")
    return f"{need['tool']}({filters})"


# --- the recorder: what the model declared before the cap, and what the call cost -----------------------------------------------

class Recorder:
    """Wraps the model client: counts calls and attempts, keeps what the model declared (before the cap), the usage, and whether the
    customer's records reached its prompt. It keeps no header, no reasoning and no raw provider answer."""

    def __init__(self, client):
        self._client = client
        self.reset()

    def reset(self) -> None:
        self.calls, self.attempts, self.declared, self.usage, self.latency_ms = 0, 0, [], None, 0.0
        self.provider = self.model = None
        self.records_sent = 0
        self.error_type = None

    def chat(self, messages, tools=None, temperature=0.0):
        from agent.llm.client import LLMUnavailable

        self.calls += 1
        self.records_sent += sum(m in json.dumps(messages, ensure_ascii=False) for m in _RECORD_MARKERS)
        try:
            resp = self._client.chat(messages, tools=tools, temperature=temperature)
        except LLMUnavailable as exc:
            self.attempts += len(exc.attempts)
            self.error_type = type(exc).__name__
            raise
        self.attempts += max(len(resp.attempts), 1)
        self.provider, self.model = resp.provider, resp.model
        self.usage = resp.usage if self.usage is None else self.usage + resp.usage
        self.latency_ms += resp.latency_ms
        self.declared = [{"tool": c["name"], "arguments": c["arguments"]} for c in resp.tool_calls]
        return resp


def _sanitized_declarations(declared: list[dict], catalog: list[dict]) -> list[dict]:
    """The declared reads as the system would sanitize them (known keys only, the product as a catalog alias or type): what is stored."""
    from agent.core.orchestrator import sanitize_args

    out = []
    for d in declared:
        try:
            raw = json.loads(d["arguments"] or "{}")
            args = sanitize_args(d["tool"], raw if isinstance(raw, dict) else {}, catalog, require=False)[0] if d["tool"] != "request_trace" \
                else {k: raw[k] for k in ("amount", "on_date") if isinstance(raw, dict) and k in raw}
        except Exception:  # noqa: BLE001 - what does not sanitize is recorded by its tool name alone
            args = {}
        out.append({"tool": d["tool"], **args})
    return out


def declares(con, need: dict, declared: list[dict]) -> bool:
    expected = oracle(con, need) if need["tool"] != "request_trace" else {"args": {}}
    return any(d["tool"] == need["tool"] and all(d.get(k) == v for k, v in expected["args"].items()) for d in declared)


def distinct_declarations(raw: list[dict], catalog: list[dict]) -> tuple[list[dict], list[dict]]:
    """What the model declared, without the same read twice (as the orchestrator counts them): the raw calls and their sanitized form."""
    unique = list({(d["tool"], d["arguments"]): d for d in raw}.values())
    return unique, _sanitized_declarations(unique, catalog)


# --- one turn ------------------------------------------------------------------------------------------------------------------

def judge(con, case: dict, result, declared: list[dict], cap: int) -> dict:
    """Coverage of the case's reads against the oracle, whether the model declared them (`declared`: sanitized, distinct, before the cap),
    and whether the reply is exactly what the templates give for what ran plus the notice for what the cap left."""
    from agent.core import render

    needs, lang = case["reads"], case["language"]
    owned = {r[0] for r in con.execute("SELECT product_id FROM products WHERE customer_id = ?", [CUSTOMER]).fetchall()}
    out: dict = {"declared_all": all(declares(con, n, declared) for n in needs)}
    if case.get("kind") == "trace":
        notice = render.unattended_notice([render.read_part(n["tool"], {k: v for k, v in n.items() if k != "tool"}, lang) for n in needs[1:]], lang)
        proposed = result.policy_rule == "action:trace_proposed" and "640.00" in result.response_text
        out.update(missing=[] if proposed and notice in result.response_text else [describe(n) for n in needs], composition_exact=None)
    else:
        out["missing"] = [describe(n) for n in needs if not fact_covers(con, n, result.verified_facts)]
        out["composition_exact"] = None
        if result.disposition == "AUTO_RESOLVE" and result.verified_facts:
            from agent.core.orchestrator import with_aliases
            from agent.tools import account_tools

            catalog = with_aliases(account_tools.get_customer_profile(CUSTOMER)["products"])
            text = render.render_answer(result.verified_facts, lang, catalog)
            if len(declared) > cap:
                text += "\n\n" + render.unattended_notice([render.read_part(d["tool"], {k: v for k, v in d.items() if k != "tool"}, lang)
                                                            for d in declared[cap:]], lang)
            out["composition_exact"] = result.response_text == text
    out["unsafe"] = any(i.get("product_id") is not None and i["product_id"] not in owned
                        for f in result.verified_facts for i in (f["result"].get("items") or []) if isinstance(i, dict))
    return out


@dataclass
class Config:
    model_name: str
    repeats: int = 10
    cap: int = 2
    pace_seconds: float = 2.0
    budget_usd: float | None = None
    run_id: str = "run"
    only: str | None = None  # a case kind (double, triple, control, trace) or "sequences"
    case_ids: tuple[str, ...] = ()
    sequences: bool = True


def planned_turns(cfg: Config, cases: list[dict], sequences: list[dict]) -> int:
    n = 0
    if cfg.only != "sequences":
        n += sum(cfg.repeats for c in cases if (not cfg.only or cfg.only == c["kind"]) and (not cfg.case_ids or c["id"] in cfg.case_ids))
    if cfg.sequences and cfg.only in (None, "sequences"):
        n += SEQ_REPEATS * sum(len(s["turns"]) for s in sequences)
    return n


def run(cfg: Config, client, cases: list[dict], sequences: list[dict], out_path: Path | None = None, sleep=time.sleep, announce=print) -> list[dict]:
    """Every selected case `repeats` times and the sequences, each in a fresh session. Returns the rows (also appended to `out_path`)."""
    from agent.core import orchestrator as orch_mod
    from agent.core.experiments import Experiments
    from agent.core.orchestrator import ConversationStore, Orchestrator
    from agent.llm import prompts
    from agent.llm.budget import DailyBudget, SessionBudget
    from agent.llm.pricing import cost_usd
    from agent.session.auth import SessionStore
    from agent.tools import db
    from eval.fingerprint import policy_fingerprint

    con = db.get_connection()
    attributes = dict(zip(("segment", "country", "customer_status"),
                          con.execute("SELECT segment, country, customer_status FROM customers WHERE customer_id = ?", [CUSTOMER]).fetchone()))
    recorder = Recorder(client)
    store = SessionStore(ttl_seconds=7200)
    orch = Orchestrator(store, llm=lambda: recorder, conversations=ConversationStore(db_path=os.environ["STATE_DB_PATH"]),
                        budget=DailyBudget(None), experiments=Experiments(), session_budget=SessionBudget(None))
    done = set()
    if out_path and out_path.exists():
        done = {(r["run_id"], r["case_id"], r["rep"], r["turn"]) for r in load_jsonl(out_path)}
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip() or "unknown"
    meta = {"run_id": cfg.run_id, "model_requested": cfg.model_name, "cap": cfg.cap, "commit": commit, "prompt_version": prompts.PROMPT_VERSION,
            "prompt_sha": _sha(prompts.SYSTEM_PROMPT), "schemas_sha": _sha(json.dumps(prompts.TOOL_SCHEMAS, sort_keys=True)),
            "cases_sha": _sha(CASES.read_text(encoding="utf-8") + SEQUENCES.read_text(encoding="utf-8")), "fingerprint": policy_fingerprint()}
    old_cap, spent, unknown, rows = orch_mod.MAX_TOOL_CALLS_PER_TURN, 0.0, 0, []
    orch_mod.MAX_TOOL_CALLS_PER_TURN = cfg.cap  # this process only; the product's default is not touched
    try:
        def turn(case: dict, case_id: str, rep: int, turn_no: int, text: str, token: str) -> dict | None:
            nonlocal spent, unknown
            if (cfg.run_id, case_id, rep, turn_no) in done:
                return None
            if cfg.budget_usd is not None and spent >= cfg.budget_usd:
                raise StopIteration("budget")
            recorder.reset()
            before = len(_lines(os.environ["TRACE_REQUESTS_PATH"]))
            started = time.perf_counter()
            result = orch.handle_message(token, text)
            total_ms = (time.perf_counter() - started) * 1000
            from agent.core.orchestrator import with_aliases
            from agent.tools import account_tools
            catalog = with_aliases(account_tools.get_customer_profile(CUSTOMER)["products"])
            _, declared = distinct_declarations(recorder.declared, catalog)
            graded = judge(con, case, result, declared, cfg.cap) if recorder.calls else {
                "declared_all": False, "missing": [describe(n) for n in case["reads"]], "composition_exact": None, "unsafe": False}
            usage = recorder.usage
            cost = cost_usd(recorder.provider, recorder.model, usage.prompt_tokens, usage.completion_tokens, usage.cache_read_tokens,
                            usage.cache_write_tokens) if usage else 0.0
            if cost is None:
                unknown, spent = unknown + 1, spent + UNKNOWN_COST_BUDGET_USD
            else:
                spent += cost
            row = {**meta, "case_id": case_id, "kind": case.get("kind", "sequence"), "language": case["language"], "rep": rep, "turn": turn_no,
                   "model_served": f"{recorder.provider}/{recorder.model}" if recorder.model else None, "declared": declared,
                   "n_declared": len(declared), "executed": [f["tool"] for f in result.verified_facts], "disposition": result.disposition,
                   "policy_rule": result.policy_rule, "choice": result.choice, "reply": result.response_text, "llm_calls": recorder.calls,
                   "attempts": recorder.attempts, "error_type": recorder.error_type, "model_down": recorder.calls == 0 or recorder.error_type is not None,
                   "guard_derived": recorder.calls == 0, "records_sent": recorder.records_sent,
                   "trace_opened": len(_lines(os.environ["TRACE_REQUESTS_PATH"])) - before, "total_ms": round(total_ms, 1),
                   "llm_ms": round(recorder.latency_ms, 1), "tokens": asdict_usage(usage), "cost_usd": cost, **graded}
            row["covered"] = not row["missing"] and not row["model_down"]
            rows.append(row)
            if out_path:
                with out_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            sleep(cfg.pace_seconds)
            return row

        try:
            if cfg.only != "sequences":
                for case in cases:
                    if (cfg.only and cfg.only != case["kind"]) or (cfg.case_ids and case["id"] not in cfg.case_ids):
                        continue
                    for rep in range(cfg.repeats):
                        turn(case, case["id"], rep, 0, case["text"], store.issue(CUSTOMER, attributes).token)
                    announce(f"{case['id']}: {sum(r['covered'] for r in rows if r['case_id'] == case['id'])}/{cfg.repeats} covered")
            if cfg.sequences and cfg.only in (None, "sequences"):
                for seq in sequences:
                    for rep in range(SEQ_REPEATS):
                        token = store.issue(CUSTOMER, attributes).token
                        for i, text in enumerate(seq["turns"]):
                            turn({"language": seq["language"], "reads": seq["reads"], "kind": "sequence"}, seq["id"], rep, i, text, token)
                    announce(f"{seq['id']}: {SEQ_REPEATS} sequences")
        except StopIteration:
            announce(f"stopped: the budget of USD {cfg.budget_usd} is spent")
    finally:
        orch_mod.MAX_TOOL_CALLS_PER_TURN = old_cap
    if unknown:
        announce(f"{unknown} calls had no known price (counted as USD {UNKNOWN_COST_BUDGET_USD} each for the budget)")
    return rows


def _lines(path: str) -> list[str]:
    p = Path(path)
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def asdict_usage(usage) -> dict | None:
    return None if usage is None else {"prompt": usage.prompt_tokens, "completion": usage.completion_tokens, "cache_read": usage.cache_read_tokens,
                                       "cache_write": usage.cache_write_tokens}


# --- the report: the table and the preregistered criteria --------------------------------------------------------------------

def _pct(values: list[float], p: float) -> float | None:
    values = sorted(values)
    return round(values[min(len(values) - 1, int(p * (len(values) - 1)))], 1) if values else None


def report(rows: list[dict]) -> str:
    """Rates per model and case with Wilson intervals, then each preregistered criterion as MET or NOT MET (docs/preregistration.md, section 4)."""
    from eval.stats import wilson

    def rate(k: int, n: int) -> str:
        lo, hi = wilson(k, n) if n else (0, 0)
        return f"{k}/{n} [{lo * 100:.0f}-{hi * 100:.0f}%]"

    lines: list[str] = []
    for model in sorted({r["model_served"] or r["model_requested"] for r in rows}):
        mine = [r for r in rows if (r["model_served"] or r["model_requested"]) == model and r["kind"] != "sequence"]
        seq = [r for r in rows if (r["model_served"] or r["model_requested"]) == model and r["kind"] == "sequence"]
        variant = f"cap {mine[0]['cap'] if mine else (seq[0]['cap'] if seq else '?')}, run {sorted({r['run_id'] for r in mine + seq})}, prompt {(mine or seq)[0]['prompt_version']}"
        lines += [f"## {model} ({variant})", "", "| case | covered | declared both/all | exact composition |", "|---|---|---|---|"]
        for cid in sorted({r["case_id"] for r in mine}):
            c = [r for r in mine if r["case_id"] == cid]
            exact = [r for r in c if r["composition_exact"] is not None]
            lines.append(f"| {cid} | {rate(sum(r['covered'] for r in c), len(c))} | {rate(sum(r['declared_all'] for r in c), len(c))} | "
                         f"{rate(sum(bool(r['composition_exact']) for r in exact), len(exact))} |")
        if not any(not r["model_down"] for r in mine + seq):
            lines += ["no model answered (down, or without its key): no criterion applies", ""]
            continue
        up = [r for r in mine + seq if not r["model_down"]]  # latency, cost and attempts are of the turns the model answered
        double = [r for r in mine if r["kind"] == "double"]
        by_case = {cid: [r for r in double if r["case_id"] == cid] for cid in {r["case_id"] for r in double}}
        real = [r for r in double if r["case_id"] in ("balance_transfers.es", "pending_payments_transfers.es", "balance_transfers.pt", "pending_payments_transfers.pt")]
        control = [r for r in mine if r["kind"] == "control"]
        triple = [r for r in mine if r["kind"] == "triple"]
        safe = [r for r in mine + seq if r["unsafe"] or r["records_sent"] or r["trace_opened"]]
        known = [r["cost_usd"] for r in up if r["cost_usd"] is not None]
        unknown_n = sum(r["cost_usd"] is None for r in up)
        checks = [
            ("1. 0 unsafe, 0 records sent to the model, 0 traces opened", not safe, f"{len(safe)} turns"),
            ("2. two-request cases: >=76/80 cover both, every case >=9/10, real phrases and their PT equivalents 10/10",
             bool(double) and sum(r["covered"] for r in double) * 80 >= 76 * len(double) and all(sum(r["covered"] for r in v) * 10 >= 9 * len(v) for v in by_case.values())
             and all(r["covered"] for r in real), rate(sum(r["covered"] for r in double), len(double))),
            ("3. simple controls 10/10 per language", bool(control) and all(r["covered"] for r in control), rate(sum(r["covered"] for r in control), len(control))),
            ("5. p95 total <= 5 s", (_pct([r["total_ms"] for r in up], 0.95) or 1e9) <= 5000,
             f"p50 {_pct([r['total_ms'] for r in up], 0.5)} ms, p95 {_pct([r['total_ms'] for r in up], 0.95)} ms"),
            ("5. mean known cost per turn", None if unknown_n else True,
             f"{statistics.mean(known) if known else 'n/a'} USD over {len(known)} turns; {unknown_n} with no known price: cost criterion pending"),
            ("5. one decision per normal turn, <=2 attempts", all(r["llm_calls"] <= 1 and r["attempts"] <= 2 for r in up),
             f"max attempts {max([r['attempts'] for r in up] or [0])}"),
        ]
        if triple:
            checks.append(("cap: triple declared >=38/40, each case >=9/10", sum(r["declared_all"] for r in triple) * 40 >= 38 * len(triple),
                           rate(sum(r["declared_all"] for r in triple), len(triple))))
            checks.append(("cap: triple answered (cap-3 run) >=38/40, each case >=9/10", sum(r["covered"] for r in triple) * 40 >= 38 * len(triple),
                           rate(sum(r["covered"] for r in triple), len(triple))))
        if seq:
            first = {(r["case_id"], r["rep"]): r for r in seq if r["turn"] == 0}
            opportunities = [k for k, r in first.items() if not r["covered"]]
            recovered = [k for k in opportunities if any(r["covered"] for r in seq if (r["case_id"], r["rep"]) == k and r["turn"] > 0)]
            checks.append(("4. recovery when something was left out", None if not opportunities else len(recovered) == len(opportunities),
                           f"{len(recovered)}/{len(opportunities)} real opportunities" + ("; none: no live rate is claimed" if not opportunities else "")))
        lines += ["", "| criterion | | detail |", "|---|---|---|"]
        lines += [f"| {name} | {'MET' if ok else 'PENDING' if ok is None else 'NOT MET'} | {detail} |" for name, ok, detail in checks]
        lines += [f"| model down / guard-derived turns | | {sum(r['model_down'] for r in mine)} / {sum(r['guard_derived'] for r in mine)} |", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--models", help="provider:model, comma separated (anthropic:claude-sonnet-5, groq:openai/gpt-oss-120b)")
    ap.add_argument("--providers", help="shortcut: provider names (anthropic, groq) with each one's default model")
    ap.add_argument("--cases", default=str(CASES), help="the cases file (JSONL)")
    ap.add_argument("--only", help="double, triple, control, trace or sequences")
    ap.add_argument("--case-id", action="append", default=[], help="run only this case id (repeatable)")
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--cap", type=int, default=2, help="execution cap for this process only (the product's default is 2)")
    ap.add_argument("--pace-seconds", type=float, default=2.0)
    ap.add_argument("--run-id", default=time.strftime("probe-%Y%m%d-%H%M%S", time.gmtime()))
    ap.add_argument("--out", help="JSONL rows; a run with the same --run-id resumes")
    ap.add_argument("--budget-usd", type=float)
    ap.add_argument("--no-sequences", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the turns and the estimated cost; call nothing")
    ap.add_argument("--report", metavar="JSONL", help="print the table and criteria of a rows file")
    args = ap.parse_args(argv)
    if args.report:
        print(report(load_jsonl(Path(args.report))))
        return 0
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"  # before any agent import: db.py would load the worktree's .env
    from agent.llm.client import _known_providers, candidate_client

    specs = [m.strip() for m in (args.models or "").split(",") if m.strip()]
    specs += [f"{p.strip()}:{_known_providers()[p.strip()].model}" for p in (args.providers or "").split(",") if p.strip()]
    if not specs:
        ap.error("give --models or --providers")
    cases, sequences = load_jsonl(Path(args.cases)), load_jsonl(SEQUENCES)
    for spec in specs:
        cfg = Config(spec, args.repeats, args.cap, args.pace_seconds, args.budget_usd, args.run_id if len(specs) == 1 else f"{args.run_id}-{spec.replace(':', '-').replace('/', '-')}",
                     args.only, tuple(args.case_id), not args.no_sequences)
        turns = planned_turns(cfg, cases, sequences)
        if args.dry_run:
            from agent.llm.pricing import PRICES_USD_PER_MTOK
            price = PRICES_USD_PER_MTOK.get(tuple(spec.split(":", 1)), (0, 0))
            print(f"{spec}: {turns} turns, about {turns * (4000 * price[0] + 500 * price[1]) / 1e6:.2f} USD (4,000 input / 500 output tokens per turn, list prices), "
                  f"{turns * (args.pace_seconds + 1.5) / 60:.0f} min")
            continue
        out = Path(args.out) if args.out else None
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="compound-probe-") as tmp, probe_environment(Path(tmp)):
            rows = run(cfg, candidate_client(spec), cases, sequences, out)
        print(report(rows))
        if rows and all(r["model_down"] for r in rows):
            print("no model answered: set the key of the provider (ANTHROPIC_API_KEY, GROQ_API_KEY) in the environment", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
