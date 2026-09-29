"""Small-sample statistics used by every eval report.

Wilson score intervals for proportions (well-behaved at 0% / 100% and small
n, unlike the normal approximation), and the "rule of three" for zero
observed events: with 0 failures in n trials, the 95% upper bound on the
true failure rate is about 3/n — which is why "0 unsafe outcomes" in a small
test set does not mean zero risk (the brief says the same).
"""
from __future__ import annotations

import math


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(successes: int, n: int) -> dict:
    lo, hi = wilson(successes, n)
    return {"k": successes, "n": n, "rate": round(successes / n, 4) if n else None,
            "ci95": [round(lo, 4), round(hi, 4)] if n else None}


def zero_event_upper_bound(n: int) -> float | None:
    return round(3 / n, 4) if n else None


def fmt(r: dict) -> str:
    if not r or r.get("n") in (0, None):
        return "n/a (n=0)"
    return f"{100 * r['rate']:.1f}% [{100 * r['ci95'][0]:.1f}–{100 * r['ci95'][1]:.1f}] (n={r['n']})"
