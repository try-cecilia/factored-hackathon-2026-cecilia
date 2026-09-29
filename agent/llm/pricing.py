"""Token prices used to turn measured token usage into cost.

ASSUMPTION, not a measurement: USD list prices per 1M tokens as known at
authoring time (2026-09). Verify against the providers' current pricing
pages before quoting any cost figure externally; every eval report prints
PRICING_AS_OF next to its cost numbers for exactly that reason.
"""
from __future__ import annotations

import re

PRICING_AS_OF = "2026-09 (assumed list prices; verify before external use)"

# (provider, model) -> (input_usd_per_mtok, output_usd_per_mtok). Groq: console.groq.com/docs/models,
# read 2026-09-27 (Llama 3.3 70B is "contact sales" since it left the self-serve tiers). Anthropic: list
# prices from Anthropic's model reference (cached 2026-06-24); thinking tokens bill as output.
PRICES_USD_PER_MTOK = {
    ("groq", "openai/gpt-oss-120b"): (0.15, 0.60),
    ("groq", "openai/gpt-oss-20b"): (0.075, 0.30),
    ("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo"): (0.88, 0.88),
    ("anthropic", "claude-opus-5"): (5.0, 25.0),
    ("anthropic", "claude-opus-4-8"): (5.0, 25.0),  # server-side refusal fallback target
    ("anthropic", "claude-sonnet-5"): (2.0, 10.0),
    ("anthropic", "claude-haiku-4-5"): (1.0, 5.0),
}


CACHE_READ_FACTOR, CACHE_WRITE_FACTOR = 0.1, 1.25  # Anthropic prompt caching, 5-minute TTL


def cost_usd(provider: str | None, model: str | None, prompt_tokens: int, completion_tokens: int,
             cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float | None:
    key = (provider or "", model or "")
    # APIs may answer with a dated snapshot of the requested alias (claude-haiku-4-5-20251001)
    price = PRICES_USD_PER_MTOK.get(key) or PRICES_USD_PER_MTOK.get((key[0], re.sub(r"-\d{8}$", "", key[1])))
    if price is None:
        return None
    cached = cache_read_tokens * CACHE_READ_FACTOR + cache_write_tokens * CACHE_WRITE_FACTOR
    return ((prompt_tokens + cached) * price[0] + completion_tokens * price[1]) / 1_000_000
