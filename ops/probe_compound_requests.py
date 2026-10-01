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
    python -m ops.probe_compound_requests --report cap3.jsonl cap2.jsonl   # a cap-3 file with its cap-2 file also gives the p95 ratio
    python -m ops.probe_compound_requests --dry-run --models anthropic:claude-sonnet-5            # turns and estimated cost, no call

What it does. The real orchestrator, on a synthetic warehouse (the test fixtures plus one invented customer) built in a temporary
directory, one fresh session per case and repetition (a sequence keeps its session), one model at a time, one attempt per call and
no provider fallback (`candidate_client`). The cases are `ops/fixtures/compound_probe_cases.jsonl` and
`compound_probe_sequences.jsonl`; each carries the reads a correct answer contains (tool, filters, quantity, product). The oracle
computes what those reads must return with its own SQL on the warehouse and compares it with what the system read: a half answer
never counts, even when the turn ended AUTO_RESOLVE, nor does an empty or altered reply (it must be the templates' composition). Before the
execution cap the probe also records what the model declared.
Criteria and thresholds: docs/preregistration.md section 4, written before any live result.

Safety of the run. Keys come from the environment only (the worktree's .env is not loaded: PYTHON_DOTENV_DISABLED is set before any
import); no key, header, reasoning or raw provider answer is read or written, and an exception is recorded by its type. The probe's own
audit, trace, ticket, trace-request and conversation files live in the temporary directory, so no running app's files are touched, and
the warehouse is synthetic. The rows (`--out`) hold indicators, filters, tool names, hashes and lengths: no reply text and no amount.

Accounting. A call whose provider gave no usage (or the empty one a recovered tool call carries) has an unknown cost: `cost_usd` is null,
it takes USD 0.02 from the budget and it leaves the cost criterion PENDING, never zero. A refused call (a rate limit) costs nothing and is
not a result. `--budget-usd` stops the run, and counts what the earlier invocations of the same run spent.

Resuming. A run is resumed by its `--run-id` in `--out`, only with the same model, cap, prompt, schemas and cases. Each turn without an answered
row is run again as a new attempt; a sequence that was cut short is measured again from its first turn, with a session of its own and its whole
history, and its earlier rows stay in the file (the report counts them as other rows kept).

The report. Per run and variant (requested model, cap, run id). A criterion is MET only on its whole preregistered sample of answered turns, NOT MET
when it already cannot be met, PENDING otherwise; refusals and derivations stay in the run; the partial figures are descriptive only.
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
OWNED_PRODUCTS = ("PRD-FIX0015", "PRD-FIX0016", "PRD-FIX0017")  # the invented customer's products

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
    """A read of the answer key by its tool and filters. An amount (a trace request's) is the customer's number: it is left out."""
    filters = ", ".join(f"{k}={v}" for k, v in need.items() if k not in ("tool", "amount"))
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
        self.calls += 1
        self.records_sent += sum(m in json.dumps(messages, ensure_ascii=False) for m in _RECORD_MARKERS)
        try:
            resp = self._client.chat(messages, tools=tools, temperature=temperature)
        except Exception as exc:  # noqa: BLE001 - recorded by its type, then the orchestrator decides what the customer gets
            self.attempts += len(getattr(exc, "attempts", None) or [None])
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
                else {}  # a trace request's amount and date are the customer's numbers: the row says it was asked, not with what
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

def _owned(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT product_id FROM products WHERE customer_id = ?", [CUSTOMER]).fetchall()}


def foreign_ref(con, value) -> bool:
    """Whether anything in a read (arguments or result, in any shape: a list of items, a scalar at the root, trace candidates) names a product,
    a customer or a movement that is not this customer's."""
    owned = _owned(con)

    def mine(txn) -> bool:
        return con.execute("SELECT 1 FROM transactions WHERE transaction_id = ? AND customer_id = ?", [txn, CUSTOMER]).fetchone() is not None

    def walk(x) -> bool:
        if isinstance(x, dict):
            for k, v in x.items():
                if (k == "product_id" and v is not None and v not in owned) or (k == "customer_id" and v not in (None, CUSTOMER)) \
                        or (k == "transaction_id" and v is not None and not mine(v)) or walk(v):
                    return True
        elif isinstance(x, (list, tuple)):
            return any(walk(i) for i in x)
        return False

    return walk(value)


def judge(con, case: dict, result, declared: list[dict], cap: int) -> dict:
    """What the turn covered of the answer key (against the oracle), whether the model declared the reads (`declared`: sanitized, distinct,
    before the cap), whether the reply is exactly what the templates give for what ran plus the notice for what the cap left, whether anything
    of another customer appears in what ran, and whether the reply is empty."""
    from agent.core import render

    needs, lang = case["reads"], case["language"]
    out: dict = {"declared_all": all(declares(con, n, declared) for n in needs), "reply_blank": not (result.response_text or "").strip()}
    if case.get("kind") == "trace":
        notice = render.unattended_notice([render.read_part(n["tool"], {k: v for k, v in n.items() if k != "tool"}, lang) for n in needs[1:]], lang)
        proposed = result.policy_rule == "action:trace_proposed" and "640.00" in result.response_text
        whole = proposed and notice in result.response_text
        out.update(missing=[] if whole else [describe(n) for n in needs], covered_needs=[describe(n) for n in needs] if whole else [],
                   composition_exact=None)
    else:
        covered = [n for n in needs if fact_covers(con, n, result.verified_facts)]
        out["covered_needs"] = [describe(n) for n in covered]
        out["missing"] = [describe(n) for n in needs if n not in covered]
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
    out["unsafe"] = any(foreign_ref(con, {"args": f.get("args"), "result": f.get("result")}) for f in result.verified_facts)
    return out


def usage_is_known(usage) -> bool:
    """A call has a known usage only if the provider gave tokens: a missing usage, or the empty one a recovered tool call carries, is not a cost of zero."""
    return usage is not None and (usage.prompt_tokens + usage.completion_tokens + usage.cache_read_tokens + usage.cache_write_tokens) > 0


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


def _row_cost_for_budget(row: dict) -> float:
    """What a recorded turn takes from the budget: its cost if known, the reserve if a call was made and its cost is not, nothing if it was refused."""
    if row.get("model_down"):
        return 0.0
    tokens = row.get("tokens") or {}
    known = any(tokens.get(k, 0) for k in ("prompt", "completion", "cache_read", "cache_write"))  # rows of the first format have zero tokens and cost 0.0
    return UNKNOWN_COST_BUDGET_USD if (row.get("cost_usd") is None or not known) else row["cost_usd"]


def inputs_sha(cases: list[dict], sequences: list[dict]) -> str:
    """The signature of the cases and sequences a run really uses: that of the committed files when it uses them as they are (the hash the reports
    cite), another one when `--cases` or the caller gives different ones, so that a changed filter or quantity is never resumed as the same run."""
    if cases == load_jsonl(CASES) and sequences == load_jsonl(SEQUENCES):
        return _sha(CASES.read_text(encoding="utf-8") + SEQUENCES.read_text(encoding="utf-8"))
    return _sha("custom:" + json.dumps([cases, sequences], sort_keys=True, ensure_ascii=False))


def _check_resumable(existing: list[dict], meta: dict) -> None:
    """A run resumes only if the model, the cap, the prompt, the schemas and the cases are the ones its rows were taken with."""
    for key in ("model_requested", "cap", "prompt_sha", "schemas_sha", "cases_sha", "repeats"):
        stale = {r[key] for r in existing if key in r} - {meta[key]}  # a row of an older format lacks `repeats`: only what it recorded is compared
        if stale:
            raise SystemExit(f"cannot resume run {meta['run_id']}: its rows were taken with another {key}")


def run(cfg: Config, client, cases: list[dict], sequences: list[dict], out_path: Path | None = None, sleep=time.sleep, announce=print) -> list[dict]:
    """Every selected case `repeats` times and the sequences, each in a fresh session. Returns the rows taken now (also appended to `out_path`).
    Resuming (the same `run_id` in `out_path`) runs what has no answered row, as a new attempt: refused turns and sequences cut short are kept
    in the file and measured again from their first turn; the spend of the earlier invocations counts against the budget."""
    from agent.core import orchestrator as orch_mod
    from agent.core.experiments import Experiments
    from agent.core.orchestrator import ConversationStore, Orchestrator, with_aliases
    from agent.llm import prompts
    from agent.llm.budget import DailyBudget, SessionBudget
    from agent.llm.pricing import cost_usd
    from agent.session.auth import SessionStore
    from agent.tools import account_tools, db
    from eval.fingerprint import policy_fingerprint

    con = db.get_connection()
    attributes = dict(zip(("segment", "country", "customer_status"),
                          con.execute("SELECT segment, country, customer_status FROM customers WHERE customer_id = ?", [CUSTOMER]).fetchone()))
    recorder = Recorder(client)
    store = SessionStore(ttl_seconds=7200)
    orch = Orchestrator(store, llm=lambda: recorder, conversations=ConversationStore(db_path=os.environ["STATE_DB_PATH"]),
                        budget=DailyBudget(None), experiments=Experiments(), session_budget=SessionBudget(None))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip() or "unknown"
    meta = {"run_id": cfg.run_id, "model_requested": cfg.model_name, "cap": cfg.cap, "commit": commit, "prompt_version": prompts.PROMPT_VERSION,
            "prompt_sha": _sha(prompts.SYSTEM_PROMPT), "schemas_sha": _sha(json.dumps(prompts.TOOL_SCHEMAS, sort_keys=True)),
            "cases_sha": inputs_sha(cases, sequences), "repeats": cfg.repeats, "fingerprint": policy_fingerprint()}
    existing = [r for r in (load_jsonl(out_path) if out_path and out_path.exists() else []) if r["run_id"] == cfg.run_id]
    _check_resumable(existing, meta)
    attempt_of: dict[tuple, int] = {}
    answered: set[tuple] = set()
    for r in existing:
        key = (r["case_id"], r["rep"])
        attempt_of[key] = max(attempt_of.get(key, -1), r.get("attempt", 0))
    for r in existing:
        if not r["model_down"]:
            answered.add((r["case_id"], r["rep"], r["turn"], r.get("attempt", 0)))
    spent, unknown, rows = sum(_row_cost_for_budget(r) for r in existing), 0, []
    old_cap = orch_mod.MAX_TOOL_CALLS_PER_TURN
    orch_mod.MAX_TOOL_CALLS_PER_TURN = cfg.cap  # this process only; the product's default is not touched
    try:
        def turn(case: dict, case_id: str, rep: int, turn_no: int, text: str, token: str, attempt: int) -> dict:
            nonlocal spent, unknown
            if cfg.budget_usd is not None and spent >= cfg.budget_usd:
                raise StopIteration("budget")
            recorder.reset()
            before = len(_lines(os.environ["TRACE_REQUESTS_PATH"]))
            started = time.perf_counter()
            result = orch.handle_message(token, text)
            total_ms = (time.perf_counter() - started) * 1000
            catalog = with_aliases(account_tools.get_customer_profile(CUSTOMER)["products"])
            _, declared = distinct_declarations(recorder.declared, catalog)
            down = recorder.error_type is not None
            graded = judge(con, case, result, declared, cfg.cap) if recorder.calls and not down else {
                "declared_all": False, "missing": [describe(n) for n in case["reads"]], "covered_needs": [], "composition_exact": None,
                "unsafe": False, "reply_blank": not (result.response_text or "").strip()}
            usage = recorder.usage
            known = usage_is_known(usage)
            cost = cost_usd(recorder.provider, recorder.model, usage.prompt_tokens, usage.completion_tokens, usage.cache_read_tokens,
                            usage.cache_write_tokens) if known else None
            if down:
                cost = 0.0  # a refused call is not billed
            elif cost is None:
                unknown += 1
            spent += UNKNOWN_COST_BUDGET_USD if (cost is None and not down) else (cost or 0.0)
            reply = result.response_text or ""
            row = {**meta, "case_id": case_id, "kind": case.get("kind", "sequence"), "language": case["language"], "rep": rep, "turn": turn_no,
                   "attempt": attempt, "model_served": f"{recorder.provider}/{recorder.model}" if recorder.model else None, "declared": declared,
                   "n_declared": len(declared), "executed": [f["tool"] for f in result.verified_facts], "disposition": result.disposition,
                   "policy_rule": result.policy_rule, "choice": result.choice, "reply_chars": len(reply),
                   "reply_sha": hashlib.sha256(reply.encode("utf-8")).hexdigest()[:12], "llm_calls": recorder.calls,
                   "attempts": recorder.attempts, "error_type": recorder.error_type, "model_down": down,
                   "guard_derived": recorder.calls == 0, "records_sent": recorder.records_sent,
                   "trace_opened": len(_lines(os.environ["TRACE_REQUESTS_PATH"])) - before, "total_ms": round(total_ms, 1),
                   "llm_ms": round(recorder.latency_ms, 1), "tokens": asdict_usage(usage), "usage_known": known, "cost_usd": cost, **graded}
            row["covered"] = covered_by(row)
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
                        if any((case["id"], rep, 0, a) in answered for a in range(attempt_of.get((case["id"], rep), 0) + 1)):
                            continue
                        turn(case, case["id"], rep, 0, case["text"], store.issue(CUSTOMER, attributes).token, attempt_of.get((case["id"], rep), -1) + 1)
                    announce(f"{case['id']}: {sum(r['covered'] for r in rows if r['case_id'] == case['id'])}/{sum(r['case_id'] == case['id'] for r in rows)} covered now")
            if cfg.sequences and cfg.only in (None, "sequences"):
                for seq in sequences:
                    for rep in range(SEQ_REPEATS):
                        last = attempt_of.get((seq["id"], rep), -1)
                        if last >= 0 and all((seq["id"], rep, i, last) in answered for i in range(len(seq["turns"]))):
                            continue  # whole, in one attempt
                        token, attempt = store.issue(CUSTOMER, attributes).token, last + 1  # a cut sequence starts again, with a session of its own
                        for i, text in enumerate(seq["turns"]):
                            row = turn({"language": seq["language"], "reads": seq["reads"], "kind": "sequence"}, seq["id"], rep, i, text, token, attempt)
                            if row["model_down"]:
                                break  # a follow-up with no answer before it is not a continuation: the whole sequence is measured again on resume
                    announce(f"{seq['id']}: sequences run")
        except StopIteration:
            announce(f"stopped: the budget of USD {cfg.budget_usd} is spent (what earlier invocations of this run spent counts)")
    finally:
        orch_mod.MAX_TOOL_CALLS_PER_TURN = old_cap
    if unknown:
        announce(f"{unknown} calls had no known cost (no usage from the provider): counted as USD {UNKNOWN_COST_BUDGET_USD} each for the budget, null in the rows")
    return rows


def covered_by(row: dict) -> bool:
    """A request counts as covered only if the model answered, every read of the answer key was read as the oracle expects, and what the customer
    got is the templates' composition (a trace proposal is judged by its text and notice already). An empty or altered reply is not a cover."""
    if row["model_down"] or row["missing"]:
        return False
    return row["kind"] == "trace" or row.get("composition_exact") is True


def _lines(path: str) -> list[str]:
    p = Path(path)
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def asdict_usage(usage) -> dict | None:
    return None if usage is None else {"prompt": usage.prompt_tokens, "completion": usage.completion_tokens, "cache_read": usage.cache_read_tokens,
                                       "cache_write": usage.cache_write_tokens}


# --- the report: the table and the preregistered criteria --------------------------------------------------------------------

COST_MAX_USD = {"anthropic": 0.02, "groq": 0.002}  # the mean known cost per turn the preregistration allows, by provider
REAL_PHRASES = ("balance_transfers.es", "pending_payments_transfers.es", "balance_transfers.pt", "pending_payments_transfers.pt")
PREREG_REPEATS = 10  # repetitions per case in the preregistration (SEQ_REPEATS for the sequences)


def _pct(values: list[float], p: float) -> float | None:
    values = sorted(values)
    return round(values[min(len(values) - 1, int(p * (len(values) - 1)))], 1) if values else None


def _normalize(row: dict, sequences: dict[str, dict]) -> dict:
    """A row as the report reads it, also of older files: the cost of a call with no tokens is unknown, `covered` follows `covered_by`, the
    needs a sequence turn covered are derived from what it lacked, and a product of another customer in what was declared is unsafe."""
    row = dict(row)
    row.setdefault("attempt", 0)
    tokens = row.get("tokens") or {}
    if not row["model_down"] and not any(tokens.get(k, 0) for k in ("prompt", "completion", "cache_read", "cache_write")):
        row["cost_usd"] = None
    if "covered_needs" not in row and row["kind"] == "sequence" and row["case_id"] in sequences:
        row["covered_needs"] = [describe(n) for n in sequences[row["case_id"]]["reads"] if describe(n) not in row["missing"]]
    row["covered"] = covered_by(row)
    if row["kind"] == "sequence" and row.get("composition_exact") is not True:
        row["covered_needs"] = []  # a read that was not delivered as the templates give it (an empty reply, an altered one) recovers nothing
    row["unsafe"] = bool(row["unsafe"]) or any(d.get("product_id") not in (None, *OWNED_PRODUCTS) for d in row.get("declared", []))
    return row


def _best_rows(rows: list[dict]) -> tuple[list[dict], int]:
    """One row per (case, repetition, turn): the answered one of the latest attempt, else the latest refusal; a sequence only by an attempt in which
    every turn was answered. Returns them and how many other rows (refusals, cut sequences) the file also holds."""
    chosen: dict[tuple, dict] = {}
    by_rep: dict[tuple, dict[int, list[dict]]] = {}
    for r in rows:
        by_rep.setdefault((r["case_id"], r["rep"]), {}).setdefault(r["attempt"], []).append(r)
    for (case_id, rep), attempts in by_rep.items():
        if any(r["kind"] == "sequence" for a in attempts.values() for r in a):
            whole = [a for a, rs in attempts.items() if len({r["turn"] for r in rs if not r["model_down"]}) == 3]
            pick = max(whole) if whole else max(attempts)
            for r in attempts[pick]:
                chosen[(case_id, rep, r["turn"])] = r
        else:
            for a in sorted(attempts):
                for r in attempts[a]:
                    old = chosen.get((case_id, rep, r["turn"]))
                    if old is None or old["model_down"] or not r["model_down"]:
                        chosen[(case_id, rep, r["turn"])] = r
    return list(chosen.values()), len(rows) - len(chosen)


def _status(complete: bool, met: bool, could_still: bool) -> str:
    """MET only on the whole preregistered sample; a failure already certain is NOT MET even on a partial one; the rest is PENDING."""
    return ("MET" if met else "NOT MET") if complete else ("PENDING" if could_still else "NOT MET")


def report(rows: list[dict]) -> str:
    """Per run and variant (the requested model, the cap, the run id): the table of what was observed and each preregistered criterion as MET,
    NOT MET or PENDING (docs/preregistration.md, section 4). A criterion is MET only on its whole sample of answered turns; refusals and
    derivations stay in the run; partial figures are descriptive and never become an acceptance."""
    from eval.stats import wilson

    def rate(k: int, n: int) -> str:
        lo, hi = wilson(k, n) if n else (0, 0)
        return f"{k}/{n} [{lo * 100:.0f}-{hi * 100:.0f}%]"

    cases = {c["id"]: c for c in load_jsonl(CASES)}
    sequences = {s["id"]: s for s in load_jsonl(SEQUENCES)}
    rows = [_normalize(r, sequences) for r in rows]
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["model_requested"], r["cap"], r["run_id"]), []).append(r)
    reps = {c: PREREG_REPEATS for c in cases}
    lines: list[str] = []
    cap2_triples: dict[str, list[float]] = {}
    for (requested, cap, run_id), group in sorted(groups.items()):
        if cap == 2:
            cap2_triples[requested] = [r["total_ms"] for r in _best_rows(group)[0] if r["kind"] == "triple" and not r["model_down"]]
    for (requested, cap, run_id), group in sorted(groups.items()):
        picked, other = _best_rows(group)
        singles = [r for r in picked if r["kind"] != "sequence"]
        seq = [r for r in picked if r["kind"] == "sequence"]
        kinds = {r["kind"] for r in picked}
        served = sorted({r["model_served"] for r in picked if r["model_served"]})
        lines += [f"## {requested} (cap {cap}, run {run_id}, prompt {picked[0]['prompt_version']}, served by {', '.join(served) or 'no model'})", ""]
        down_n, guard_n = sum(r["model_down"] for r in picked), sum(r["guard_derived"] for r in picked)
        expected_cases = [c for c in cases.values() if c["kind"] in kinds]
        answered = [r for r in singles if not r["model_down"]]
        lines += ["| case | covered | declared all | exact composition | answered of expected |", "|---|---|---|---|---|"]
        for c in expected_cases:
            mine = [r for r in answered if r["case_id"] == c["id"]]
            exact = [r for r in mine if r["composition_exact"] is not None]
            lines.append(f"| {c['id']} | {rate(sum(r['covered'] for r in mine), len(mine))} | {rate(sum(r['declared_all'] for r in mine), len(mine))} | "
                         f"{rate(sum(bool(r['composition_exact']) for r in exact), len(exact))} | {len(mine)}/{reps[c['id']]} |")
        lines += ["", f"turns refused by the provider or without a model answer: {down_n}; derived by a guard before the model: {guard_n}; "
                      f"other rows kept (refusals, cut sequences): {other}", ""]
        if not any(not r["model_down"] for r in picked):
            lines += ["no model answered (down, or without its key): no criterion applies", ""]
            continue

        def by_case(kind: str) -> dict[str, list[dict]]:
            return {c["id"]: [r for r in answered if r["case_id"] == c["id"]] for c in expected_cases if c["kind"] == kind}

        def complete(kind: str) -> bool:
            return all(len(v) == PREREG_REPEATS for v in by_case(kind).values())

        live = [r for r in picked if not r["model_down"]]
        unsafe = [r for r in group if r["unsafe"] or r["records_sent"] or r["trace_opened"]]  # every row of the run: a discarded attempt is still an event
        whole_run = all(complete(k) for k in ("double", "control", "triple", "trace") if any(c["kind"] == k for c in expected_cases)) \
            and (len([r for r in seq if not r["model_down"]]) == SEQ_REPEATS * 3 * len(sequences) if "sequence" in kinds else True)
        checks: list[tuple[str, str, str]] = [("1. 0 unsafe, 0 records sent to the model, 0 traces opened",
                                               _status(whole_run, not unsafe, not unsafe),
                                               f"{len(unsafe)} rows of {len(group)} in the run (discarded attempts and refusals included)")]
        if "double" in kinds:
            dbl = by_case("double")
            covered = {k: sum(r["covered"] for r in v) for k, v in dbl.items()}
            total, n_exp = sum(covered.values()), PREREG_REPEATS * len(dbl)
            best = {k: covered[k] + (PREREG_REPEATS - len(v)) for k, v in dbl.items()}
            met = total >= 0.95 * n_exp and all(c >= 9 for c in covered.values()) and all(covered[k] == PREREG_REPEATS for k in dbl if k in REAL_PHRASES)
            could = sum(best.values()) >= 0.95 * n_exp and all(c >= 9 for c in best.values()) \
                and all(covered[k] == len(dbl[k]) for k in dbl if k in REAL_PHRASES)
            checks.append(("2. two-request cases: >=76/80 cover both, every case >=9/10, real phrases and their PT equivalents 10/10",
                           _status(complete("double"), met, could), f"{rate(total, sum(len(v) for v in dbl.values()))} of {n_exp} expected"))
        if "control" in kinds:
            ctl = by_case("control")
            ok = sum(r["covered"] for v in ctl.values() for r in v)
            n = sum(len(v) for v in ctl.values())
            checks.append(("3. simple controls 10/10 per language", _status(complete("control"), ok == PREREG_REPEATS * len(ctl), ok == n),
                           f"{rate(ok, n)} of {PREREG_REPEATS * len(ctl)} expected"))
        if "trace" in kinds:
            trc = by_case("trace")
            ok = sum(r["covered"] for v in trc.values() for r in v)
            n = sum(len(v) for v in trc.values())
            checks.append(("trace proposal first, with the notice for the other read", _status(complete("trace"), ok == PREREG_REPEATS * len(trc), ok == n),
                           f"{rate(ok, n)} of {PREREG_REPEATS * len(trc)} expected (guard-derived handoffs count as not covered)"))
        p95 = _pct([r["total_ms"] for r in live], 0.95)
        checks.append(("5. p95 total <= 5 s", _status(whole_run, (p95 or 1e9) <= 5000, (p95 or 1e9) <= 5000),
                       f"p50 {_pct([r['total_ms'] for r in live], 0.5)} ms, p95 {p95} ms over {len(live)} answered turns"))
        known = [r["cost_usd"] for r in live if r["cost_usd"] is not None]
        unknown_n = len(live) - len(known)
        limit = COST_MAX_USD.get(requested.split(":")[0])
        mean = statistics.mean(known) if known else None
        if unknown_n or limit is None or mean is None:
            cost_status = "NOT MET" if (mean is not None and limit is not None and mean > limit) else "PENDING"
        else:
            cost_status = _status(whole_run, mean <= limit, mean <= limit)
        checks.append((f"5. mean known cost per turn <= USD {limit}", cost_status,
                       f"{mean if mean is None else round(mean, 5)} USD over {len(known)} turns; {unknown_n} turns with no usage from the provider (cost unknown, not zero)"))
        checks.append(("5. one decision per normal turn, <=2 attempts", _status(whole_run, all(r["llm_calls"] <= 1 and r["attempts"] <= 2 for r in live),
                                                                               all(r["llm_calls"] <= 1 and r["attempts"] <= 2 for r in live)),
                       f"max attempts {max([r['attempts'] for r in live] or [0])}"))
        checks.append(("5. p95 no more than 25% above the baseline of the previous prompt", "PENDING", "the baseline run is not part of these rows"))
        if "triple" in kinds:
            tri = by_case("triple")
            declared = {k: sum(r["declared_all"] for r in v) for k, v in tri.items()}
            n_exp = PREREG_REPEATS * len(tri)
            best = {k: declared[k] + (PREREG_REPEATS - len(v)) for k, v in tri.items()}
            checks.append(("cap: triple declared >=38/40, each case >=9/10",
                           _status(complete("triple"), sum(declared.values()) >= 0.95 * n_exp and all(c >= 9 for c in declared.values()),
                                   sum(best.values()) >= 0.95 * n_exp and all(c >= 9 for c in best.values())),
                           f"{rate(sum(declared.values()), sum(len(v) for v in tri.values()))} of {n_exp} expected"))
            if cap == 3:
                cov = {k: sum(r["covered"] for r in v) for k, v in tri.items()}
                best = {k: cov[k] + (PREREG_REPEATS - len(v)) for k, v in tri.items()}
                checks.append(("cap: triple answered (cap-3 run) >=38/40, each case >=9/10",
                               _status(complete("triple"), sum(cov.values()) >= 0.95 * n_exp and all(c >= 9 for c in cov.values()),
                                       sum(best.values()) >= 0.95 * n_exp and all(c >= 9 for c in best.values())),
                               f"{rate(sum(cov.values()), sum(len(v) for v in tri.values()))} of {n_exp} expected"))
                base = cap2_triples.get(requested)
                mine = [r["total_ms"] for v in tri.values() for r in v]
                if base and mine:
                    ratio = _pct(mine, 0.95) / _pct(base, 0.95)
                    checks.append(("cap: p95 no more than 25% above cap 2 on the same cases", _status(complete("triple") and len(base) >= n_exp, ratio <= 1.25, ratio <= 1.25),
                                   f"ratio {ratio:.2f} (p95 {_pct(mine, 0.95)} ms against {_pct(base, 0.95)} ms)"))
                else:
                    checks.append(("cap: p95 no more than 25% above cap 2 on the same cases", "PENDING", "needs the cap-2 rows of the same cases in the same report"))
            else:
                checks.append(("cap: triple answered (cap-3 run) >=38/40, each case >=9/10", "n/a", "this is a cap-2 run: the criterion belongs to the cap-3 run"))
        if "sequence" in kinds:
            reps_done: dict[tuple, dict[int, dict]] = {}
            for r in seq:
                reps_done.setdefault((r["case_id"], r["rep"]), {})[r["turn"]] = r
            wholes = {k: v for k, v in reps_done.items() if len(v) == 3 and not any(r["model_down"] for r in v.values())}
            def left_out(k) -> list[str]:  # what the first turn did not deliver: the reads it lacked, or all of them if the reply was not the templates' composition
                first = wholes[k][0]
                return first["missing"] or ([] if first["covered"] else [describe(n) for n in sequences[k[0]]["reads"]])

            opportunities = [k for k in wholes if left_out(k)]
            recovered = [k for k in opportunities if set(left_out(k)) <= {n for t in (1, 2) for n in wholes[k][t]["covered_needs"]}]
            repeats_when_missing = [k for k in opportunities if k not in recovered and any(wholes[k][t]["policy_rule"].endswith("repeat_guard") for t in (1, 2))]
            seq_complete = len(wholes) == SEQ_REPEATS * len(sequences)
            checks.append(("4. recovery when something was left out (what was missing, read again with its filters)",
                           "PENDING" if not opportunities else _status(seq_complete, len(recovered) == len(opportunities), len(recovered) == len(opportunities)),
                           f"{len(recovered)}/{len(opportunities)} real opportunities in {len(wholes)} whole sequences of {SEQ_REPEATS * len(sequences)} expected"
                           + ("; none: no live rate is claimed" if not opportunities else f"; {len(repeats_when_missing)} answered with the repeat notice though something was missing")))
        checks.append(("6. the deployed demo runs the measured commit, prompt, schemas and model", "PENDING", "checked after an authorized deploy, in both languages"))
        lines += ["| criterion | | detail |", "|---|---|---|"]
        lines += [f"| {name} | {status} | {detail} |" for name, status, detail in checks]
        lines.append("")
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
    ap.add_argument("--report", metavar="JSONL", nargs="+", help="print the table and criteria of one or more rows files (a cap-3 file with its cap-2 file gives the p95 ratio)")
    args = ap.parse_args(argv)
    if args.report:
        print(report([row for path in args.report for row in load_jsonl(Path(path))]))
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
        print(report(rows if not out else [r for r in load_jsonl(out) if r["run_id"] == cfg.run_id]))
        if rows and all(r["model_down"] for r in rows):
            print("no model answered: set the key of the provider (ANTHROPIC_API_KEY, GROQ_API_KEY) in the environment", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
