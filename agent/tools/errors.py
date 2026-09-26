"""Errors raised by the deterministic tool layer.

These are the signal the policy/decide layer (agent/policy/router.py) uses to
route to CLARIFY or ESCALATE — the LLM never gets to decide what happens on
its own; it only sees the outcome after the policy layer has acted on it.
"""


class ToolError(Exception):
    """Base class for tool-layer failures."""


class PermissionDenied(ToolError):
    """Raised when the authenticated customer does not own the requested resource.

    This is the guardrail against prompt injection / unauthorized access: it
    fires purely from database ownership checks, never from anything the LLM
    or the user said, so no amount of "ignore previous instructions" phrasing
    can bypass it.
    """


class ResourceNotFound(ToolError):
    """Requested product/transaction/etc. does not exist."""


class DataUnavailable(ToolError):
    """Data exists but is incomplete/null in a way that blocks a verified answer
    (e.g. no exchange rate for the requested date and no reasonable fallback)."""


class MissingSlot(ToolError):
    """The LLM tried to call a tool without a required argument (e.g. no
    product_id for payment_status). Routes to CLARIFY, not ESCALATE — this
    is a normal "need more info" case, not a policy/security failure."""

    def __init__(self, message: str, missing_slots: list[str] | None = None):
        super().__init__(message)
        self.missing_slots = missing_slots or []
