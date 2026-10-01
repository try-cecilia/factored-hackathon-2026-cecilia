# Live probe: three requests with the execution cap at 3, GPT-OSS 120B on Groq (the fallback)

Measured by `ops/probe_compound_requests.py` on 2026-10-01, run `triple-cap3-groq`, commit `ef0802e`, prompt 3.2.1, execution cap 3 **set inside the probe's process only** (`--cap 3`; the product's default stays 2), the 4 three-request cases of `ops/fixtures/compound_probe_cases.jsonl` (hash `875acb4c73ae`), 10 repetitions each,
on the probe's synthetic warehouse (the test fixtures plus one invented customer; no real customer data). Criteria and thresholds were committed
before the run (`docs/preregistration.md`, section 4). One model, one attempt per call, no provider fallback, one fresh session per case and
repetition. Command: `python -m ops.probe_compound_requests --models groq:openai/gpt-oss-120b --only triple --repeats 10 --cap 3 --run-id triple-cap3-groq --out <rows>.jsonl`.

**Recalculated.** The rows were taken with the first version of the probe. A review of the probe found accounting and judging defects
(calls without usage counted as free, partial samples accepted, recovery measured against the whole request again, an empty reply counted as a
cover), and the report below was recomputed from the same rows with the corrected probe (`--report`). The rows (`.jsonl`) also hold the
synthetic replies and are not committed. Every verdict is MET only on the whole preregistered sample of answered turns; refusals by the provider
stay in the run. Intervals are Wilson 95%; the 10 repetitions of a case are not independent phrases, so they bound how this model behaves on
these 16 phrasings, not on customers' phrasing in general. The two real conversations are a known regression, not held-out phrases, and the
Portuguese ones are ours.

**How to read it. These figures are partial.** Of the 40 planned turns, 16 were answered and 24 were refused by the provider's rate limit
(recorded as the model being down). In the 16 answered turns the model declared exactly one read each time (0 of 16 [0-19%]), so the cap changed
nothing: the limit of the fallback is in what the model declares (Groq's documentation lists it without parallel tool use), not in how many the
code runs. 4 of the 16 carried no usage, so the cost is PENDING; the p95 ratio against cap 2 is PENDING because the cap-2 triples are only
7 of 40.

---

## groq:openai/gpt-oss-120b (cap 3, run triple-cap3-groq, prompt 3.2.1, served by groq/openai/gpt-oss-120b)

| case | covered | declared all | exact composition | answered of expected |
|---|---|---|---|---|
| three_things.es | 0/4 [0-49%] | 0/4 [0-49%] | 4/4 [51-100%] | 4/10 |
| three_things.pt | 0/0 [0-0%] | 0/0 [0-0%] | 0/0 [0-0%] | 0/10 |
| three_same_tool.es | 0/10 [0-28%] | 0/10 [0-28%] | 10/10 [72-100%] | 10/10 |
| three_same_tool.pt | 0/2 [0-66%] | 0/2 [0-66%] | 2/2 [34-100%] | 2/10 |

turns refused by the provider or without a model answer: 24; derived by a guard before the model: 0; other rows kept (refusals, cut sequences): 0

| criterion | | detail |
|---|---|---|
| 1. 0 unsafe, 0 records sent to the model, 0 traces opened | PENDING | 0 turns of 16 answered |
| 5. p95 total <= 5 s | PENDING | p50 642.2 ms, p95 851.7 ms over 16 answered turns |
| 5. mean known cost per turn <= USD 0.002 | PENDING | 0.00032 USD over 12 turns; 4 turns with no usage from the provider (cost unknown, not zero) |
| 5. one decision per normal turn, <=2 attempts | PENDING | max attempts 1 |
| 5. p95 no more than 25% above the baseline of the previous prompt | PENDING | the baseline run is not part of these rows |
| cap: triple declared >=38/40, each case >=9/10 | NOT MET | 0/16 [0-19%] of 40 expected |
| cap: triple answered (cap-3 run) >=38/40, each case >=9/10 | NOT MET | 0/16 [0-19%] of 40 expected |
| cap: p95 no more than 25% above cap 2 on the same cases | PENDING | ratio 0.69 (p95 851.7 ms against 1227.4 ms) |
| 6. the deployed demo runs the measured commit, prompt, schemas and model | PENDING | checked after an authorized deploy, in both languages |
