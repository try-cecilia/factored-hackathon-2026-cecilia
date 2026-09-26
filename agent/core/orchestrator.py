"""Understand -> Decide -> Act -> Verify -> Escalate orchestration.

This is the only place that talks to both the LLM and the deterministic
policy/tool layers. Two invariants hold throughout:
- The LLM never receives or sets `customer_id`; the orchestrator injects it
  from the validated session on every tool call.
- A disposition (AUTO_RESOLVE / CLARIFY / ABSTAIN / ESCALATE) is always
  decided by agent/policy/router.py, never inferred from LLM prose alone.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from agent.llm.client import LLMUnavailable, get_default_client
from agent.llm.prompts import SYSTEM_PROMPT, TOOL_NAME_TO_INTENT, TOOL_SCHEMAS
from agent.policy import escalation
from agent.policy.router import Decision, Disposition, contains_escalation_signal, decide_after_tool_call
from agent.session.auth import ExpiredSession, InvalidSession, SessionStore, default_store
from agent.tools import account_tools
from agent.tools.errors import MissingSlot, ToolError

TOOL_FUNCTIONS = {
    "get_account_summary": account_tools.get_account_summary,
    "list_transactions": account_tools.list_transactions,
    "get_payment_status": account_tools.get_payment_status,
    "get_exchange_rate": account_tools.get_exchange_rate,
}

_REQUIRED_ARGS_BY_TOOL = {
    schema["function"]["name"]: schema["function"]["parameters"].get("required", []) for schema in TOOL_SCHEMAS
}

REAUTH_MESSAGE = {
    "es": "Tu sesión expiró o no es válida. Por favor vuelve a iniciar sesión para continuar.",
    "pt": "Sua sessão expirou ou não é válida. Por favor, faça login novamente para continuar.",
}
ESCALATION_MESSAGE = {
    "es": "Entiendo tu preocupación. Voy a transferir tu caso de inmediato a un agente humano especializado, junto con el detalle de tu consulta.",
    "pt": "Entendo sua preocupação. Vou transferir seu caso imediatamente para um atendente humano especializado, junto com os detalhes da sua solicitação.",
}
ABSTAIN_MESSAGE = {
    "es": "Esa solicitud está fuera de lo que puedo resolver en consultas de cuenta y pagos. Te voy a orientar hacia el área correspondiente.",
    "pt": "Essa solicitação está fora do que posso resolver em consultas de conta e pagamentos. Vou te orientar para a área correta.",
}


def _detect_language(text: str) -> str:
    pt_markers = (" não ", " você ", " conta ", "obrigad", " cartão ", " cobrança")
    lowered = f" {text.lower()} "
    return "pt" if any(m in lowered for m in pt_markers) else "es"


@dataclass
class TurnResult:
    disposition: str
    response_text: str
    verified_facts: dict[str, Any] = field(default_factory=dict)
    ticket_id: Optional[str] = None
    provider: Optional[str] = None
    latency_ms: float = 0.0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class Orchestrator:
    def __init__(self, session_store: SessionStore | None = None):
        self.session_store = session_store or default_store
        self._histories: dict[str, list[dict[str, Any]]] = {}

    def handle_message(self, session_token: str, user_message: str) -> TurnResult:
        start = time.time()
        language = _detect_language(user_message)

        try:
            session = self.session_store.validate(session_token)
        except (InvalidSession, ExpiredSession):
            return TurnResult(
                disposition="REAUTH_REQUIRED",
                response_text=REAUTH_MESSAGE[language],
                latency_ms=(time.time() - start) * 1000,
            )

        customer_id = session.customer_id
        history = self._histories.setdefault(session_token, [])

        # Safety-critical keyword check runs before any LLM/tool call, so it
        # can't be talked out of firing by clever phrasing downstream.
        if contains_escalation_signal(user_message):
            decision = Decision(
                disposition=Disposition.ESCALATE,
                reason="Utterance contains a fraud/dispute/safety signal.",
                open_questions=["Verify identity beyond session token before acting."],
            )
            ticket = escalation.escalate(customer_id, session_token, user_message, decision, actions_taken=[], language=language)
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": ESCALATION_MESSAGE[language]})
            return TurnResult(
                disposition=Disposition.ESCALATE.value,
                response_text=ESCALATION_MESSAGE[language],
                ticket_id=ticket.ticket_id,
                latency_ms=(time.time() - start) * 1000,
            )

        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": user_message}]
        client = get_default_client()
        try:
            response = client.chat(messages, tools=TOOL_SCHEMAS)
        except LLMUnavailable as exc:
            decision = Decision(disposition=Disposition.ESCALATE, reason=f"LLM unavailable: {exc}", open_questions=["Both LLM providers failed; needs manual handling."])
            ticket = escalation.escalate(customer_id, session_token, user_message, decision, actions_taken=[], language=language)
            return TurnResult(
                disposition=Disposition.ESCALATE.value,
                response_text=ESCALATION_MESSAGE[language],
                ticket_id=ticket.ticket_id,
                latency_ms=(time.time() - start) * 1000,
            )

        history.append({"role": "user", "content": user_message})

        if not response.tool_calls:
            content = response.content or ABSTAIN_MESSAGE[language]
            disposition = Disposition.CLARIFY.value if "?" in content else Disposition.ABSTAIN.value
            history.append({"role": "assistant", "content": content})
            return TurnResult(
                disposition=disposition,
                response_text=content,
                provider=response.provider,
                latency_ms=(time.time() - start) * 1000,
            )

        # Only the first tool call is executed per turn; multi-call chaining
        # is out of scope for this workflow's complexity.
        call = response.tool_calls[0]
        tool_name = call["name"]
        try:
            raw_args = json.loads(call["arguments"]) if call["arguments"] else {}
        except json.JSONDecodeError:
            raw_args = {}
        raw_args.pop("customer_id", None)  # never trust an LLM-supplied identity
        intent = TOOL_NAME_TO_INTENT.get(tool_name, tool_name)

        tool_fn = TOOL_FUNCTIONS.get(tool_name)
        result, error = None, None
        if tool_fn is None:
            error = ToolError(f"Unknown tool requested: {tool_name}")
        else:
            missing = [a for a in _REQUIRED_ARGS_BY_TOOL.get(tool_name, []) if not raw_args.get(a)]
            if missing:
                error = MissingSlot(f"{tool_name} called without required argument(s): {missing}", missing_slots=missing)
            else:
                try:
                    result = tool_fn(customer_id, **raw_args)
                except ToolError as exc:
                    error = exc
                except Exception as exc:  # noqa: BLE001 - bounded fallback for unexpected tool/DB failures
                    error = ToolError(f"Unexpected tool failure calling {tool_name}: {exc}")

        decision = decide_after_tool_call(intent, error, result)
        actions_taken = [{"tool": tool_name, "args": raw_args, "success": error is None, "error": str(error) if error else None}]

        if decision.disposition == Disposition.AUTO_RESOLVE:
            tool_message = {"role": "tool", "tool_call_id": call["id"], "name": tool_name, "content": json.dumps(result, default=str)}
            follow_up_messages = messages + [
                {"role": "assistant", "content": None, "tool_calls": [{"id": call["id"], "type": "function", "function": {"name": tool_name, "arguments": call["arguments"]}}]},
                tool_message,
            ]
            try:
                final = client.chat(follow_up_messages)
                final_text = final.content or str(result)
            except LLMUnavailable:
                final_text = f"[verificado] {result}"
            history.append({"role": "assistant", "content": final_text})
            return TurnResult(
                disposition=Disposition.AUTO_RESOLVE.value,
                response_text=final_text,
                verified_facts={"tool": tool_name, "result": result},
                provider=response.provider,
                latency_ms=(time.time() - start) * 1000,
                tool_calls=actions_taken,
            )

        if decision.disposition == Disposition.CLARIFY:
            msg = {
                "es": "Necesito un dato más para continuar: ¿podrías indicarme a qué producto te refieres?",
                "pt": "Preciso de mais uma informação: você poderia indicar a qual produto se refere?",
            }[language]
            history.append({"role": "assistant", "content": msg})
            return TurnResult(disposition=Disposition.CLARIFY.value, response_text=msg, provider=response.provider, latency_ms=(time.time() - start) * 1000, tool_calls=actions_taken)

        # ESCALATE
        ticket = escalation.escalate(customer_id, session_token, user_message, decision, actions_taken=actions_taken, language=language)
        history.append({"role": "assistant", "content": ESCALATION_MESSAGE[language]})
        return TurnResult(
            disposition=Disposition.ESCALATE.value,
            response_text=ESCALATION_MESSAGE[language],
            ticket_id=ticket.ticket_id,
            provider=response.provider,
            latency_ms=(time.time() - start) * 1000,
            tool_calls=actions_taken,
        )


default_orchestrator = Orchestrator()
