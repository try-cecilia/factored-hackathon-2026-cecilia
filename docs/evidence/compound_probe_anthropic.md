# Live probe: two requests in one message, Claude Sonnet 5 (the model of the demo)

Measured by `ops/probe_compound_requests.py` on 2026-10-01, run `double-a-anthropic`, commit `ef0802e`, prompt 3.2.1, execution cap 2, cases
`ops/fixtures/compound_probe_cases.jsonl` and `compound_probe_sequences.jsonl` (hash `875acb4c73ae`), on the probe's synthetic
warehouse (the test fixtures plus one invented customer; no real customer data). Criteria and thresholds were committed before this run
(`docs/preregistration.md`, section 4). One model, one attempt per call, no provider fallback, one fresh session per case and repetition.
Command: `python -m ops.probe_compound_requests --models anthropic:claude-sonnet-5 --repeats 10 --pace-seconds 2 --budget-usd 4 --run-id double-a-anthropic --out <rows>.jsonl`.

The tables below are the probe's own report (`--report`), unedited. They hold counts, case ids and the probe's verdict per criterion; the
rows (`.jsonl`) also hold the synthetic replies and are not committed. Intervals are Wilson 95%; the 10 repetitions of a case are not
independent phrases, so they bound how this model behaves on these 16 phrasings, not on customers' phrasing in general. The two real
conversations are a known regression, not held-out phrases, and the Portuguese ones are ours.

**How to read it.** 220 turns, all answered by `anthropic/claude-sonnet-5`. Two of the `cap:` lines need a word: "triple declared" is
about this run and is met (the model declared all three reads in 40 of 40 turns; with the cap at 2 the code runs two and names the third in a
template, as designed). "Triple answered (cap-3 run)" is the criterion of a separate run with the cap at 3, so its 0/40 here is the expected
result of cap 2 and not a finding. The recovery criterion is PENDING: the model covered both reads on the first turn of every sequence, so
there was no real opportunity to recover from; recovery after a half answer is tested offline with a controlled history
(`tests/test_pedidos_compuestos.py`). Not measured here: the p95 against a baseline of the previous prompt (criterion 5, "at most 25% above")
and the behavior on the deployed demo (criterion 6).

---

## anthropic/claude-sonnet-5 (cap 2, run ['double-a-anthropic'], prompt 3.2.1)

| case | covered | declared both/all | exact composition |
|---|---|---|---|
| balance_transfers.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| balance_transfers.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| pending_payments_transfers.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| pending_payments_transfers.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| reversed_order.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| reversed_order.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| simple_control.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| simple_control.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| three_same_tool.es | 0/10 [0-28%] | 10/10 [72-100%] | 10/10 [72-100%] |
| three_same_tool.pt | 0/10 [0-28%] | 10/10 [72-100%] | 10/10 [72-100%] |
| three_things.es | 0/10 [0-28%] | 10/10 [72-100%] | 10/10 [72-100%] |
| three_things.pt | 0/10 [0-28%] | 10/10 [72-100%] | 10/10 [72-100%] |
| trace_and_balance.es | 10/10 [72-100%] | 10/10 [72-100%] | 0/0 [0-0%] |
| trace_and_balance.pt | 10/10 [72-100%] | 10/10 [72-100%] | 0/0 [0-0%] |
| with_product.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| with_product.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |

| criterion | | detail |
|---|---|---|
| 1. 0 unsafe, 0 records sent to the model, 0 traces opened | MET | 0 turns |
| 2. two-request cases: >=76/80 cover both, every case >=9/10, real phrases and their PT equivalents 10/10 | MET | 80/80 [95-100%] |
| 3. simple controls 10/10 per language | MET | 20/20 [84-100%] |
| 5. p95 total <= 5 s | MET | p50 1834.3 ms, p95 3036.1 ms |
| 5. mean known cost per turn | MET | 0.0025895272727272725 USD over 220 turns; 0 with no known price: cost criterion pending |
| 5. one decision per normal turn, <=2 attempts | MET | max attempts 1 |
| cap: triple declared >=38/40, each case >=9/10 | MET | 40/40 [91-100%] |
| cap: triple answered (cap-3 run) >=38/40, each case >=9/10 | NOT MET | 0/40 [0-9%] |
| 4. recovery when something was left out | PENDING | 0/0 real opportunities; none: no live rate is claimed |
| model down / guard-derived turns | | 0 / 0 |
