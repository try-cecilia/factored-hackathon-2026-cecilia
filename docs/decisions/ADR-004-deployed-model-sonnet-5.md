# ADR-004: the deployed model is Claude Sonnet 5

- **Status:** accepted, recorded 2026-09-29.
- **Context:** the language model only interprets (ADR-001): it picks the tool and its arguments and nothing it writes
  reaches the customer. The controls checked offline (the ownership check, replies written by code, never sending a
  customer record to the model) hold whatever the model does, so the choice of model mostly moves how many requests the
  system can resolve without a person. It is not irrelevant to safety: a product the model names by its alias is taken
  as given (`resolve_product_ref` in `agent/core/orchestrator.py` does not compare it with the digits the customer
  wrote), so a model that picks the wrong one of the customer's own products gets a correct answer about the wrong
  product (Haiku 4.5, 2026-10-03 and 2026-10-04, below). We measured two candidates on the same
  held-out cases.

## Decision

`render.yaml` deploys **Claude Sonnet 5**. Claude Haiku 4.5 stays selectable, and a free Groq key
(`openai/gpt-oss-120b`) or a local model keeps the assistant running when Anthropic is unavailable or its budget is
spent; without any key the system answers in limited mode (plain balances, everything else to a person).

The measurement (`eval/reports/SYSTEM_EVAL_LIVE.md`): a stratified sample of 132 held-out cases, every case type in both
languages, three runs each, Wilson 95% intervals.

| | Claude Sonnet 5 | Claude Haiku 4.5 |
|---|---|---|
| Safe automated resolution | 95.0% [86.3–98.3] | 78.3% [66.4–86.9] |
| Escalation recall | 100% | 88.9% (4 missed) |
| Unsafe outcomes | 0 / 132 in each run | 0 / 132 in each run |
| Latency per case, p50 / p95 | 1.8 s / 3.9 s | 1.2 s / 3.8 s |
| Model cost per safe resolution | USD 0.0029 | USD 0.0057 |

Sonnet 5 resolves more, misses no escalation and costs less per safe resolution as measured here. We did not
investigate why the cheaper model costs more per safe resolution (more calls, more tokens per call, or fewer
resolutions to spread the spend over), so the ranking is a measurement and not an explanation. The two are equal on the
outcome that matters most: no unsafe outcome in either.

**Measured again on 2026-10-02**, on the code the demo runs (prompt 3.2.1), on 138 held-out cases (3 of every case type
in each language), three runs each. The decision holds:

| | Claude Sonnet 5 | Claude Haiku 4.5 |
|---|---|---|
| Safe automated resolution | 95.0% [86.3–98.3] | 78.3% [66.4–86.9] |
| Escalation recall | 100% | 78.6% (9 missed) |
| Unsafe outcomes | 0 / 138 in each run | 0 / 138 in runs 1 and 3; 1 / 138 in run 2 |
| Latency per case, p50 / p95 | 1.9 s / 4.2 s | 1.1 s / 4.2 s |
| Model cost per safe resolution | USD 0.0034 | USD 0.0079 |

The two are no longer equal on safety: Haiku 4.5 had one reply the judge could not rebuild from the templates
(`text_outside_the_templates`), in its second run. Only run 1 keeps its rows, so that case could not be inspected
(`LIMITATIONS.md`, items 1 and 5). Sonnet 5 had none in any run.

**Measured again on 2026-10-03**, on the code the other reports measure (policy fingerprint `ad2212c4c416`, commit
`8578e450`; the run of 2026-10-02 was on older code, `a14b84b7ad04`), with the same protocol: the same 138 cases, three
runs each, Anthropic only. The report now keeps the rows of every run. The decision holds:

| | Claude Sonnet 5 | Claude Haiku 4.5 |
|---|---|---|
| Safe automated resolution | 95.0% [86.3–98.3] | 76.7% [64.6–85.6] |
| Escalation recall | 97.6% (1 missed, in runs 1 and 2) | 78.6% (9 missed) |
| Unsafe outcomes | 0 / 138 in each run | 0 / 138 in runs 1 and 3; 1 / 138 in run 2 |
| Latency per case, p50 / p95 | 1.2 s / 2.6 s | 1.0 s / 3.8 s |
| Model cost per safe resolution | USD 0.0034 | USD 0.0080 |

Haiku 4.5's unsafe outcome is now one that can be inspected: asked for the savings account ending 3862, it chose another
of the customer's own products and the reply listed that product's movements (`wrong_account_or_figure`). Sonnet 5 had
none, and its one missed escalation (a Portuguese deposit that never arrived, asked about instead of handed over) is the
first it has had in these runs.

**Measured again on 2026-10-04, on the whole test split**: all 548 held-out cases, three runs each, Anthropic only, on
the code the other reports measure (prompt 3.3.0, policy fingerprint `0a68b7fa6bc2`, commit `96d1f2d8`). The decision
holds, with intervals about half as wide:

| | Claude Sonnet 5 | Claude Haiku 4.5 |
|---|---|---|
| Safe automated resolution | 97.1% [94.0–98.6] | 79.0% [73.4–83.7] |
| Escalation recall | 99.4% (1 missed, in run 1) | 78.0% (37 missed) |
| Unsafe outcomes | 0 / 548 in each run | 0 / 548 in runs 1 and 3; 1 / 548 in run 2 |
| Latency per case, p50 / p95 | 1.4 s / 3.0 s | 1.1 s / 4.0 s |
| Model cost per safe resolution | USD 0.0034 | USD 0.0084 |

Haiku 4.5's unsafe outcome is of the same kind as on 2026-10-03: asked for the balance of the savings account ending
1128, it chose another of the customer's own products and the reply showed that one. Sonnet 5 had none in any run, and
its one missed escalation is again a Portuguese deposit that never arrived, in run 1 only.

## Trade-offs

- **The cases are one synthetic test split.** Zero unsafe in 548 bounds the true rate only below about 0.55%. A
  segment or country cell holds 58 to 80 in-scope cases, and a language 119. The offline runs with
  scripted models cover the same workload, and they show that the controls checked offline hold with a deliberately
  bad model (`SYSTEM_EVAL_ADVERSARIAL.md`, `ABLATION.md`). They do not show that the model's choice of product
  cannot matter: the scripted models do not pick the wrong one of the customer's own products, and Haiku 4.5 did, once
  in each of the last two measurements.
- **Haiku is faster** at the median (1.1 s against 1.4 s on 2026-10-04), not at p95 (4.0 s against 3.0 s). A
  person's average inquiry takes about 341 s, so ≈0.3 s does not decide anything at this workload.
- **The vendor is a dependency.** The fallbacks above (Groq, local, limited mode) exist for that, and each is measured
  or reported as not yet measured in `LIMITATIONS.md`.
- The Groq model ran only on a small sample (42 of the 226 reserved failure cases), with 3 not handled as the policy
  asks, so it is a fallback and not a default.
