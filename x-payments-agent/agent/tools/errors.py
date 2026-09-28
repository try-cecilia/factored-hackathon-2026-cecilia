"""Errors raised by the deterministic tool layer.

Each maps to exactly one disposition in agent/policy/router.py — the LLM
never decides what a tool failure means:

  MissingSlot / InvalidArgument / ResourceNotFound -> CLARIFY
  NotApplicable                                    -> answered (AUTO_RESOLVE)
  PermissionDenied                                 -> ESCALATE (security)
  DataUnavailable                                  -> ESCALATE (data)
  any other ToolError / unexpected exception       -> ESCALATE (tool failure)
"""
from __future__ import annotations


class ToolError(Exception):
    """Base class for tool-layer failures."""


class PermissionDenied(ToolError):
    """The authenticated customer does not own the requested resource.

    Fires from database ownership checks only — never from anything the LLM
    or the user said — so no prompt phrasing can bypass it.
    """

    def __init__(self, message: str, resource_id: str | None = None):
        super().__init__(message)
        self.resource_id = resource_id


class ResourceNotFound(ToolError):
    """Requested product/transaction does not exist."""


class DataUnavailable(ToolError):
    """The data needed for a verified answer is missing, null, or too stale."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


class NotApplicable(ToolError):
    """The question is valid but doesn't apply to this product (e.g. payment
    status of a savings account). Answerable — not a reason to transfer."""

    def __init__(self, message: str, payload: dict | None = None):
        super().__init__(message)
        self.payload = payload or {}


class MissingSlot(ToolError):
    """A required argument is missing or ambiguous (e.g. which product)."""

    def __init__(self, message: str, missing_slots: list[str] | None = None):
        super().__init__(message)
        self.missing_slots = missing_slots or []


class InvalidArgument(MissingSlot):
    """An argument was present but malformed (bad date, unknown currency)."""
