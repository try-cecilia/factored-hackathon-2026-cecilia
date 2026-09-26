"""Token prices used to turn measured token usage into cost.

ASSUMPTION, not a measurement: USD list prices per 1M tokens as known at
authoring time (2026-09). Verify against the providers' current pricing
pages before quoting any cost figure externally; every eval report prints
PRICING_AS_OF next to its cost numbers for exactly that reason.
"""
from __future__ import annotations

PRICING_AS_OF = "2026-09 (assumed list prices; verify before external use)"

# (provider, model) -> (input_usd_per_mtok, output_usd_per_mtok)
PRICES_USD_PER_MTOK = {
    ("groq", "llama-3.3-70b-versatile"): (0.59, 0.79),
    ("groq", "llama-3.1-8b-instant"): (0.05, 0.08),
    ("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo"): (0.88, 0.88),
}


def cost_usd(provider: str | None, model: str | None, prompt_tokens: int, completion_tokens: int) -> float | None:
    price = PRICES_USD_PER_MTOK.get((provider or "", model or ""))
    if price is None:
        return None
    return (prompt_tokens * price[0] + completion_tokens * price[1]) / 1_000_000
