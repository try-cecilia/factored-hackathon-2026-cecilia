"""Understand -> Decide -> Act -> Verify -> Escalate, one turn at a time.

The only module that talks to both the LLM and the deterministic layers.
Invariants:
- The LLM never receives or sets `customer_id`; it's injected from the
  validated session on every tool call.
- The system never gives the LLM a customer record. Tool results never go
  back to it, the catalog holds aliases, type, currency and status only,
  and the history keeps the amounts the customer typed but no warehouse
  figures. What the customer types is sent with identifiers masked
  (agent/llm/privacy.py); a name or an amount they type is sent as written.
- The LLM never writes to the customer. One primary model response per turn
  chooses tools (the client may retry it or fall back to another provider);
  every reply is rendered from verified tool results or fixed templates
  (agent/core/render.py). No figure, and no claimed action, can come from
  model prose.
- Dispositions come from agent/policy/router.py, never from the model.
- Bounded everything: one primary model response and two tool calls per
  turn, history length, number of live conversations, LLM time budget.
Every turn writes one trace record (agent/tools/audit.py) with the policy
rule that fired, LLM attempts/usage, tool calls, cost and the time each stage
took (agent/observability.py). The turn has a time budget (agent/resilience.py)
and a failure of any kind ends in a fixed reply or a handoff, never a guess or
a half-done action.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable

from agent.core import render
from agent.core.experiments import Experiments
from agent.llm import prompts
from agent import observability
from agent.llm.budget import DailyBudget, SessionBudget, default_budget
from agent.llm.client import LLMUnavailable, Usage, get_default_client
from agent.llm.pricing import cost_usd
from agent.llm.privacy import mask_card_numbers, redact
from agent.policy import escalation, router
from agent.policy.desk import default_desk
from agent.policy.router import Decision, Disposition
from agent.policy.signals import detect_language, normalize
from agent.resilience import RetryPolicy, current_deadline, handoff_deadline, retry_call, run_bounded, turn_deadline
from agent.session.auth import ExpiredSession, InvalidSession, SessionStore, default_store, session_ref
from agent.tools import account_tools, state
from agent.observability import stage
from agent.tools.audit import current_trace_id, default_trace_log
from agent.tools.errors import InvalidArgument, MissingSlot, NotApplicable, ToolError
from agent.tools.traces import default_traces

TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "get_account_summary": account_tools.get_account_summary,
    "list_transactions": account_tools.list_transactions,
    "get_payment_status": account_tools.get_payment_status,
    "get_exchange_rate": account_tools.get_exchange_rate,
    "request_trace": account_tools.request_trace,
}
_SCHEMAS = {s["function"]["name"]: s["function"]["parameters"] for s in prompts.TOOL_SCHEMAS}
# What the model's history keeps of our replies: fixed text, no figures, no identifiers.
MODEL_VIEW = {
    "answered": "[Se respondió al cliente con datos verificados de: {used}]",
    "choose_product": "[Se le pidió al cliente elegir producto: {opts}]",
    "trace_choose": "[Se le pidió al cliente elegir cuál de sus movimientos pendientes rastrear]",
    "trace_already_open": "[Se informó el pedido de rastreo que el cliente ya tenía abierto]",
    "trace_proposed": "[Se le propuso al cliente abrir un pedido de rastreo; se espera su respuesta]",
    "trace_opened": "[Se abrió el pedido de rastreo que el cliente confirmó]",
    "trace_cancelled": "[El cliente no quiso abrir el pedido de rastreo; no se abrió nada]",
    "unattended": "[Quedaron sin atender, por el límite de consultas de un turno: {calls}]",
    "repeated": "[Se le dijo al cliente que esa consulta ya estaba respondida arriba y se le pidió que dijera qué otra cosa necesitaba]",
}
# What a read's arguments say about the request, kept in the history the model gets (no records: filters the customer asked for).
VIEW_ARGS = ("transaction_type", "status", "limit", "start_date", "end_date", "on_date", "source_currency", "target_currency")
READ_ANSWERS = ("verified_tool_results", "degraded:deterministic_balance")  # the rules whose reply is a read: two in a row are never the same

MAX_TOOL_CALLS_PER_TURN = 2
TOOL_RETRY = RetryPolicy(max_attempts=2, base_s=0.05, cap_s=0.25)  # every tool here is a read: repeating one is harmless
MAX_PROMPT_CHARS = int(os.environ.get("LLM_MAX_PROMPT_CHARS") or 24_000)  # ~6K tokens; the fixed prompt is ~2.1K tokens
logger = logging.getLogger(__name__)
turn_logger = logging.getLogger("cecilai.turn")  # one line per turn: ids, outcome, timings, nothing the customer wrote
MAX_HISTORY_MESSAGES = 8
MAX_CASE_INDEX = 100  # cases of one session the sidebar can list (a session opens a handful; this only bounds the row)
MAX_TRANSCRIPT = 40  # rendered turns kept for the customer to read again (20 exchanges); the model never sees them
MAX_CONVERSATIONS = 10_000
DEGRADED_MIN_CONFIDENCE = 0.6


@dataclass
class TurnResult:
    trace_id: str
    disposition: str
    response_text: str
    language: str
    category: str = "none"
    policy_rule: str = ""
    ticket_id: str | None = None
    verified_facts: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    usage: Usage = field(default_factory=Usage)
    cost_usd: float | None = 0.0  # 0.0 = no model call billed; None = a model call whose price is unknown
    llm_calls: int = 0
    latency_ms: float = 0.0
    model_view: str | None = None  # what the model's history keeps of this reply: no figures, no identifiers
    model_input: str | None = None  # the customer's words as the model received them (masked); None if it received nothing
    choice: str | None = None  # what the numbered options of a CLARIFY are: "product" (a name) or "movement" (a number); None if it has none
    read_digest: str | None = None  # a digest of this reply when it is a read, kept to never send the same one twice in a row (not traced)

    @property
    def degraded(self) -> bool:
        """The assistant answered in limited mode: the model was unavailable (or its budget spent), so the code answered alone."""
        return self.policy_rule.startswith("degraded:") or self.category == "llm_unavailable"


@dataclass
class _Conversation:
    messages: list[dict] = field(default_factory=list)  # what the model may see
    requests: list[str] = field(default_factory=list)  # what a human agent may see: card numbers masked only
    language: str = "es"
    language_set: bool = False  # whether the customer's own words ever showed a language; "es" above is only the default until then
    pending_clarification: bool = False
    pending_action: dict | None = None  # a trace proposed on the last turn, kept in code: never sent to the model
    pending_choice: list[dict] | None = None  # the pending movements listed on the last turn, to pick one by number
    last_answer: str | None = None  # a digest of the last reply when it was a read, to never send the same one twice in a row
    cases: dict[str, str] = field(default_factory=dict)  # legacy notices, retained when loading older conversations
    transcript: list[dict] = field(default_factory=list)  # what the customer saw, as rendered: card numbers masked, no model data
    case_index: list[dict] = field(default_factory=list)  # the session's handoffs (ticket_id, category, at), not bounded by the transcript

    @classmethod
    def from_saved(cls, data: dict) -> "_Conversation":
        """A conversation saved before `language_set` existed keeps the language it had: with turns, or with a language other than the
        default, it was learned from the customer (the safest reading: it changes nothing for those rows, and the only cost is that a
        session whose every turn was without a language signal keeps the default instead of falling back to its ticket's)."""
        if "language_set" not in data:
            data = {**data, "language_set": bool(data.get("messages") or data.get("requests") or data.get("transcript")
                                                 or data.get("language", "es") != "es")}
        return cls(**data)


class ConversationStore:
    """Bounded LRU of per-session histories: for the model, the customer's
    masked words (amounts they typed included) and summaries of our replies
    without warehouse figures; for tickets, the
    customer's requests with card numbers masked. Each turn is also written to
    SQLite (agent/tools/state.py), so a restart or a refresh resumes the same
    conversation, including a trace proposed and waiting for the customer's yes."""

    RETENTION_SECONDS = 24 * 3600  # a conversation outlives its 15-minute session only briefly
    # The retention job (ops/retention.py) deletes rows from another process. The copy kept in memory is served only while its
    # row is still there, checked at most this often, and never past the retention window: what was purged is not brought back.
    VERIFY_SECONDS = 60

    def __init__(self, max_conversations: int = MAX_CONVERSATIONS, max_messages: int = MAX_HISTORY_MESSAGES,
                 db_path: str | None = None):
        self._data: OrderedDict[str, _Conversation] = OrderedDict()
        self._touched: dict[str, float] = {}  # when each conversation in memory was last read or written
        self._checked: dict[str, float] = {}  # when its row was last seen in the file (only for those that were saved)
        self.max_conversations, self.max_messages = max_conversations, max_messages
        self._db, self._lock = state.connect(db_path), threading.Lock()
        with self._lock, self._db:
            self._db.execute("DELETE FROM conversations WHERE updated_at < ?", (time.time() - self.RETENTION_SECONDS,))

    def get(self, key: str) -> _Conversation:
        now = time.time()
        conv = self._data.pop(key, None)
        if conv is not None and not self._still_valid(key, now):
            conv = None  # past the retention window, or purged from the file: not served, and not written back by a later save
            self._touched.pop(key, None)
            self._checked.pop(key, None)
        conv = conv or self._load(key, now) or _Conversation()
        self._data[key] = conv
        self._touched[key] = now
        while len(self._data) > self.max_conversations:
            old, _ = self._data.popitem(last=False)
            self._touched.pop(old, None)
            self._checked.pop(old, None)
        return conv

    def _still_valid(self, key: str, now: float) -> bool:
        if now - self._touched.get(key, now) > self.RETENTION_SECONDS:
            return False
        checked = self._checked.get(key)
        if checked is None or now - checked <= self.VERIFY_SECONDS:
            return True  # never saved (its first turn is still in flight), or looked at a moment ago
        with self._lock:
            row = self._db.execute("SELECT 1 FROM conversations WHERE key = ?", (key,)).fetchone()
        if row is None:
            return False
        self._checked[key] = now
        return True

    def _load(self, key: str, now: float) -> _Conversation | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM conversations WHERE key = ? AND updated_at >= ?",
                                   (key, now - self.RETENTION_SECONDS)).fetchone()
        if row:
            self._checked[key] = now
        return _Conversation.from_saved(json.loads(row[0])) if row else None

    def save(self, key: str) -> None:
        """Write the conversation as the turn left it (a no-op for a key this store has not handed out)."""
        conv = self._data.get(key)
        if conv is not None:
            now = time.time()
            with self._lock, self._db:
                self._db.execute("INSERT OR REPLACE INTO conversations VALUES (?, ?, ?)",
                                 (key, json.dumps(asdict(conv), ensure_ascii=False, default=str), now))
            self._touched[key] = self._checked[key] = now

    def append(self, conv: _Conversation, role: str, content: str) -> None:
        conv.messages.append({"role": role, "content": content})
        del conv.messages[:-self.max_messages]

    def record_turn(self, conv: _Conversation, text: str, result: "TurnResult") -> None:
        """Keep the exchange as the customer saw it, for GET /chat/history. The customer's words go in with card numbers masked
        (the same masking as the ticket's copy); the reply is the rendered text, and only the fields the screen needs."""
        now = time.time()
        conv.transcript.append({"role": "user", "text": mask_card_numbers(text), "at": now})
        conv.transcript.append({"role": "assistant", "text": result.response_text, "at": now, "trace_id": result.trace_id,
                                "disposition": result.disposition, "category": result.category, "language": result.language,
                                "ticket_id": result.ticket_id, "degraded": result.degraded, "choice": result.choice})
        del conv.transcript[:-MAX_TRANSCRIPT]
        if result.disposition == "ESCALATE" and result.ticket_id and all(c["ticket_id"] != result.ticket_id for c in conv.case_index):
            conv.case_index.append({"ticket_id": result.ticket_id, "category": result.category, "at": now})
            del conv.case_index[:-MAX_CASE_INDEX]

    def clear_transcript(self, key: str) -> None:
        """Forget what was shown (logout): the figures in it are not kept for the rest of the retention window."""
        conv = self._data.pop(key, None) or self._load(key, time.time())
        if conv is not None and conv.transcript:
            conv.transcript.clear()
            self._data[key] = conv
            self.save(key)

    def mark_case_notified(self, customer_id: str, ticket_id: str, status: str) -> bool:
        """Record a notice once per customer, even across sessions, restarts and conversation cleanup."""
        with self._lock, self._db:
            # Only a claimed ticket can change again; a terminal notice must never be repeated or rolled back.
            changed = self._db.execute(
                "INSERT INTO case_notifications VALUES (?, ?, ?) "
                "ON CONFLICT(customer_id, ticket_id) DO UPDATE SET status = excluded.status "
                "WHERE case_notifications.status = 'claimed' AND case_notifications.status != excluded.status",
                (customer_id, ticket_id, status))
            return changed.rowcount == 1

    def append_request(self, conv: _Conversation, request: str) -> None:
        conv.requests.append(request)
        del conv.requests[:-self.max_messages]

    def __len__(self) -> int:
        return len(self._data)


