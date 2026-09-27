"""Understand -> Decide -> Act -> Verify -> Escalate, one turn at a time.

The only module that talks to both the LLM and the deterministic layers.
Invariants:
- The LLM never receives or sets `customer_id`; it's injected from the
  validated session on every tool call.
- The LLM never sees a customer record: it gets the customer's masked words
  (agent/llm/privacy.py), a catalog of aliases and a figure-free history.
  Tool results never go back to it.
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
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from agent.core import render
from agent.llm import prompts
from agent.llm.client import LLMUnavailable, Usage, get_default_client
from agent.llm.pricing import cost_usd
from agent.llm.privacy import redact
from agent.policy import escalation, router
from agent.policy.router import Decision, Disposition
from agent.policy.signals import detect_language, normalize
from agent.session.auth import ExpiredSession, InvalidSession, SessionStore, default_store
from agent.tools import account_tools
from agent.tools.audit import current_trace_id, default_trace_log
from agent.tools.errors import InvalidArgument, MissingSlot, NotApplicable, ToolError

TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "get_account_summary": account_tools.get_account_summary,
    "list_transactions": account_tools.list_transactions,
    "get_payment_status": account_tools.get_payment_status,
    "get_exchange_rate": account_tools.get_exchange_rate,
}
_SCHEMAS = {s["function"]["name"]: s["function"]["parameters"] for s in prompts.TOOL_SCHEMAS}
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
    cost_usd: float | None = None
    llm_calls: int = 0
    latency_ms: float = 0.0
    model_view: str | None = None  # what the model's history keeps of this reply: no figures, no identifiers


@dataclass
class _Conversation:
    messages: list[dict] = field(default_factory=list)
    language: str = "es"
    pending_clarification: bool = False


class ConversationStore:
    """Bounded LRU of per-session histories as the model sees them: the
    customer's masked words and figure-free summaries of our replies."""

    def __init__(self, max_conversations: int = MAX_CONVERSATIONS, max_messages: int = MAX_HISTORY_MESSAGES):
        self._data: OrderedDict[str, _Conversation] = OrderedDict()
        self.max_conversations, self.max_messages = max_conversations, max_messages

    def get(self, key: str) -> _Conversation:
        conv = self._data.pop(key, None) or _Conversation()
        self._data[key] = conv
        while len(self._data) > self.max_conversations:
            self._data.popitem(last=False)
        return conv

    def append(self, conv: _Conversation, role: str, content: str) -> None:
        conv.messages.append({"role": role, "content": content})
        del conv.messages[:-self.max_messages]

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
    return f"[Se respondió al cliente con datos verificados de: {used}]"


def _clarify_view(missing: list[str], catalog: list[dict], reply_text: str) -> str:
    if "product_id" in missing and catalog:
        opts = "; ".join(f"{i}) {p['alias']} {p['product_type']} {p['currency']}" for i, p in enumerate(catalog, start=1))
        return f"[Se le pidió al cliente elegir producto: {opts}]"
    return reply_text  # dates / currency / generic questions are fixed templates without customer data


# --- orchestrator -------------------------------------------------------------

