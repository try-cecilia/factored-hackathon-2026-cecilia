# Live probe: two requests in one message, GPT-OSS 120B on Groq (the fallback)

Measured by `ops/probe_compound_requests.py` on 2026-10-01, run `double-a-groq`, commit `ef0802e`, prompt 3.2.1, execution cap 2, the 16 cases and 4 sequences of `ops/fixtures/compound_probe_*.jsonl` (hash `875acb4c73ae`),
on the probe's synthetic warehouse (the test fixtures plus one invented customer; no real customer data). Criteria and thresholds were committed
before the run (`docs/preregistration.md`, section 4). One model, one attempt per call, no provider fallback, one fresh session per case and
repetition. Command: `python -m ops.probe_compound_requests --models groq:openai/gpt-oss-120b --repeats 10 --pace-seconds 2 --budget-usd 1 --run-id double-a-groq --out <rows>.jsonl`.

**Recalculated.** The rows were taken with the first version of the probe. A review of the probe found accounting and judging defects
(calls without usage counted as free, partial samples accepted, recovery measured against the whole request again, an empty reply counted as a
cover), and the report below was recomputed from the same rows with the corrected probe (`--report`). The rows (`.jsonl`) also hold the
synthetic replies and are not committed. Every verdict is MET only on the whole preregistered sample of answered turns; refusals by the provider
stay in the run. Intervals are Wilson 95%; the 10 repetitions of a case are not independent phrases, so they bound how this model behaves on
these 16 phrasings, not on customers' phrasing in general. The two real conversations are a known regression, not held-out phrases, and the
Portuguese ones are ours.

**How to read it. These figures are partial.** Of the 220 planned turns, 53 were answered by `groq/openai/gpt-oss-120b` and 167 were refused by
the provider (the account's rate limit, HTTP 429, in the run's log; the probe records them as the model being down and counts none of them as a
result). Every criterion that needs the whole sample is therefore PENDING, except the ones a partial sample already settles: two-request cases
cannot reach 76 of 80 (0 of 15 covered, and 65 turns were never answered), the three-request declarations cannot reach 38 of 40, and the trace
proposals are 0 of 6. In every two- and three-request turn that was answered (22 of 22) the model declared exactly one read, so the second was
never asked for; the simple controls were answered correctly (4 of 4, too few for the criterion). That matches Groq's documentation, which lists
this model without parallel tool use. **Cost:** 13 of the 53 answered turns carried no usage (the provider sent none, or the tool call was
recovered), so their cost is unknown, not zero, and the cost criterion is PENDING (the mean over the 40 turns with usage is shown). **Recovery:**
5 sequences were whole (all three turns answered) and in all 5 the follow-up read what had been left out with its filters; that is 5 of 5 in a
sample of 5 of 20, not a rate. The first version of this report said 0 of 8 because it asked the follow-up for the whole request again.
This is evidence that the limit is real, not a rate for the model; a complete run needs a key without that rate limit.

---

## groq:openai/gpt-oss-120b (cap 2, run double-a-groq, prompt 3.2.1, served by groq/openai/gpt-oss-120b)

| case | covered | declared all | exact composition | answered of expected |
|---|---|---|---|---|
| balance_transfers.es | 0/3 [0-56%] | 0/3 [0-56%] | 3/3 [44-100%] | 3/10 |
| balance_transfers.pt | 0/1 [0-79%] | 0/1 [0-79%] | 1/1 [21-100%] | 1/10 |
| pending_payments_transfers.es | 0/2 [0-66%] | 0/2 [0-66%] | 2/2 [34-100%] | 2/10 |
| pending_payments_transfers.pt | 0/1 [0-79%] | 0/1 [0-79%] | 1/1 [21-100%] | 1/10 |
| reversed_order.es | 0/2 [0-66%] | 0/2 [0-66%] | 2/2 [34-100%] | 2/10 |
| reversed_order.pt | 0/2 [0-66%] | 0/2 [0-66%] | 2/2 [34-100%] | 2/10 |
| with_product.es | 0/1 [0-79%] | 0/1 [0-79%] | 1/1 [21-100%] | 1/10 |
| with_product.pt | 0/3 [0-56%] | 0/3 [0-56%] | 3/3 [44-100%] | 3/10 |
| three_things.es | 0/1 [0-79%] | 0/1 [0-79%] | 1/1 [21-100%] | 1/10 |
| three_things.pt | 0/2 [0-66%] | 0/2 [0-66%] | 2/2 [34-100%] | 2/10 |
| three_same_tool.es | 0/1 [0-79%] | 0/1 [0-79%] | 1/1 [21-100%] | 1/10 |
| three_same_tool.pt | 0/3 [0-56%] | 0/3 [0-56%] | 3/3 [44-100%] | 3/10 |
| simple_control.es | 2/2 [34-100%] | 2/2 [34-100%] | 2/2 [34-100%] | 2/10 |
| simple_control.pt | 2/2 [34-100%] | 2/2 [34-100%] | 2/2 [34-100%] | 2/10 |
| trace_and_balance.es | 0/6 [0-39%] | 0/6 [0-39%] | 0/0 [0-0%] | 6/10 |
| trace_and_balance.pt | 0/0 [0-0%] | 0/0 [0-0%] | 0/0 [0-0%] | 0/10 |

turns refused by the provider or without a model answer: 167; derived by a guard before the model: 0; other rows kept (refusals, cut sequences): 0

| criterion | | detail |
|---|---|---|
| 1. 0 unsafe, 0 records sent to the model, 0 traces opened | PENDING | 0 rows of 220 in the run (discarded attempts and refusals included) |
| 2. two-request cases: >=76/80 cover both, every case >=9/10, real phrases and their PT equivalents 10/10 | NOT MET | 0/15 [0-20%] of 80 expected |
| 3. simple controls 10/10 per language | PENDING | 4/4 [51-100%] of 20 expected |
| trace proposal first, with the notice for the other read | NOT MET | 0/6 [0-39%] of 20 expected (guard-derived handoffs count as not covered) |
| 5. p95 total <= 5 s | PENDING | p50 717.2 ms, p95 1525.2 ms over 53 answered turns |
| 5. mean known cost per turn <= USD 0.002 | PENDING | 0.00037 USD over 40 turns; 13 turns with no usage from the provider (cost unknown, not zero) |
| 5. one decision per normal turn, <=2 attempts | PENDING | max attempts 1 |
| 5. p95 no more than 25% above the baseline of the previous prompt | PENDING | the baseline run is not part of these rows |
| cap: triple declared >=38/40, each case >=9/10 | NOT MET | 0/7 [0-35%] of 40 expected |
| cap: triple answered (cap-3 run) >=38/40, each case >=9/10 | n/a | this is a cap-2 run: the criterion belongs to the cap-3 run |
| 4. recovery when something was left out (what was missing, read again with its filters) | PENDING | 5/5 real opportunities in 5 whole sequences of 20 expected; 0 answered with the repeat notice though something was missing |
| 6. the deployed demo runs the measured commit, prompt, schemas and model | PENDING | checked after an authorized deploy, in both languages |
