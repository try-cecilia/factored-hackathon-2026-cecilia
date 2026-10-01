# Live probe: two requests in one message, GPT-OSS 120B on Groq (the fallback)

Measured by `ops/probe_compound_requests.py` on 2026-10-01, run `double-a-groq`, commit `ef0802e`, prompt 3.2.1, execution cap 2, cases
`ops/fixtures/compound_probe_cases.jsonl` and `compound_probe_sequences.jsonl` (hash `875acb4c73ae`), on the probe's synthetic
warehouse (the test fixtures plus one invented customer; no real customer data). Criteria and thresholds were committed before this run
(`docs/preregistration.md`, section 4). One model, one attempt per call, no provider fallback, one fresh session per case and repetition.
Command: `python -m ops.probe_compound_requests --models groq:openai/gpt-oss-120b --repeats 10 --pace-seconds 2 --budget-usd 1 --run-id double-a-groq --out <rows>.jsonl`.

The tables below are the probe's own report (`--report`), unedited. They hold counts, case ids and the probe's verdict per criterion; the
rows (`.jsonl`) also hold the synthetic replies and are not committed. Intervals are Wilson 95%; the 10 repetitions of a case are not
independent phrases, so they bound how this model behaves on these 16 phrasings, not on customers' phrasing in general. The two real
conversations are a known regression, not held-out phrases, and the Portuguese ones are ours.

**How to read it. These figures are partial.** Of the 220 planned turns, 53 were answered by `groq/openai/gpt-oss-120b` and 167 were
refused by the provider (the account's rate limit, HTTP 429; the probe records them as the model being down and counts none of them as a
result). The first table and criteria are those 53 turns (15 two-request, 7 three-request, 4 simple controls, 6 trace and balance, 21 of the
sequences). The second table is the 167 turns that got no answer; its "no criterion applies" line says that, it is not a verdict. What the
answered turns show: in every two- and three-request turn (22 of 22) the model declared exactly one read, so the second was never asked for and
the reply covered 0 of 15 two-request cases [0-20%]; the simple controls were answered correctly (4 of 4). That matches Groq's documentation,
which lists this model without parallel tool use. With so few answered turns the intervals are wide and this is not a rate for the model: it
is evidence that the limit is real. A complete run needs a key without that rate limit.

---

## groq/openai/gpt-oss-120b (cap 2, run ['double-a-groq'], prompt 3.2.1)

| case | covered | declared both/all | exact composition |
|---|---|---|---|
| balance_transfers.es | 0/3 [0-56%] | 0/3 [0-56%] | 3/3 [44-100%] |
| balance_transfers.pt | 0/1 [0-79%] | 0/1 [0-79%] | 1/1 [21-100%] |
| pending_payments_transfers.es | 0/2 [0-66%] | 0/2 [0-66%] | 2/2 [34-100%] |
| pending_payments_transfers.pt | 0/1 [0-79%] | 0/1 [0-79%] | 1/1 [21-100%] |
| reversed_order.es | 0/2 [0-66%] | 0/2 [0-66%] | 2/2 [34-100%] |
| reversed_order.pt | 0/2 [0-66%] | 0/2 [0-66%] | 2/2 [34-100%] |
| simple_control.es | 2/2 [34-100%] | 2/2 [34-100%] | 2/2 [34-100%] |
| simple_control.pt | 2/2 [34-100%] | 2/2 [34-100%] | 2/2 [34-100%] |
| three_same_tool.es | 0/1 [0-79%] | 0/1 [0-79%] | 1/1 [21-100%] |
| three_same_tool.pt | 0/3 [0-56%] | 0/3 [0-56%] | 3/3 [44-100%] |
| three_things.es | 0/1 [0-79%] | 0/1 [0-79%] | 1/1 [21-100%] |
| three_things.pt | 0/2 [0-66%] | 0/2 [0-66%] | 2/2 [34-100%] |
| trace_and_balance.es | 0/6 [0-39%] | 0/6 [0-39%] | 0/0 [0-0%] |
| with_product.es | 0/1 [0-79%] | 0/1 [0-79%] | 1/1 [21-100%] |
| with_product.pt | 0/3 [0-56%] | 0/3 [0-56%] | 3/3 [44-100%] |

| criterion | | detail |
|---|---|---|
| 1. 0 unsafe, 0 records sent to the model, 0 traces opened | MET | 0 turns |
| 2. two-request cases: >=76/80 cover both, every case >=9/10, real phrases and their PT equivalents 10/10 | NOT MET | 0/15 [0-20%] |
| 3. simple controls 10/10 per language | MET | 4/4 [51-100%] |
| 5. p95 total <= 5 s | MET | p50 717.2 ms, p95 1525.2 ms |
| 5. mean known cost per turn | MET | 0.00027558396226415094 USD over 53 turns; 0 with no known price: cost criterion pending |
| 5. one decision per normal turn, <=2 attempts | MET | max attempts 1 |
| cap: triple declared >=38/40, each case >=9/10 | NOT MET | 0/7 [0-35%] |
| cap: triple answered (cap-3 run) >=38/40, each case >=9/10 | NOT MET | 0/7 [0-35%] |
| 4. recovery when something was left out | NOT MET | 0/8 real opportunities |
| model down / guard-derived turns | | 0 / 0 |

## groq:openai/gpt-oss-120b (cap 2, run ['double-a-groq'], prompt 3.2.1)

| case | covered | declared both/all | exact composition |
|---|---|---|---|
| balance_transfers.es | 0/7 [0-35%] | 0/7 [0-35%] | 0/0 [0-0%] |
| balance_transfers.pt | 0/9 [0-30%] | 0/9 [0-30%] | 0/0 [0-0%] |
| pending_payments_transfers.es | 0/8 [0-32%] | 0/8 [0-32%] | 0/0 [0-0%] |
| pending_payments_transfers.pt | 0/9 [0-30%] | 0/9 [0-30%] | 0/0 [0-0%] |
| reversed_order.es | 0/8 [0-32%] | 0/8 [0-32%] | 0/0 [0-0%] |
| reversed_order.pt | 0/8 [0-32%] | 0/8 [0-32%] | 0/0 [0-0%] |
| simple_control.es | 0/8 [0-32%] | 0/8 [0-32%] | 0/0 [0-0%] |
| simple_control.pt | 0/8 [0-32%] | 0/8 [0-32%] | 0/0 [0-0%] |
| three_same_tool.es | 0/9 [0-30%] | 0/9 [0-30%] | 0/0 [0-0%] |
| three_same_tool.pt | 0/7 [0-35%] | 0/7 [0-35%] | 0/0 [0-0%] |
| three_things.es | 0/9 [0-30%] | 0/9 [0-30%] | 0/0 [0-0%] |
| three_things.pt | 0/8 [0-32%] | 0/8 [0-32%] | 0/0 [0-0%] |
| trace_and_balance.es | 0/4 [0-49%] | 0/4 [0-49%] | 0/0 [0-0%] |
| trace_and_balance.pt | 0/10 [0-28%] | 0/10 [0-28%] | 0/0 [0-0%] |
| with_product.es | 0/9 [0-30%] | 0/9 [0-30%] | 0/0 [0-0%] |
| with_product.pt | 0/7 [0-35%] | 0/7 [0-35%] | 0/0 [0-0%] |
no model answered (down, or without its key): no criterion applies
