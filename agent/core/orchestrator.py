"""Understand -> Decide -> Act -> Verify -> Escalate, one turn at a time.

The only module that talks to both the LLM and the deterministic layers.
Invariants:
- The LLM never receives or sets `customer_id`; it's injected from the
  validated session on every tool call.
- The system never gives the LLM a customer record. Tool results never go
  back to it, the catalog holds aliases, type, currency and status only,
  and the history is figure-free. What the customer types is sent with
  identifiers masked (agent/llm/privacy.py); a name or an amount they type
  is sent as written.
- The LLM never writes to the customer. One call per turn chooses tools;
  every reply is rendered from verified tool results or fixed templates
  (agent/core/render.py). No figure, and no claimed action, can come from
  model prose.
- Dispositions come from agent/policy/router.py, never from the model.
- Bounded everything: one model call and two tool calls per turn, history
  length, number of live conversations, LLM time budget.
Every turn writes one trace record (agent/tools/audit.py) with the policy
rule that fired, LLM attempts/usage, tool calls and cost.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from agent.core import render
from agent.core.experiments import Experiments
from agent.llm import prompts
from agent.llm.budget import DailyBudget, default_budget
from agent.llm.client import LLMUnavailable, Usage, get_default_client
from agent.llm.pricing import cost_usd
from agent.llm.privacy import mask_card_numbers, redact
from agent.policy import escalation, router
from agent.policy.desk import default_desk
from agent.policy.router import Decision, Disposition
from agent.policy.signals import detect_language, normalize
from agent.session.auth import ExpiredSession, InvalidSession, SessionStore, default_store, session_ref
from agent.tools import account_tools, state
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
}
MAX_TOOL_CALLS_PER_TURN = 2
MAX_HISTORY_MESSAGES = 8
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


@dataclass
class _Conversation:
    messages: list[dict] = field(default_factory=list)  # what the model may see
    requests: list[str] = field(default_factory=list)  # what a human agent may see: card numbers masked only
    language: str = "es"
    pending_clarification: bool = False
    pending_action: dict | None = None  # a trace proposed on the last turn, kept in code: never sent to the model
    pending_choice: list[dict] | None = None  # the pending movements listed on the last turn, to pick one by number
    cases: dict[str, str] = field(default_factory=dict)  # legacy notices, retained when loading older conversations


class ConversationStore:
    """Bounded LRU of per-session histories: for the model, the customer's
    masked words and figure-free summaries of our replies; for tickets, the
    customer's requests with card numbers masked. Each turn is also written to
    SQLite (agent/tools/state.py), so a restart or a refresh resumes the same
    conversation, including a trace proposed and waiting for the customer's yes."""

    RETENTION_SECONDS = 24 * 3600  # a conversation outlives its 15-minute session only briefly

    def __init__(self, max_conversations: int = MAX_CONVERSATIONS, max_messages: int = MAX_HISTORY_MESSAGES,
                 db_path: str | None = None):
        self._data: OrderedDict[str, _Conversation] = OrderedDict()
        self.max_conversations, self.max_messages = max_conversations, max_messages
        self._db, self._lock = state.connect(db_path), threading.Lock()
        with self._lock, self._db:
            self._db.execute("DELETE FROM conversations WHERE updated_at < ?", (time.time() - self.RETENTION_SECONDS,))

    def get(self, key: str) -> _Conversation:
        conv = self._data.pop(key, None) or self._load(key) or _Conversation()
        self._data[key] = conv
        while len(self._data) > self.max_conversations:
            self._data.popitem(last=False)
        return conv

    def _load(self, key: str) -> _Conversation | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM conversations WHERE key = ?", (key,)).fetchone()
        return _Conversation(**json.loads(row[0])) if row else None

    def save(self, key: str) -> None:
        """Write the conversation as the turn left it (a no-op for a key this store has not handed out)."""
        conv = self._data.get(key)
        if conv is not None:
            with self._lock, self._db:
                self._db.execute("INSERT OR REPLACE INTO conversations VALUES (?, ?, ?)",
                                 (key, json.dumps(asdict(conv), ensure_ascii=False, default=str), time.time()))

    def append(self, conv: _Conversation, role: str, content: str) -> None:
        conv.messages.append({"role": role, "content": content})
        del conv.messages[:-self.max_messages]

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


