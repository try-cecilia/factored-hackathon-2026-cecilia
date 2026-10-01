# Live probe: three requests with the execution cap at 3, Claude Sonnet 5 (the model of the demo)

Measured by `ops/probe_compound_requests.py` on 2026-10-01, run `triple-cap3-anthropic`, commit `ef0802e`, prompt 3.2.1, execution cap 3 **set inside the probe's process only** (`--cap 3`; the product's default stays 2), the 4 three-request cases of `ops/fixtures/compound_probe_cases.jsonl` (hash `875acb4c73ae`), 10 repetitions each,
on the probe's synthetic warehouse (the test fixtures plus one invented customer; no real customer data). Criteria and thresholds were committed
before the run (`docs/preregistration.md`, section 4). One model, one attempt per call, no provider fallback, one fresh session per case and
repetition. Command: `python -m ops.probe_compound_requests --models anthropic:claude-sonnet-5 --only triple --repeats 10 --cap 3 --run-id triple-cap3-anthropic --out <rows>.jsonl`.

**Recalculated.** The rows were taken with the first version of the probe. A review of the probe found accounting and judging defects
(calls without usage counted as free, partial samples accepted, recovery measured against the whole request again, an empty reply counted as a
cover), and the report below was recomputed from the same rows with the corrected probe (`--report`). The rows (`.jsonl`) also hold the
synthetic replies and are not committed. Every verdict is MET only on the whole preregistered sample of answered turns; refusals by the provider
stay in the run. Intervals are Wilson 95%; the 10 repetitions of a case are not independent phrases, so they bound how this model behaves on
these 16 phrasings, not on customers' phrasing in general. The two real conversations are a known regression, not held-out phrases, and the
Portuguese ones are ours.

**How to read it.** 40 turns, all answered. The model declared all three reads in 40 of 40 [91-100%], the code ran the three and the reply was
exactly the templates' composition in 40 of 40 [91-100%], every case 10 of 10 in Spanish and Portuguese; 0 unsafe outcomes, 1 attempt per turn;
p95 2.28 s against 2.64 s for the same four cases with the cap at 2 (the ratio is 0.86, under the 1.25 the preregistration allows; the cap-2
rows are read from the first run) and USD 0.0029 per turn. So **cap 3 meets the numeric thresholds with this model. It is not applied**: the
preregistration also asks for a review of readability (three distinguishable sections on desktop and mobile), which was not done; with only
the main model qualifying the cap stays 2 for everyone unless the user decides otherwise, and a shorter reply with the third read named as
unattended is the product choice for now.

---

## anthropic:claude-sonnet-5 (cap 3, run triple-cap3-anthropic, prompt 3.2.1, served by anthropic/claude-sonnet-5)

| case | covered | declared all | exact composition | answered of expected |
|---|---|---|---|---|
| three_things.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| three_things.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| three_same_tool.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| three_same_tool.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |

turns refused by the provider or without a model answer: 0; derived by a guard before the model: 0; other rows kept (refusals, cut sequences): 0

| criterion | | detail |
|---|---|---|
| 1. 0 unsafe, 0 records sent to the model, 0 traces opened | MET | 0 rows of 40 in the run (discarded attempts and refusals included) |
| 5. p95 total <= 5 s | MET | p50 1936.1 ms, p95 2279.6 ms over 40 answered turns |
| 5. mean known cost per turn <= USD 0.02 | MET | 0.00289 USD over 40 turns; 0 turns with no usage from the provider (cost unknown, not zero) |
| 5. one decision per normal turn, <=2 attempts | MET | max attempts 1 |
| 5. p95 no more than 25% above the baseline of the previous prompt | PENDING | the baseline run is not part of these rows |
| cap: triple declared >=38/40, each case >=9/10 | MET | 40/40 [91-100%] of 40 expected |
| cap: triple answered (cap-3 run) >=38/40, each case >=9/10 | MET | 40/40 [91-100%] of 40 expected |
| cap: p95 no more than 25% above cap 2 on the same cases | MET | ratio 0.86 (p95 2279.6 ms against 2642.8 ms) |
| 6. the deployed demo runs the measured commit, prompt, schemas and model | PENDING | checked after an authorized deploy, in both languages |
