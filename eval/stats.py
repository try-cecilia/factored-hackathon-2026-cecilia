"""Small-sample statistics used by every eval report.

Wilson score intervals for proportions (well-behaved at 0% / 100% and small
n, unlike the normal approximation), and the "rule of three" for zero
observed events: with 0 failures in n trials, the 95% upper bound on the
true failure rate is about 3/n — which is why "0 unsafe outcomes" in a small
test set does not mean zero risk (the brief says the same).
"""
from __future__ import annotations

import math
import random


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


def paired_accuracy(y_true: list, pred_a: list, pred_b: list, resamples: int = 10_000, seed: int = 0) -> dict:
    """Accuracy of B minus accuracy of A on the very same items (two systems scored on one held-out set).

    Two intervals that overlap do not say the difference is noise, and two that do not are a conservative test:
    the items are shared, so the difference is estimated on them directly. `diff_ci95` is a percentile bootstrap
    over items (seeded, so the report is reproducible); `mcnemar_p` is the exact two-sided test on the items where
    exactly one of the two is right."""
    n = len(y_true)
    a_ok = [p == t for p, t in zip(pred_a, y_true)]
    b_ok = [p == t for p, t in zip(pred_b, y_true)]
    only_b, only_a = sum(b and not a for a, b in zip(a_ok, b_ok)), sum(a and not b for a, b in zip(a_ok, b_ok))
    d = only_a + only_b
    p = 1.0 if d == 0 else min(1.0, 2 * sum(math.comb(d, i) for i in range(min(only_a, only_b) + 1)) / 2 ** d)
    rng = random.Random(seed)
    diffs = sorted(sum(b_ok[i] - a_ok[i] for i in idx) / n for idx in ([rng.randrange(n) for _ in range(n)] for _ in range(resamples)))
    lo, hi = diffs[int(0.025 * resamples)], diffs[int(0.975 * resamples) - 1]
    return {"n": n, "only_b_right": only_b, "only_a_right": only_a, "diff": round((sum(b_ok) - sum(a_ok)) / n, 4),
            "diff_ci95": [round(lo, 4), round(hi, 4)], "mcnemar_p": round(p, 6), "resamples": resamples, "seed": seed}


def zero_event_upper_bound(n: int) -> float | None:
    return round(3 / n, 4) if n else None


def fmt(r: dict) -> str:
    if not r or r.get("n") in (0, None):
        return "n/a (n=0)"
    return f"{100 * r['rate']:.1f}% [{100 * r['ci95'][0]:.1f}–{100 * r['ci95'][1]:.1f}] (n={r['n']})"