# --- argument sanitation ----------------------------------------------------

def resolve_product_ref(value: Any, catalog: list[dict]) -> str:
    """Map what the model passed (alias, id, last-4, number, or a product type)
    onto one of *this customer's* products. Values that match nothing pass
    through unchanged so the tool's ownership check can judge them."""
    v = str(value).strip()
    by_alias = {p["alias"].lower(): p["product_id"] for p in catalog if p.get("alias")}
    if v.lower() in by_alias:
        return by_alias[v.lower()]
    ids = {p["product_id"] for p in catalog}
    if v in ids:
        return v
    digits = "".join(ch for ch in v if ch.isdigit())
    if len(digits) >= 4:
        hits = [p for p in catalog if p.get("last4") == digits[-4:]]
        if len(hits) == 1:
            return hits[0]["product_id"]
    hits = [p for p in catalog if normalize(p["product_type"]) in normalize(v) or normalize(v) in normalize(p["product_type"])]
    active = [p for p in hits if p["product_status"] != "Closed"] or hits
    if len(active) == 1:
        return active[0]["product_id"]
    if len(active) > 1:
        raise MissingSlot(f"'{v}' matches {len(active)} products", missing_slots=["product_id"])
    return v


def sanitize_args(tool: str, raw: dict, catalog: list[dict], require: bool = True) -> tuple[dict, list[str]]:
    """The arguments the tool takes, each checked (enums, integers, the product resolved to one of the customer's). With `require`
    False the required ones may be missing: the values that are there are kept, for a read that is described and not run."""
    schema = _SCHEMAS[tool]
    props, required = schema["properties"], schema.get("required", [])
    dropped = [k for k in raw if k not in props]
    args = {k: v for k, v in raw.items() if k in props and v not in (None, "")}
    for k, spec in props.items():
        if k not in args:
            continue
        if "enum" in spec:
            val = str(args[k]).strip()
            val = val.upper() if k.endswith("currency") else val
            match = next((e for e in spec["enum"] if e.lower() == val.lower()), None)
            if match is None:
                raise InvalidArgument(f"{k}={args[k]!r} not in {spec['enum']}", missing_slots=[k])
            args[k] = match
        if spec.get("type") == "integer":
            try:
                args[k] = max(spec.get("minimum", 1), min(int(args[k]), spec.get("maximum", 50)))
            except (TypeError, ValueError):
                args.pop(k)
    if "product_id" in args:
        args["product_id"] = resolve_product_ref(args["product_id"], catalog)
    elif "product_id" in required and tool == "get_payment_status":
        credit = [p for p in catalog if p["product_type"] in account_tools.CREDIT_PRODUCT_TYPES and p["product_status"] != "Closed"]
        if len(credit) == 1:  # unambiguous: fill the slot instead of asking
            args["product_id"] = credit[0]["product_id"]
    missing = [k for k in required if k not in args]
    if missing and require:
        raise MissingSlot(f"{tool} needs {missing}", missing_slots=missing)
    return args, dropped