class Orchestrator:
    def __init__(self, session_store: SessionStore | None = None, llm: Callable[[], Any] | None = None,
                 conversations: ConversationStore | None = None):
        # `is None`, not `or`: both stores define __len__, so an empty one is falsy.
        self.session_store = default_store if session_store is None else session_store
        self._llm = llm or get_default_client
        self.conversations = ConversationStore() if conversations is None else conversations

    def handle_message(self, session_token: str, text: str) -> TurnResult:
        trace_id = uuid.uuid4().hex
        ctx_token = current_trace_id.set(trace_id)
        start = time.time()
        trace: dict[str, Any] = {"trace_id": trace_id, "ts": start, "prompt_version": prompts.PROMPT_VERSION, "llm_steps": []}
        try:
            result = self._handle(session_token, text, trace_id, trace)
        finally:
            current_trace_id.reset(ctx_token)
        result.latency_ms = (time.time() - start) * 1000
        default_trace_log.write({**trace, **{k: v for k, v in asdict(result).items() if k not in ("verified_facts",)},
                                 "verified_tools": [f["tool"] for f in result.verified_facts]})
        return result

    # -- helpers --
    def _finish(self, conv, safe_text, result: TurnResult) -> TurnResult:
        conv.pending_clarification = result.disposition == Disposition.CLARIFY.value
        self.conversations.append(conv, "user", safe_text)
        self.conversations.append(conv, "assistant", result.model_view or result.response_text)
        return result

    def _escalate(self, decision: Decision, session, conv, safe_text, lang, trace_id, actions, facts, llm_meta) -> TurnResult:
        """File the ticket, read it back, and only then tell the customer they were transferred."""
        prior = [m["content"] for m in conv.messages if m["role"] == "user"]
        try:
            ticket = escalation.escalate(decision, session.customer_id, session.ref, safe_text, lang, actions,
                                         [{"tool": f["tool"], "result": f["result"]} for f in facts],
                                         prior, session.attributes, trace_id)
            filed = escalation.default_queue.get(ticket.ticket_id) is not None
        except Exception:  # noqa: BLE001 - an unwritable queue must not crash the turn; it is reported as unfiled
            filed = False
        if not filed:
            return TurnResult(trace_id, Disposition.ESCALATE.value, render.MSG["escalate_unverified"][lang].format(code=trace_id[:8]),
                              lang, decision.category, f"{decision.rule}|handoff_unverified", None, facts, actions, **llm_meta)
        msg = render.MSG["escalate_security" if decision.category == "security" else "escalate"][lang]
        return TurnResult(trace_id, Disposition.ESCALATE.value, msg, lang, decision.category, decision.rule,
                          ticket.ticket_id, facts, actions, **llm_meta)

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
        safe_text = redact(text)  # all that is kept or sent anywhere; the raw text only feeds local policy checks
        trace.update({"session_ref": session.ref, "segment": session.attributes.get("segment"),
                      "country": session.attributes.get("country"), "language_scores": [guess.pt_score, guess.es_score]})

        usage, costs, llm_calls = Usage(), [], 0
        provider = model = None

        def llm_meta() -> dict:
            return {"provider": provider, "model": model, "usage": usage, "llm_calls": llm_calls,
                    "cost_usd": None if (not costs or any(c is None for c in costs)) else round(sum(costs), 8)}

        # Decide (pre-LLM): compliance hold, safety lexicon, classifier guard.
        pre, reading = router.pre_llm(text, session.attributes.get("customer_status"), conv.pending_clarification)
        trace["intent_reading"] = asdict(reading)
        if pre:
            return self._finish(conv, safe_text, self._escalate(pre, session, conv, safe_text, lang, trace_id, [], [], llm_meta()))
        foreign = account_tools.foreign_product_refs(session.customer_id, text)
        if foreign:  # caught in code, whatever a model would have done with it
            denied = [{"tool": "ownership_check", "args": {"product_id": pid}, "success": False, "error_type": "PermissionDenied"}
                      for pid in foreign]
            return self._finish(conv, safe_text, self._escalate(router.foreign_reference(foreign), session, conv, safe_text, lang,
                                                                trace_id, denied, [], llm_meta()))

        profile = account_tools.get_customer_profile(session.customer_id)
        catalog = with_aliases(profile["products"])
        messages = [{"role": "system", "content": prompts.SYSTEM_PROMPT},
                    {"role": "system", "content": prompts.context_block(profile.get("as_of"), catalog)},
                    *conv.messages, {"role": "user", "content": safe_text}]

        # Understand: one model call chooses the tools. Its prose is never used.
        try:
            resp = self._llm().chat(messages, tools=prompts.TOOL_SCHEMAS)
        except LLMUnavailable as exc:
            trace["llm_steps"].append({"step": 0, "outcome": "unavailable", "attempts": exc.attempts})
            degraded = self._degraded(reading, text, session, catalog, lang, trace_id, trace, llm_meta())
            if degraded is not None:
                return self._finish(conv, safe_text, degraded)
            return self._finish(conv, safe_text, self._escalate(router.llm_unavailable(exc.attempts), session, conv, safe_text,
                                                                lang, trace_id, [], [], llm_meta()))
        llm_calls = 1
        usage = resp.usage
        provider, model = resp.provider, resp.model
        costs.append(cost_usd(resp.provider, resp.model, resp.usage.prompt_tokens, resp.usage.completion_tokens,
                              resp.usage.cache_read_tokens, resp.usage.cache_write_tokens))
        trace["llm_steps"].append({"step": 0, "provider": resp.provider, "model": resp.model, "latency_ms": round(resp.latency_ms, 1),
                                   "usage": asdict(resp.usage), "attempts": resp.attempts, "n_tool_calls": len(resp.tool_calls)})

        calls = resp.tool_calls[:MAX_TOOL_CALLS_PER_TURN]
        if not calls:  # nothing to look up: abstain or ask, always with a fixed template
            decision = router.no_tool_answer(reading, text)
            reply = render.MSG["abstain" if decision.disposition == Disposition.ABSTAIN else "clarify_generic"][lang]
            res = TurnResult(trace_id, decision.disposition.value, reply, lang, decision.category, decision.rule,
                             None, [], [], **llm_meta())
            return self._finish(conv, safe_text, res)

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
                    res = TurnResult(trace_id, Disposition.CLARIFY.value, reply, lang, decision.category, decision.rule,
                                     None, facts, actions, **llm_meta(), model_view=_clarify_view(missing, catalog, reply))
                    return self._finish(conv, safe_text, res)
                return self._finish(conv, safe_text, self._escalate(decision, session, conv, safe_text, lang, trace_id,
                                                                    actions, facts, llm_meta()))
            facts.append({"tool": name, "args": action["args"], "result": result})

        # Verify + reply: rendered from the verified results only.
        res = TurnResult(trace_id, Disposition.AUTO_RESOLVE.value, render.render_answer(facts, lang, catalog), lang, "resolved",
                         "verified_tool_results", None, facts, actions, **llm_meta(), model_view=_answered_view(facts, catalog))
        return self._finish(conv, safe_text, res)


default_orchestrator = Orchestrator()
