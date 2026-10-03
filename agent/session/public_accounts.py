"""The public sandbox accounts: test customers whose PINs the jury demo publishes, so many visitors share each one.

DEMO_PUBLIC_CUSTOMERS is the single canonical list (ops/entrypoint.sh fills it with the demo roles in the sandbox). It is read
on each call, so nothing cached outlives a change; empty or unset means no public account at all. A session of one of these
accounts is one visitor, not the customer: what belongs to a session (its cases, their news) is never shown to another one.
"""
from __future__ import annotations

import os


def public_customer_ids() -> list[str]:
    """The public accounts, in the order configured."""
    return list(dict.fromkeys(c.strip() for c in os.environ.get("DEMO_PUBLIC_CUSTOMERS", "").split(",") if c.strip()))


def is_shared(customer_id: str) -> bool:
    """Whether this account's sessions belong to different people (it is a public sandbox account)."""
    return customer_id in public_customer_ids()