def out_of_time() -> bool:
    """Whether the turn's budget is spent. Checked before every lookup and every action, and after each lookup."""
    d = current_deadline.get()
    return d is not None and d.expired


def run_tool(name: str, customer_id: str, **args: Any) -> Any:
    """A tool call with a bounded retry for a transient failure of what it reads (a busy disk, a database connection).
    Every tool here is a read, so repeating one is harmless; a ToolError (bad argument, not yours, no data) is a
    real answer and is never retried. Within the turn's deadline, like every retry."""
    return retry_call(lambda: TOOL_FUNCTIONS[name](customer_id, **args), policy=TOOL_RETRY, idempotent=True)


def fit_prompt(messages: list[dict], limit: int = MAX_PROMPT_CHARS) -> list[dict]:
    """The history trimmed to the size limit, oldest first. Only history is cut: the two fixed system blocks and the
    customer's message (at most 1,000 characters, masked) always go whole, so the limit bounds how much history a turn
    carries, not the prompt; if those parts alone exceed it, the prompt goes out over the limit."""
    head, history, last = messages[:2], list(messages[2:-1]), messages[-1]
    size = lambda ms: sum(len(str(m["content"])) for m in ms)  # noqa: E731
    while history and size(head) + size(history) + size([last]) > limit:
        history.pop(0)
    return [*head, *history, last]


def with_aliases(catalog: list[dict]) -> list[dict]:
    """P1, P2... in catalog order, the same order render.clarify lists them
    to the customer, so "la segunda" means P2 to the model too."""
    return [{**p, "alias": f"P{i}"} for i, p in enumerate(catalog, start=1)]


def _call_view(tool: str, args: dict, alias: dict[str, str], ref: str = "") -> str:
    """One read as the model's history keeps it: the tool, the product's alias (or `ref`, the product as the model named it
    when it could not be resolved) and the filters asked for."""
    shown = [alias.get(args.get("product_id"), "") or ref, *(f"{k}={args[k]}" for k in VIEW_ARGS if args.get(k) not in (None, ""))]
    return f"{tool}({', '.join(x for x in shown if x)})"


def _answered_view(facts: list[dict], catalog: list[dict]) -> str:
    alias = {p["product_id"]: p["alias"] for p in catalog}
    used = ", ".join(_call_view(f["tool"], f.get("args") or {}, alias) for f in facts)
    return MODEL_VIEW["answered"].format(used=used)


def _clarify_view(missing: list[str], catalog: list[dict], reply_text: str) -> str:
    if "product_id" in missing and catalog:
        opts = "; ".join(f"{i}) {p['alias']} {p['product_type']} {p['currency']}" for i, p in enumerate(catalog, start=1))
        return MODEL_VIEW["choose_product"].format(opts=opts)
    return reply_text  # dates / currency / generic questions are fixed templates without customer data


# --- orchestrator -------------------------------------------------------------