def sanitize_args(tool: str, raw: dict, catalog: list[dict]) -> tuple[dict, list[str]]:
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
    if missing:
        raise MissingSlot(f"{tool} needs {missing}", missing_slots=missing)
    return args, dropped


def with_aliases(catalog: list[dict]) -> list[dict]:
    """P1, P2... in catalog order, the same order render.clarify lists them
    to the customer, so "la segunda" means P2 to the model too."""
    return [{**p, "alias": f"P{i}"} for i, p in enumerate(catalog, start=1)]


def _answered_view(facts: list[dict], catalog: list[dict]) -> str:
    alias = {p["product_id"]: p["alias"] for p in catalog}
    used = ", ".join(f"{f['tool']}({alias.get((f.get('args') or {}).get('product_id'), '')})" for f in facts)
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
                 experiments: Experiments | None = None):
        # `is None`, not `or`: both stores define __len__, so an empty one is falsy.
        self.session_store = default_store if session_store is None else session_store
        self._llm = llm or get_default_client
        self.conversations = ConversationStore() if conversations is None else conversations
        self.budget = default_budget if budget is None else budget
        self.experiments = Experiments.from_env() if experiments is None else experiments  # shadow/canary: off unless configured

    def handle_message(self, session_token: str, text: str) -> TurnResult:
        trace_id = uuid.uuid4().hex
        ctx_token = current_trace_id.set(trace_id)
        # The record's timestamp is wall time; the latency, a monotonic clock fine enough for milliseconds (Windows'
        # wall clock ticks every 15.6 ms).
        ts, start = time.time(), time.perf_counter()
        trace: dict[str, Any] = {"trace_id": trace_id, "ts": ts, "prompt_version": prompts.PROMPT_VERSION,
                                 "llm_steps": [], "model_route": "not_called"}
        try:
            result = self._with_case_news(session_token, self._handle(session_token, text, trace_id, trace))
        finally:
            current_trace_id.reset(ctx_token)
            self.conversations.save(session_ref(session_token))  # even on a crash: what the turn changed is kept
        result.latency_ms = (time.perf_counter() - start) * 1000
        default_trace_log.write({**trace, **{k: v for k, v in asdict(result).items() if k not in ("verified_facts",)},
                                 "verified_tools": [f["tool"] for f in result.verified_facts]})
        return result

    def _with_case_news(self, session_token: str, result: TurnResult) -> TurnResult:
        """What a person did with this customer's tickets since they last heard: said once, by code, ahead of the reply."""
        try:
            session = self.session_store.validate(session_token)
        except (InvalidSession, ExpiredSession):
            return result
        conv = self.conversations.get(session.ref)
        news = []
        for ticket in escalation.default_queue.for_customer(session.customer_id):
            ticket_id = ticket["ticket_id"]
            state = default_desk.state(ticket_id)
            line = render.case_update(state["status"], result.language, default_traces.get(state["trace_id"] or ""))
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
        Raises InvalidSession/ExpiredSession for a bad token."""
        session = self.session_store.validate(session_token)
        ticket = escalation.default_queue.get(ticket_id)
        if ticket is None or ticket["customer_id"] != session.customer_id:
            return None
        state = default_desk.state(ticket_id)
        lang = self.conversations.get(session.ref).language
        text = render.case_update(state["status"], lang, default_traces.get(state["trace_id"] or ""))
        return {"ticket_id": ticket_id, "status": state["status"], "message": text}

    # -- helpers --
    def _finish(self, conv, model_text, ticket_text, result: TurnResult) -> TurnResult:
        conv.pending_clarification = result.disposition == Disposition.CLARIFY.value
        self.conversations.append(conv, "user", model_text)
        self.conversations.append(conv, "assistant", result.model_view or result.response_text)
        self.conversations.append_request(conv, ticket_text)
        return result

    def _escalate(self, decision: Decision, session, conv, ticket_text, lang, trace_id, actions, facts, llm_meta,
                  pending_action: dict | None = None) -> TurnResult:
        """File the ticket, read it back, and only then tell the customer they were transferred."""
        try:
            ticket = escalation.escalate(decision, session.customer_id, session.ref, ticket_text, lang, actions,
                                         [{"tool": f["tool"], "result": f["result"]} for f in facts],
                                         list(conv.requests), session.attributes, trace_id, pending_action)
            filed = escalation.default_queue.get(ticket.ticket_id) is not None
        except Exception:  # noqa: BLE001 - an unwritable queue must not crash the turn; it is reported as unfiled
            filed = False
        if not filed:
            return TurnResult(trace_id, Disposition.ESCALATE.value, render.MSG["escalate_unverified"][lang].format(code=trace_id[:8]),
                              lang, decision.category, f"{decision.rule}|handoff_unverified", None, facts, actions, **llm_meta)
        msg = render.MSG["escalate_security" if decision.category == "security" else "escalate"][lang]
        return TurnResult(trace_id, Disposition.ESCALATE.value, msg, lang, decision.category, decision.rule,
                          ticket.ticket_id, facts, actions, **llm_meta)

    def _trace_step(self, result, conv, lang, trace_id, actions, done, escalate, meta) -> TurnResult:
        """The customer's pending movements that match: propose the one (opened only on their yes), say which trace
        is already open, ask which one, or hand it to a person when nothing of theirs is pending."""
        decision = router.trace_step(result)
        items = result["items"]
        if decision.disposition == Disposition.ESCALATE:
            return escalate(decision, actions, [])
        if decision.rule == "action:trace_choose":
            conv.pending_choice = items  # a plain "la segunda" is resolved in code next turn
            opts = "; ".join(f"{i}) {render.movement(m, lang)}" for i, m in enumerate(items, start=1))
            return done(TurnResult(trace_id, decision.disposition.value, render.MSG["trace_choose"][lang].format(opts=opts), lang,
                                   decision.category, decision.rule, None, [], actions, **meta, model_view=MODEL_VIEW["trace_choose"]))
        m = items[0]
        if decision.rule == "action:trace_already_open":
            opened = m["open_trace"]
            text = render.MSG["trace_already_open"][lang].format(tid=opened["trace_id"], mov=render.movement(m, lang),
                                                                  sla=opened["sla_business_days"])
            return done(TurnResult(trace_id, decision.disposition.value, text, lang, decision.category, decision.rule, None,
                                   [{"tool": "request_trace", "args": {"product_id": m["product_id"]}, "result": opened}], actions,
                                   **meta, model_view=MODEL_VIEW["trace_already_open"]))
        # One movement: show it and ask for a plain yes; the proposal is kept in code for one turn.
        conv.pending_action = {"transaction_id": m["transaction_id"], "product_id": m["product_id"], "movement": m}
        return done(TurnResult(trace_id, decision.disposition.value, render.MSG["trace_propose"][lang].format(mov=render.movement(m, lang)),
                               lang, decision.category, decision.rule, None, [], actions, **meta, model_view=MODEL_VIEW["trace_proposed"]))

    def _open_trace(self, proposal, session, lang, trace_id, done, escalate) -> TurnResult:
        """The customer said yes: open the trace, read it back, and only then say it exists."""
        action = {"tool": "request_trace", "args": {"product_id": proposal["product_id"]}, "confirmed_by_customer": True}
        still_pending, review, age_days = True, None, None
        try:
            # The proposal is one turn old: the movement may have settled since, so eligibility is checked again.
            pending = TOOL_FUNCTIONS["request_trace"](session.customer_id, product_id=proposal["product_id"],
                                                      transaction_id=proposal["transaction_id"])["items"]
            found = next((m for m in pending if m["transaction_id"] == proposal["transaction_id"]), None)
            still_pending = found is not None
            review = found.get("review_reason") if found else None
            age_days = found.get("age_days") if found else None
            verified = None
            if still_pending and not review:
                default_traces.open(session.customer_id, proposal["transaction_id"], proposal["product_id"], session.ref)
                verified = default_traces.find(session.customer_id, proposal["transaction_id"])  # this customer's, this movement's
        except Exception:  # noqa: BLE001 - an unwritable service is an unverified action, never a crash
            verified = None
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
        text = render.MSG["trace_opened"][lang].format(tid=verified["trace_id"], mov=render.movement(proposal["movement"], lang),
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
        if reading.intent == "out_of_scope":
            trace["rule"] = "degraded:classifier_out_of_scope"
            return TurnResult(trace_id, Disposition.ABSTAIN.value, render.MSG["abstain"][lang], lang, "out_of_scope",
                              "degraded:classifier_out_of_scope", **meta)
        mentions_product = any(ch.isdigit() for ch in text) or any(
            normalize(w) in normalize(text) for w in ("ahorro", "corriente", "credito", "debito", "prestamo", "hipotec",
                                                      "poupanca", "cartao", "emprestimo", "financiamento"))
        if reading.intent == "balance_inquiry" and not mentions_product:
            result = account_tools.get_account_summary(session.customer_id)
            facts = [{"tool": "get_account_summary", "args": {}, "result": result}]
            trace["rule"] = "degraded:deterministic_balance"
            return TurnResult(trace_id, Disposition.AUTO_RESOLVE.value, render.render_answer(facts, lang), lang, "resolved",
                              "degraded:deterministic_balance", None, facts,
                              [{"tool": "get_account_summary", "args": {}, "success": True, "degraded": True}],
                              model_view=_answered_view(facts, catalog), **meta)
        return None

    def _handle(self, token: str, text: str, trace_id: str, trace: dict) -> TurnResult:
        guess = detect_language(text)
        try:
            session = self.session_store.validate(token)
        except (InvalidSession, ExpiredSession) as exc:
            trace["rule"] = f"session:{type(exc).__name__}"
            return TurnResult(trace_id, "REAUTH_REQUIRED", render.MSG["reauth"][guess.language], guess.language,
                              "session", f"session:{type(exc).__name__}")

        conv = self.conversations.get(session.ref)
        lang = guess.language if (guess.pt_score or guess.es_score) else conv.language
        conv.language = lang
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

        def escalate(decision: Decision, actions: list[dict], facts: list[dict], pending_action: dict | None = None) -> TurnResult:
            return done(self._escalate(decision, session, conv, ticket_text, lang, trace_id, actions, facts, llm_meta(),
                                       pending_action))

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
                return self._trace_step({"items": [choices[index]]}, conv, lang, trace_id, [], done, escalate, llm_meta())

        # Decide (pre-LLM): compliance hold, safety lexicon, classifier guard.
        pre, reading = router.pre_llm(text, session.attributes.get("customer_status"), conv.pending_clarification)
        trace["intent_reading"] = asdict(reading)
        if pre:
            return escalate(pre, [], [])
        foreign = account_tools.foreign_product_refs(session.customer_id, text)
        if foreign:  # caught in code, whatever a model would have done with it
            return escalate(router.foreign_reference(foreign), [
                {"tool": "ownership_check", "args": {"product_id": pid}, "success": False, "error_type": "PermissionDenied"}
                for pid in foreign], [])

        profile = account_tools.get_customer_profile(session.customer_id)
        catalog = with_aliases(profile["products"])
        model_text = redact(text, {p["product_id"]: p["alias"] for p in catalog})
        messages = [{"role": "system", "content": prompts.SYSTEM_PROMPT},
                    {"role": "system", "content": prompts.context_block(profile.get("as_of"), catalog)},
                    *conv.messages, {"role": "user", "content": model_text}]

        # Understand: one model call chooses the tools. Its prose is never used.
        try:
            if self.budget.exhausted():  # past the daily spend cap: the model counts as down
                raise LLMUnavailable("daily model budget reached", [{"provider": "budget", "outcome": "skipped",
                                                                     "reason": "daily_budget_exhausted"}])
            trace["model_route"] = "unavailable"
            resp, model_route = self.experiments.chat(session.ref, self._llm, messages, prompts.TOOL_SCHEMAS)
            trace["model_route"] = model_route
        except LLMUnavailable as exc:
            trace["llm_steps"].append({"step": 0, "outcome": "unavailable", "attempts": exc.attempts})
            degraded = self._degraded(reading, text, session, catalog, lang, trace_id, trace, llm_meta())
            return done(degraded) if degraded is not None else escalate(router.llm_unavailable(exc.attempts), [], [])
        llm_calls, model_input = 1, model_text
        usage = resp.usage
        provider, model = resp.provider, resp.model
        costs.append(cost_usd(resp.provider, resp.model, resp.usage.prompt_tokens, resp.usage.completion_tokens,
                              resp.usage.cache_read_tokens, resp.usage.cache_write_tokens))
        self.budget.add(costs[-1])
        trace["llm_steps"].append({"step": 0, "provider": resp.provider, "model": resp.model, "latency_ms": round(resp.latency_ms, 1),
                                   "usage": asdict(resp.usage), "attempts": resp.attempts, "n_tool_calls": len(resp.tool_calls)})

        self.experiments.shadow(trace_id, session.ref, messages, prompts.TOOL_SCHEMAS, resp, model_route)  # background, logged only
        calls = resp.tool_calls[:MAX_TOOL_CALLS_PER_TURN]
        if not calls:  # nothing to look up: abstain or ask, always with a fixed template
            decision = router.no_tool_answer(reading, text)
            reply = render.MSG["abstain" if decision.disposition == Disposition.ABSTAIN else "clarify_generic"][lang]
            return done(TurnResult(trace_id, decision.disposition.value, reply, lang, decision.category, decision.rule,
                                   None, [], [], **llm_meta()))

        if any(c["name"] == "request_trace" for c in calls):  # a proposed action takes the turn on its own
            calls = [next(c for c in calls if c["name"] == "request_trace")]

        # Act: sanitized arguments, identity from the session, ownership checked in the tool.
        facts: list[dict] = []
        actions: list[dict] = []
        for call in calls:
            name = call["name"]
            try:
                raw_args = json.loads(call["arguments"] or "{}")
                raw_args = raw_args if isinstance(raw_args, dict) else {}
            except json.JSONDecodeError:
                raw_args = {}
            raw_args.pop("customer_id", None)  # identity always comes from the session
            action = {"tool": name, "raw_args": raw_args}
            result, error = None, None
            try:
                if name not in TOOL_FUNCTIONS:
                    raise ToolError(f"unknown tool {name}")
                args, dropped = sanitize_args(name, raw_args, catalog)
                action.update({"args": args, "dropped_args": dropped})
                result = TOOL_FUNCTIONS[name](session.customer_id, **args)
            except NotApplicable as exc:
                result = {"not_applicable": True, "reason": str(exc), **exc.payload}
            except ToolError as exc:
                error = exc
            except Exception as exc:  # noqa: BLE001 - unexpected tool/DB failure -> bounded, safe fallback
                error = ToolError(f"unexpected failure in {name}: {type(exc).__name__}: {exc}")
            action.update({"success": error is None, "error_type": type(error).__name__ if error else None,
                           "error": str(error) if error else None})
            actions.append(action)

            decision = router.after_tool(error)
            if decision is not None:
                trace["rule"] = decision.rule
                if decision.disposition == Disposition.CLARIFY:
                    missing = decision.missing_slots or getattr(error, "missing_slots", [])
                    reply = render.clarify(missing, catalog, lang)
                    return done(TurnResult(trace_id, Disposition.CLARIFY.value, reply, lang, decision.category, decision.rule,
                                           None, facts, actions, **llm_meta(), model_view=_clarify_view(missing, catalog, reply)))
                return escalate(decision, actions, facts)
            if name == "request_trace":
                return self._trace_step(result, conv, lang, trace_id, actions, done, escalate, llm_meta())
            facts.append({"tool": name, "args": action["args"], "result": result})

        # Verify + reply: rendered from the verified results only.
        return done(TurnResult(trace_id, Disposition.AUTO_RESOLVE.value, render.render_answer(facts, lang, catalog), lang,
                               "resolved", "verified_tool_results", None, facts, actions, **llm_meta(),
                               model_view=_answered_view(facts, catalog)))


default_orchestrator = Orchestrator()
