# ADR-004: the deployed model is Claude Sonnet 5

- **Status:** accepted, recorded 2026-09-29.
- **Context:** the language model only interprets (ADR-001): it picks the tool and its arguments and nothing it writes
  reaches the customer. The choice of model therefore moves how many requests the system can resolve without a
  person, and not whether the outcome is safe. We measured two candidates on the same held-out sample.

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

## Trade-offs

- **The sample is 132 of the test cases, not all.** Zero unsafe in 132 bounds the true rate only below about 2.3%. The
  intervals on resolution are wide (a country by segment cell holds 15 to 20 in-scope cases). The offline runs with
  scripted models cover the whole workload, and they show that safety does not depend on the model
  (`SYSTEM_EVAL_ADVERSARIAL.md`, `ABLATION.md`).
- **Haiku is faster** at the median, not at p95. A person's average inquiry takes about 341 s, so 0.6 s does not
  decide anything at this workload.
- **The vendor is a dependency.** The fallbacks above (Groq, local, limited mode) exist for that, and each is measured
  or reported as not yet measured in `LIMITATIONS.md`.
- The Groq model ran only on a small sample (42 of the 226 reserved failure cases), with 3 not handled as the policy
  asks, so it is a fallback and not a default.