class Orchestrator:
    def __init__(self, session_store: SessionStore | None = None, llm: Callable[[], Any] | None = None,
                 conversations: ConversationStore | None = None, budget: DailyBudget | None = None,
                 experiments: Experiments | None = None, session_budget: SessionBudget | None = None):
        # `is None`, not `or`: both stores define __len__, so an empty one is falsy.
        self.session_store = default_store if session_store is None else session_store
        self._llm = llm or get_default_client
        self.conversations = ConversationStore() if conversations is None else conversations
        self.budget = default_budget if budget is None else budget
        self.session_budget = SessionBudget.from_env() if session_budget is None else session_budget
        self.experiments = Experiments.from_env() if experiments is None else experiments  # shadow/canary: off unless configured

    def handle_message(self, session_token: str, text: str) -> TurnResult:
        # The API gives each request its trace id and the turn adopts it: one id from the HTTP request to the ticket.
        trace_id = current_trace_id.get() or observability.new_trace_id()
        ctx_token = current_trace_id.set(trace_id)
        # The record's timestamp is wall time; the latency, a monotonic clock fine enough for milliseconds (Windows'
        # wall clock ticks every 15.6 ms).
        ts, start = time.time(), time.perf_counter()
        trace: dict[str, Any] = {"trace_id": trace_id, "ts": ts, "prompt_version": prompts.PROMPT_VERSION,
                                 "llm_steps": [], "model_route": "not_called", **(observability.current_request.get() or {})}
        try:
            with turn_deadline() as deadline, observability.recording() as recorder:
                try:
                    result = self._handle(session_token, text, trace_id, trace)
                except Exception as exc:  # noqa: BLE001 - whatever broke, the customer gets a handoff, never a crash
                    result = self._unexpected_failure(session_token, text, trace_id, trace, exc)
                try:
                    result = self._with_case_news(session_token, result)
                except Exception as exc:  # noqa: BLE001 - the news are a courtesy: the answer, and what it already did, go out without them
                    self._record_failed("case_news", trace_id, exc)
                self._remember_turn(session_token, text, result, trace_id)
                trace["stages"] = recorder.spans
                trace["turn_budget_left_ms"] = round(deadline.remaining() * 1000)
        finally:
            current_trace_id.reset(ctx_token)
            try:
                if self._session_is_live(session_token):  # a session that is over saves nothing: it would revive a purged row
                    self.conversations.save(session_ref(session_token))  # even on a crash: what the turn changed is kept
            except Exception as exc:  # noqa: BLE001 - a failed save loses the history, never the reply
                self._record_failed("conversation_save", trace_id, exc)
        result.latency_ms = (time.perf_counter() - start) * 1000
        try:
            default_trace_log.write({**trace, **{k: v for k, v in asdict(result).items() if k not in ("verified_facts", "read_digest")},
                                     "verified_tools": [f["tool"] for f in result.verified_facts]})
        except Exception as exc:  # noqa: BLE001 - a record that cannot be written must not take the customer's answer with it
            self._record_failed("trace_write", trace_id, exc)
        self._log_turn(result, trace)
        return result

    def _remember_turn(self, session_token: str, text: str, result: TurnResult, trace_id: str) -> None:
        """Add the exchange to the session's readable history. A session that ended has none, and a failure here loses the
        history, never the reply."""
        if result.disposition == "REAUTH_REQUIRED":
            return
        try:
            session = self.session_store.validate(session_token)
            self.conversations.record_turn(self.conversations.get(session.ref), text, result)
        except (InvalidSession, ExpiredSession):
            return
        except Exception as exc:  # noqa: BLE001
            self._record_failed("transcript", trace_id, exc)

    def history(self, session_token: str) -> list[dict]:
        """The session's rendered conversation, oldest first. Raises InvalidSession/ExpiredSession for a bad token."""
        session = self.session_store.validate(session_token)
        return [dict(turn) for turn in self.conversations.get(session.ref).transcript]

    def case_index(self, session_token: str) -> list[dict]:
        """The cases this session opened, oldest first: they outlive the turns that opened them."""
        session = self.session_store.validate(session_token)
        return [dict(case) for case in self.conversations.get(session.ref).case_index]

    def _session_is_live(self, session_token: str) -> bool:
        try:
            self.session_store.validate(session_token)
        except (InvalidSession, ExpiredSession):
            return False
        except Exception:  # noqa: BLE001 - the store itself failing is not a reason to lose the turn's state
            return True
        return True

    @staticmethod
    def _record_failed(kind: str, trace_id: str, exc: Exception) -> None:
        """A record we could not write after the effects happened: counted (/admin/capacity) and logged by type, never by message."""
        observability.count_failure(kind)
        logger.error("%s failed (%s)", kind, type(exc).__name__,
                     extra={"fields": {"trace_id": trace_id, "kind": kind, "error_type": type(exc).__name__}})

    @staticmethod
    def _log_turn(result: TurnResult, trace: dict) -> None:
        """One log line per turn: ids, outcome and timings. Never the customer's words, a reply or a customer id."""
        stages = {sp["stage"]: sp["ms"] for sp in trace.get("stages", [])}
        turn_logger.info("turn disposition=%s category=%s rule=%s latency_ms=%.1f llm_calls=%d", result.disposition, result.category,
                    result.policy_rule, result.latency_ms, result.llm_calls,
                    extra={"fields": {"trace_id": result.trace_id, "disposition": result.disposition, "category": result.category,
                                      "policy_rule": result.policy_rule, "ticket_id": result.ticket_id,
                                      "latency_ms": round(result.latency_ms, 1), "llm_calls": result.llm_calls,
                                      "provider": result.provider, "model": result.model, "cost_usd": result.cost_usd,
                                      "stages_ms": stages}})

    def _unexpected_failure(self, session_token: str, text: str, trace_id: str, trace: dict, exc: Exception) -> TurnResult:
        """Something outside the tool calls broke (the profile lookup, the ownership check, the model client): the same
        safe fallback as a failed tool, a handoff to a person that says nothing about the request. Only the exception's
        type is kept, in the log, the trace and the ticket: its message can quote what the customer wrote."""
        error_type = type(exc).__name__
        logger.error("turn failed (%s)", error_type, extra={"fields": {"trace_id": trace_id, "error_type": error_type}})
        lang = detect_language(text).language
        trace.update({"rule": "unexpected_failure", "error_type": error_type})
        try:
            session = self.session_store.validate(session_token)
        except (InvalidSession, ExpiredSession):
            return TurnResult(trace_id, "REAUTH_REQUIRED", render.MSG["reauth"][lang], lang, "session", "session:expired_during_failure")
        except Exception:  # noqa: BLE001 - the session store is what failed: nothing can be filed
            return TurnResult(trace_id, Disposition.ESCALATE.value, render.MSG["escalate_unverified"][lang].format(code=trace_id[:8]),
                              lang, "tool_failure", "unexpected_failure|handoff_unverified")
        try:
            conv = self.conversations.get(session.ref)
            error = ToolError(f"unexpected failure: {error_type}")
            return self._escalate(router.after_tool(error), session, conv, mask_card_numbers(text), conv.language, trace_id,
                                  [{"tool": "turn", "success": False, "error_type": error_type}], [], {})
        except Exception:  # noqa: BLE001 - even the handoff path failed: say so, with the code to quote
            return TurnResult(trace_id, Disposition.ESCALATE.value, render.MSG["escalate_unverified"][lang].format(code=trace_id[:8]),
                              lang, "tool_failure", "unexpected_failure|handoff_unverified")

    def _with_case_news(self, session_token: str, result: TurnResult) -> TurnResult:
        """What a person did with this customer's tickets since they last heard: said once, by code, ahead of the reply."""
        try:
            session = self.session_store.validate(session_token)
        except (InvalidSession, ExpiredSession):
            return result
        conv = self.conversations.get(session.ref)
        news = []
        try:
            tickets = escalation.default_queue.for_customer(session.customer_id)
        except Exception as exc:  # noqa: BLE001 - the notices are a courtesy: with the queue unreadable, the answer still goes out
            self._record_failed("case_news", result.trace_id, exc)
            return result
        for ticket in tickets:
            ticket_id = ticket["ticket_id"]
            state = default_desk.state(ticket_id)
            # In the language of the reply it goes ahead of (the turn's, which is the session's once the customer has written).
            line = render.case_update(state["status"], result.language, default_traces.get(state["trace_id"] or ""),
                                      state["message"], bool(ticket.get("pending_action")))
            if line and self.conversations.mark_case_notified(session.customer_id, ticket_id, state["status"]):
                # Seed notices already delivered by the earlier, session-scoped implementation without repeating them.
                if conv.cases.get(ticket_id) == state["status"]:
                    continue
                news.append(line)
        if news:
            result.response_text = "\n".join(news) + "\n\n" + result.response_text
        return result

    def case_status(self, session_token: str, ticket_id: str) -> dict | None:
        """The status of one of this customer's tickets, worded as the chat would; None if it is not theirs.
        The language is the session's (the one the customer last wrote in, as for the news in the chat), not the ticket's;
        a session whose customer has not yet written anything that shows a language falls back to the ticket's.
        Raises InvalidSession/ExpiredSession for a bad token."""
        session = self.session_store.validate(session_token)
        ticket = escalation.default_queue.get(ticket_id)
        if ticket is None or ticket["customer_id"] != session.customer_id:
            return None
        state = default_desk.state(ticket_id)
        conv = self.conversations.get(session.ref)
        lang = conv.language if conv.language_set else ticket.get("language") or conv.language
        text = render.case_update(state["status"], lang, default_traces.get(state["trace_id"] or ""), state["message"],
                                  bool(ticket.get("pending_action")))
        return {"ticket_id": ticket_id, "status": state["status"], "message": text}

    # -- helpers --
    @staticmethod
    def _repeated(result: TurnResult) -> TurnResult:
        """The read's reply is the one the customer was just sent: say so, and what else they can ask, instead of sending it again.
        What was read is still verified and still on the record; only the text changes."""
        as_of = next((f["result"].get("as_of") for f in result.verified_facts if isinstance(f.get("result"), dict)), None)
        prefix = "degraded:" if result.degraded else ""
        return replace(result, disposition=Disposition.CLARIFY.value, category="repeated_request", policy_rule=f"{prefix}repeat_guard",
                       response_text=render.repeat_notice(as_of, result.language), model_view=MODEL_VIEW["repeated"], read_digest=None)

    def _no_repeat(self, conv: _Conversation, result: TurnResult) -> TurnResult:
        """A read's reply that is identical to the one just sent becomes a notice. Applied to the resolved reads alone, before
        anything that is said around them (what was left unattended), so those notes are never swallowed by it. The reply that
        follows a notice may show the data again: it is no longer the last one sent."""
        if result.policy_rule not in READ_ANSWERS:
            return result
        digest = hashlib.sha256(result.response_text.encode("utf-8")).hexdigest()[:16]
        return self._repeated(result) if digest == conv.last_answer else replace(result, read_digest=digest)

    def _finish(self, conv, model_text, ticket_text, result: TurnResult) -> TurnResult:
        conv.last_answer = result.read_digest
        conv.pending_clarification = result.disposition == Disposition.CLARIFY.value
        self.conversations.append(conv, "user", model_text)
        self.conversations.append(conv, "assistant", result.model_view or result.response_text)
        self.conversations.append_request(conv, ticket_text)
        return result

    def _escalate(self, decision: Decision, session, conv, ticket_text, lang, trace_id, actions, facts, llm_meta,
                  pending_action: dict | None = None, notice: str | None = None) -> TurnResult:
        """File the ticket, read it back, and only then tell the customer they were transferred (`notice`: the render.MSG key
        that says why, instead of the plain one)."""
        try:
            with handoff_deadline() as budget, stage("ticket", category=decision.category) as info:
                ticket = escalation.escalate(decision, session.customer_id, session.ref, ticket_text, lang, actions,
                                             [{"tool": f["tool"], "result": f["result"]} for f in facts],
                                             list(conv.requests), session.attributes, trace_id, pending_action)
                # The read-back is the last step of the same budget, bounded like the others, and the clock is checked after
                # it: a ticket that cannot be confirmed in time is not claimed, and not named: only a confirmed ticket has an id here.
                try:
                    found = run_bounded(lambda: escalation.default_queue.get(ticket.ticket_id), budget.remaining())
                except TimeoutError:  # includes Saturated
                    found = None
                filed = found is not None and not budget.expired
                info["outcome"] = "ok" if filed else "not_read_back"
        except Exception:  # noqa: BLE001 - an unwritable queue must not crash the turn; HandoffInFlight is one of these, and explicit in the stage
            filed = False
        if not filed:
            return TurnResult(trace_id, Disposition.ESCALATE.value, render.MSG["escalate_unverified"][lang].format(code=trace_id[:8]),
                              lang, decision.category, f"{decision.rule}|handoff_unverified", None, facts, actions, **llm_meta)
        msg = render.MSG[notice or ("escalate_security" if decision.category == "security" else "escalate")][lang]
        return TurnResult(trace_id, Disposition.ESCALATE.value, msg, lang, decision.category, decision.rule,
                          ticket.ticket_id, facts, actions, **llm_meta)

    def _trace_step(self, result, conv, lang, country, trace_id, actions, done, escalate, meta) -> TurnResult:
        """The customer's pending movements that match: propose the one (opened only on their yes), say which trace
        is already open, ask which one, or hand it to a person when nothing of theirs is pending."""
        decision = router.trace_step(result)
        items = result["items"]
        if decision.disposition == Disposition.ESCALATE:
            # "Nothing pending" only when the search was not narrowed: an amount, a date or a product may have left pending ones out.
            narrowed = any(v not in (None, "") for v in (result.get("filters") or {}).values())
            return escalate(decision, actions, [], notice="trace_unmatched_filtered" if narrowed else "trace_unmatched")
        if decision.rule == "action:trace_choose":
            conv.pending_choice = items  # a plain "la segunda" is resolved in code next turn
            opts = "; ".join(f"{i}) {render.movement(m, lang, country)}" for i, m in enumerate(items, start=1))
            return done(TurnResult(trace_id, decision.disposition.value, render.MSG["trace_choose"][lang].format(opts=opts), lang,
                                   decision.category, decision.rule, None, [], actions, **meta, model_view=MODEL_VIEW["trace_choose"],
                                   choice="movement"))
        m = items[0]
        if decision.rule == "action:trace_already_open":
            opened = m["open_trace"]
            text = render.MSG["trace_already_open"][lang].format(tid=opened["trace_id"], mov=render.movement(m, lang, country),
                                                                  sla=opened["sla_business_days"])
            return done(TurnResult(trace_id, decision.disposition.value, text, lang, decision.category, decision.rule, None,
                                   [{"tool": "request_trace", "args": {"product_id": m["product_id"]}, "result": opened}], actions,
                                   **meta, model_view=MODEL_VIEW["trace_already_open"]))
        # One movement: show it and ask for a plain yes; the proposal is kept in code for one turn.
        conv.pending_action = {"transaction_id": m["transaction_id"], "product_id": m["product_id"], "movement": m}
        return done(TurnResult(trace_id, decision.disposition.value, render.MSG["trace_propose"][lang].format(mov=render.movement(m, lang, country)),
                               lang, decision.category, decision.rule, None, [], actions, **meta, model_view=MODEL_VIEW["trace_proposed"]))

    def _open_trace(self, proposal, session, lang, trace_id, done, escalate) -> TurnResult:
        """The customer said yes: open the trace, read it back, and only then say it exists."""
        action = {"tool": "request_trace", "args": {"product_id": proposal["product_id"]}, "confirmed_by_customer": True}

        def out_of_time_handoff() -> TurnResult:
            # Nothing was written: the customer's yes is recorded and a person decides, with the proposal intact.
            return escalate(router.turn_timeout(), [{**action, "success": False, "error_type": "TurnTimeout"}], [],
                            {"tool": "request_trace", "transaction_id": proposal["transaction_id"],
                             "product_id": proposal["product_id"], "review_reason": "turn_timeout", "age_days": None,
                             "movement": proposal["movement"]})

        if out_of_time():
            return out_of_time_handoff()
        still_pending, review, age_days, timed_out = True, None, None, False
        try:
            # The proposal is one turn old: the movement may have settled since, so eligibility is checked again.
            with stage("tool:request_trace"):
                pending = run_tool("request_trace", session.customer_id, product_id=proposal["product_id"],
                                   transaction_id=proposal["transaction_id"])["items"]
            found = next((m for m in pending if m["transaction_id"] == proposal["transaction_id"]), None)
            still_pending = found is not None
            review = found.get("review_reason") if found else None
            age_days = found.get("age_days") if found else None
            verified = None
            timed_out = still_pending and not review and out_of_time()  # the lookup ate the budget: write nothing now
            if still_pending and not review and not timed_out:
                # Opened and read back (this customer's, this movement's), retrying a busy service a bounded number of times.
                with stage("trace_service") as info:
                    log: list[dict] = []
                    try:
                        verified = default_traces.open_verified(session.customer_id, proposal["transaction_id"],
                                                                proposal["product_id"], session.ref, attempts_log=log)
                    finally:
                        info["attempts"] = len(log)
        except Exception:  # noqa: BLE001 - an unwritable service is an unverified action, never a crash
            verified = None
        if timed_out:
            return out_of_time_handoff()
        if review:  # old or self-contradicting: the customer's yes is recorded, a person decides
            return escalate(router.trace_review(review), [{**action, "success": False, "error_type": "NeedsHumanApproval"}], [],
                            {"tool": "request_trace", "transaction_id": proposal["transaction_id"],
                             "product_id": proposal["product_id"], "review_reason": review, "age_days": age_days,
                             "movement": proposal["movement"]})
        if not still_pending:
            return escalate(router.trace_step({"items": []}), [{**action, "success": False, "error_type": "MovementNoLongerPending"}], [])
        if not verified:
            return escalate(router.trace_unverified(), [{**action, "success": False, "error_type": "TraceNotReadBack"}], [])
        decision = router.trace_opened()
        text = render.MSG["trace_opened"][lang].format(tid=verified["trace_id"], mov=render.movement(proposal["movement"], lang, session.attributes.get("country")),
                                                       sla=verified["sla_business_days"])
        return done(TurnResult(trace_id, decision.disposition.value, text, lang, decision.category, decision.rule, None,
                               [{"tool": "request_trace", "args": {"product_id": proposal["product_id"]}, "result": verified}],
                               [{**action, "success": True}], model_view=MODEL_VIEW["trace_opened"]))

    def _degraded(self, reading, text, session, catalog, lang, trace_id, trace, meta) -> TurnResult | None:
        """LLM down: handle only what needs no language model - a confident
        out-of-scope request (abstain) or a plain balance question with no
        product mentioned (deterministic summary). Anything else still goes
        to a human."""
        if not reading.model_available or (reading.p_intent or 0) < DEGRADED_MIN_CONFIDENCE:
            return None
        if out_of_time():  # the same clock as any lookup: nothing is read or answered once the turn's budget is gone
            trace["degraded_skipped"] = "turn_budget_spent"
            return None
        if reading.intent == "out_of_scope":
            trace["rule"] = "degraded:classifier_out_of_scope"
            return TurnResult(trace_id, Disposition.ABSTAIN.value, render.MSG["abstain"][lang], lang, "out_of_scope",
                              "degraded:classifier_out_of_scope", **meta)
        mentions_product = any(ch.isdigit() for ch in text) or any(
            normalize(w) in normalize(text) for w in ("ahorro", "corriente", "credito", "debito", "prestamo", "hipotec",
                                                      "poupanca", "corrente", "cartao", "emprestimo", "financiamento"))
        if reading.intent == "balance_inquiry" and not mentions_product:
            with stage("tool:get_account_summary", degraded=True):
                result = run_tool("get_account_summary", session.customer_id)
            if out_of_time():  # the lookup finished after the budget: its result is not used, a person answers
                trace["degraded_skipped"] = "turn_budget_spent"
                return None
            facts = [{"tool": "get_account_summary", "args": {}, "result": result}]
            trace["rule"] = "degraded:deterministic_balance"
            return TurnResult(trace_id, Disposition.AUTO_RESOLVE.value, render.render_answer(facts, lang, country=session.attributes.get("country")), lang, "resolved",
                              "degraded:deterministic_balance", None, facts,
                              [{"tool": "get_account_summary", "args": {}, "success": True, "degraded": True}],
                              model_view=_answered_view(facts, catalog), **meta)
        return None

    def _handle(self, token: str, text: str, trace_id: str, trace: dict) -> TurnResult:
        guess = detect_language(text)
        try:
            with stage("session"):
                session = self.session_store.validate(token)
        except (InvalidSession, ExpiredSession) as exc:
            trace["rule"] = f"session:{type(exc).__name__}"
            return TurnResult(trace_id, "REAUTH_REQUIRED", render.MSG["reauth"][guess.language], guess.language,
                              "session", f"session:{type(exc).__name__}")

        conv = self.conversations.get(session.ref)
        # Only a message where one language wins changes it: no signal, or a tie ("no dia de hoje" scores 1 to 1), keeps
        # the conversation's, which is the default until a message shows one.
        decisive = guess.pt_score != guess.es_score
        lang = guess.language if decisive else conv.language
        conv.language = lang
        conv.language_set = conv.language_set or decisive
        # The raw text only feeds local policy checks. The model gets `model_text` (identifiers masked, own product
        # ids as aliases); a human agent's ticket gets `ticket_text` (card numbers masked, amounts kept).
        model_text, ticket_text = redact(text), mask_card_numbers(text)
        trace.update({"session_ref": session.ref, "cohort": self.experiments.cohort_for(session.ref),
                      "segment": session.attributes.get("segment"),
                      "country": session.attributes.get("country"), "language_scores": [guess.pt_score, guess.es_score]})

        usage, costs, llm_calls = Usage(), [], 0
        provider = model = model_input = None

        def llm_meta() -> dict:
            return {"provider": provider, "model": model, "usage": usage, "llm_calls": llm_calls, "model_input": model_input,
                    "cost_usd": None if any(c is None for c in costs) else round(sum(costs), 8)}

        def done(result: TurnResult) -> TurnResult:
            return self._finish(conv, model_text, ticket_text, result)

        def escalate(decision: Decision, actions: list[dict], facts: list[dict], pending_action: dict | None = None,
                     notice: str | None = None) -> TurnResult:
            return done(self._escalate(decision, session, conv, ticket_text, lang, trace_id, actions, facts, llm_meta(),
                                       pending_action, notice))

        # Act on the customer's own yes: a trace proposed on the last turn is opened only if this message is a plain
        # yes, decided in code without the model. Any other message lets the proposal lapse and goes on as usual.
        if conv.pending_action is not None:
            proposal, conv.pending_action = conv.pending_action, None
            answer = router.confirmation(text)
            if answer == "yes":
                return self._open_trace(proposal, session, lang, trace_id, done, escalate)
            if answer == "no":
                d = router.trace_cancelled()
                return done(TurnResult(trace_id, d.disposition.value, render.MSG["trace_cancelled"][lang], lang, d.category, d.rule,
                                       model_view=MODEL_VIEW["trace_cancelled"]))
        # A pending movement picked by its number in the list shown last turn ("la segunda"), also in code.
        if conv.pending_choice is not None:
            choices, conv.pending_choice = conv.pending_choice, None
            index = router.ordinal(text, len(choices))
            if index is not None:
                return self._trace_step({"items": [choices[index]]}, conv, lang, session.attributes.get("country"), trace_id, [], done, escalate, llm_meta())

        # Decide (pre-LLM): compliance hold, safety lexicon, classifier guard.
        with stage("pre_llm"):
            pre, reading = router.pre_llm(text, session.attributes.get("customer_status"), conv.pending_clarification)
        trace["intent_reading"] = asdict(reading)
        if pre:
            return escalate(pre, [], [])
        with stage("ownership_check"):
            foreign = account_tools.foreign_product_refs(session.customer_id, text)
        if foreign:  # caught in code, whatever a model would have done with it
            return escalate(router.foreign_reference(foreign), [
                {"tool": "ownership_check", "args": {"product_id": pid}, "success": False, "error_type": "PermissionDenied"}
                for pid in foreign], [])

        with stage("catalog"):
            profile = account_tools.get_customer_profile(session.customer_id)
        catalog = with_aliases(profile["products"])
        model_text = redact(text, {p["product_id"]: p["alias"] for p in catalog})
        messages = [{"role": "system", "content": prompts.SYSTEM_PROMPT},
                    {"role": "system", "content": prompts.context_block(profile.get("as_of"), catalog)},
                    *conv.messages, {"role": "user", "content": model_text}]
        messages = fit_prompt(messages)

        # Understand: one primary model response chooses the tools (the client may retry it or fall back to another
        # provider). Its prose is never used.
        try:
            if self.budget.exhausted():  # past the daily spend cap: the model counts as down
                raise LLMUnavailable("daily model budget reached", [{"provider": "budget", "outcome": "skipped",
                                                                     "reason": "daily_budget_exhausted"}])
            if self.session_budget.exhausted(session.ref):  # this session has spent its share: same, for this session only
                raise LLMUnavailable("session model budget reached", [{"provider": "budget", "outcome": "skipped",
                                                                       "reason": "session_budget_exhausted"}])
            trace["model_route"] = "unavailable"
            with stage("llm") as info:
                resp, model_route = self.experiments.chat(session.ref, self._llm, messages, prompts.TOOL_SCHEMAS)
                info.update(provider=resp.provider, model=resp.model, route=model_route)
            trace["model_route"] = model_route
        except LLMUnavailable as exc:
            trace["llm_steps"].append({"step": 0, "outcome": "unavailable", "attempts": exc.attempts})
            degraded = self._degraded(reading, text, session, catalog, lang, trace_id, trace, llm_meta())
            return done(self._no_repeat(conv, degraded)) if degraded is not None else escalate(router.llm_unavailable(exc.attempts), [], [])
        llm_calls, model_input = 1, model_text
        usage = resp.usage
        provider, model = resp.provider, resp.model
        costs.append(cost_usd(resp.provider, resp.model, resp.usage.prompt_tokens, resp.usage.completion_tokens,
                              resp.usage.cache_read_tokens, resp.usage.cache_write_tokens))
        self.budget.add(costs[-1])
        self.session_budget.add(session.ref, costs[-1])
        trace["llm_steps"].append({"step": 0, "provider": resp.provider, "model": resp.model, "latency_ms": round(resp.latency_ms, 1),
                                   "usage": asdict(resp.usage), "attempts": resp.attempts, "n_tool_calls": len(resp.tool_calls)})

        self.experiments.shadow(trace_id, session.ref, messages, prompts.TOOL_SCHEMAS, resp, model_route)  # background, logged only
        # The model declares every read the customer asked for; the code runs at most MAX_TOOL_CALLS_PER_TURN of them and says,
        # by template, which it did not (and keeps them in the model's history so the next turn can finish). The same read twice
        # in a response is one read. A trace request is looked for in all of them, not only in the first ones: it takes the turn alone.
        declared = list({(c["name"], c["arguments"]): c for c in resp.tool_calls}.values())
        if not declared:  # nothing to look up: abstain or ask, always with a fixed template
            decision = router.no_tool_answer(reading, text)
            reply = render.MSG["abstain" if decision.disposition == Disposition.ABSTAIN else "clarify_generic"][lang]
            return done(TurnResult(trace_id, decision.disposition.value, reply, lang, decision.category, decision.rule,
                                   None, [], [], **llm_meta()))

        trace_call = next((c for c in declared if c["name"] == "request_trace"), None)
        calls = [trace_call] if trace_call is not None else declared[:MAX_TOOL_CALLS_PER_TURN]
        left: list[dict] = [c for c in declared if not any(c is k for k in calls)]  # declared and not run; later also the clarifications put off

        def with_unattended(result: TurnResult) -> TurnResult:
            """The reads the turn left aside, said by a template after the reply and kept in the model's history."""
            parts, views = self._unattended(left, catalog, lang)
            if not parts:
                return result
            trace["unattended_calls"] = [c["name"] for c in left]
            return replace(result, response_text=f"{result.response_text}\n\n{render.unattended_notice(parts, lang)}",
                           model_view=f"{result.model_view or result.response_text} {MODEL_VIEW['unattended'].format(calls=', '.join(views))}")

        # Act: sanitized arguments, identity from the session, ownership checked in the tool.
        facts: list[dict] = []
        actions: list[dict] = []
        clarify: tuple[Decision, list[str]] | None = None  # the first read that needs one more answer from the customer; the others still run
        for call in calls:
            name = call["name"]
            deadline = current_deadline.get()
            if deadline is not None and deadline.expired:  # only reads have run so far: hand it over, do not start another
                trace["rule"] = "turn_timeout"
                return escalate(router.turn_timeout(), actions, facts)
            try:
                raw_args = json.loads(call["arguments"] or "{}")
                raw_args = raw_args if isinstance(raw_args, dict) else {}
            except json.JSONDecodeError:
                raw_args = {}
            raw_args.pop("customer_id", None)  # identity always comes from the session
            action = {"tool": name, "raw_args": raw_args}
            result, error, failed_with = None, None, None
            try:
                if name not in TOOL_FUNCTIONS:
                    raise ToolError(f"unknown tool {name}")
                args, dropped = sanitize_args(name, raw_args, catalog)
                action.update({"args": args, "dropped_args": dropped})
                with stage(f"tool:{name}"):
                    result = run_tool(name, session.customer_id, **args)
            except NotApplicable as exc:
                result = {"not_applicable": True, "reason": str(exc), **exc.payload}
            except ToolError as exc:
                error = exc
            except Exception as exc:  # noqa: BLE001 - unexpected tool/DB failure -> bounded, safe fallback; only the type is kept, never the message
                error, failed_with = ToolError(f"unexpected failure in {name}: {type(exc).__name__}"), type(exc).__name__
            action.update({"success": error is None, "error_type": failed_with or (type(error).__name__ if error else None)})
            actions.append(action)
            if out_of_time():  # a slow lookup finished after the budget: its result is not used, a person answers
                trace["rule"] = "turn_timeout"
                return escalate(router.turn_timeout(), actions, facts)

            decision = router.after_tool(error)
            if decision is not None:
                trace["rule"] = decision.rule
                if decision.disposition == Disposition.CLARIFY:
                    if clarify is None:
                        clarify = (decision, decision.missing_slots or getattr(error, "missing_slots", []))
                    else:
                        left.append(call)  # one question per turn: this read is named as unattended, with its filters in the history
                    continue
                return escalate(decision, actions, facts)
            if name == "request_trace":
                return self._trace_step(result, conv, lang, session.attributes.get("country"), trace_id, actions, lambda res: done(with_unattended(res)), escalate, llm_meta())
            facts.append({"tool": name, "args": action["args"], "result": result})

        if clarify is not None:  # what was answered is said first, then the question for the rest
            decision, missing = clarify
            reply = render.clarify(missing, catalog, lang)
            answered = render.render_answer(facts, lang, catalog, session.attributes.get("country")) if facts else ""
            view = _clarify_view(missing, catalog, reply)
            return done(with_unattended(TurnResult(
                trace_id, Disposition.CLARIFY.value, f"{answered}\n\n{reply}" if answered else reply, lang, decision.category,
                decision.rule, None, facts, actions, **llm_meta(), model_view=f"{_answered_view(facts, catalog)} {view}" if facts else view,
                choice="product" if "product_id" in missing and catalog else None)))

        # Verify + reply: rendered from the verified results only.
        with stage("render"):
            answer = render.render_answer(facts, lang, catalog, session.attributes.get("country"))
        reply = self._no_repeat(conv, TurnResult(trace_id, Disposition.AUTO_RESOLVE.value, answer, lang, "resolved", "verified_tool_results",
                                                 None, facts, actions, **llm_meta(), model_view=_answered_view(facts, catalog)))
        return done(with_unattended(reply))

    @staticmethod
    def _unattended(left: list[dict], catalog: list[dict], lang: str) -> tuple[list[str], list[str]]:
        """For each read the model declared and the turn did not answer: its name for the customer and its line in the model's
        history. The arguments are sanitized as a set without requiring the mandatory ones (a read that needed a clarification keeps
        everything that was valid, such as both currencies of an exchange rate); if one value does not pass, each of the others is
        tried alone. A product the model named is kept only if it is a type or alias of this customer's catalog."""
        alias = {p["product_id"]: p["alias"] for p in catalog}
        vocabulary = {*alias.values(), *(p["product_type"] for p in catalog)}
        parts, views = [], []
        for call in left:
            name = call["name"]
            if name not in TOOL_FUNCTIONS:
                continue
            try:
                raw = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                raw = {}
            raw = raw if isinstance(raw, dict) else {}
            wanted = {k: raw[k] for k in (*VIEW_ARGS, "product_id") if k in raw}
            try:  # the whole set at once; the required ones may be missing, as in a read that was not complete
                args = sanitize_args(name, wanted, catalog, require=False)[0]
            except Exception:  # noqa: BLE001 - one value does not pass: keep each of the others that does
                args = {}
                for key, value in wanted.items():
                    try:
                        args.update(sanitize_args(name, {key: value}, catalog, require=False)[0])
                    except Exception:  # noqa: BLE001 - left out of what the history keeps
                        pass
            for key in ("start_date", "end_date", "on_date"):  # the tools' own rule for a date, so the history never offers one they reject
                if key in args:
                    try:
                        if not isinstance(args[key], str):
                            raise InvalidArgument(f"{key} must be text")
                        args[key] = account_tools.parse_date(args[key], key).isoformat()
                    except InvalidArgument:
                        args.pop(key)
            ref = str(raw.get("product_id")) if str(raw.get("product_id")) in vocabulary else ""
            parts.append(render.read_part(name, args, lang))
            views.append(_call_view(name, args, alias, ref))
        return parts, views


default_orchestrator = Orchestrator()
