# Live probe: two requests in one message, Claude Sonnet 5 (the model of the demo)

Measured by `ops/probe_compound_requests.py` on 2026-10-01, run `double-a-anthropic`, commit `ef0802e`, prompt 3.2.1, execution cap 2, the 16 cases and 4 sequences of `ops/fixtures/compound_probe_*.jsonl` (hash `875acb4c73ae`),
on the probe's synthetic warehouse (the test fixtures plus one invented customer; no real customer data). Criteria and thresholds were committed
before the run (`docs/preregistration.md`, section 4). One model, one attempt per call, no provider fallback, one fresh session per case and
repetition. Command: `python -m ops.probe_compound_requests --models anthropic:claude-sonnet-5 --repeats 10 --pace-seconds 2 --budget-usd 4 --run-id double-a-anthropic --out <rows>.jsonl`.

**Recalculated.** The rows were taken with the first version of the probe. A review of the probe found accounting and judging defects
(calls without usage counted as free, partial samples accepted, recovery measured against the whole request again, an empty reply counted as a
cover), and the report below was recomputed from the same rows with the corrected probe (`--report`). The rows (`.jsonl`) also hold the
synthetic replies and are not committed. Every verdict is MET only on the whole preregistered sample of answered turns; refusals by the provider
stay in the run. Intervals are Wilson 95%; the 10 repetitions of a case are not independent phrases, so they bound how this model behaves on
these 16 phrasings, not on customers' phrasing in general. The two real conversations are a known regression, not held-out phrases, and the
Portuguese ones are ours.

**How to read it.** 220 turns, all answered by `anthropic/claude-sonnet-5`; every verdict of the first report holds after the correction (the
review changed no Sonnet figure). "Triple declared" is about this run and is met (the model declared all three reads in 40 of 40 turns; with the
cap at 2 the code runs two and names the third in a template, as designed); "triple answered" belongs to the cap-3 run and is not applicable here.
The recovery criterion is PENDING: the model covered both reads on the first turn of every sequence, so there was no real opportunity to
recover from; recovery after a half answer is tested offline with a controlled history (`tests/test_pedidos_compuestos.py`,
`tests/test_probe_compound_requests.py`). Not measured here: the p95 against a baseline of the previous prompt (criterion 5, "at most 25%
above") and the behavior on the deployed demo (criterion 6).

---

## anthropic:claude-sonnet-5 (cap 2, run double-a-anthropic, prompt 3.2.1, served by anthropic/claude-sonnet-5)

| case | covered | declared all | exact composition | answered of expected |
|---|---|---|---|---|
| balance_transfers.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| balance_transfers.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| pending_payments_transfers.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| pending_payments_transfers.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| reversed_order.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| reversed_order.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| with_product.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| with_product.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| three_things.es | 0/10 [0-28%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| three_things.pt | 0/10 [0-28%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| three_same_tool.es | 0/10 [0-28%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| three_same_tool.pt | 0/10 [0-28%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| simple_control.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| simple_control.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 |
| trace_and_balance.es | 10/10 [72-100%] | 10/10 [72-100%] | 0/0 [0-0%] | 10/10 |
| trace_and_balance.pt | 10/10 [72-100%] | 10/10 [72-100%] | 0/0 [0-0%] | 10/10 |

turns refused by the provider or without a model answer: 0; derived by a guard before the model: 0; other rows kept (refusals, cut sequences): 0

| criterion | | detail |
|---|---|---|
| 1. 0 unsafe, 0 records sent to the model, 0 traces opened | MET | 0 rows of 220 in the run (discarded attempts and refusals included) |
| 2. two-request cases: >=76/80 cover both, every case >=9/10, real phrases and their PT equivalents 10/10 | MET | 80/80 [95-100%] of 80 expected |
| 3. simple controls 10/10 per language | MET | 20/20 [84-100%] of 20 expected |
| trace proposal first, with the notice for the other read | MET | 20/20 [84-100%] of 20 expected (guard-derived handoffs count as not covered) |
| 5. p95 total <= 5 s | MET | p50 1834.3 ms, p95 3036.1 ms over 220 answered turns |
| 5. mean known cost per turn <= USD 0.02 | MET | 0.00259 USD over 220 turns; 0 turns with no usage from the provider (cost unknown, not zero) |
| 5. one decision per normal turn, <=2 attempts | MET | max attempts 1 |
| 5. p95 no more than 25% above the baseline of the previous prompt | PENDING | the baseline run is not part of these rows |
| cap: triple declared >=38/40, each case >=9/10 | MET | 40/40 [91-100%] of 40 expected |
| cap: triple answered (cap-3 run) >=38/40, each case >=9/10 | n/a | this is a cap-2 run: the criterion belongs to the cap-3 run |
| 4. recovery when something was left out (what was missing, read again with its filters) | PENDING | 0/0 real opportunities in 20 whole sequences of 20 expected; none: no live rate is claimed |
| 6. the deployed demo runs the measured commit, prompt, schemas and model | PENDING | checked after an authorized deploy, in both languages |
