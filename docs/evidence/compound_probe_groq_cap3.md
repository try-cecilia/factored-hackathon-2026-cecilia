# Live probe: three requests with the execution cap at 3, GPT-OSS 120B on Groq (the fallback)

Measured by `ops/probe_compound_requests.py` on 2026-10-01, run `triple-cap3-groq`, commit `ef0802e`, prompt 3.2.1, **execution cap 3 set inside the
probe's process only** (`--cap 3`; the product's default stays 2), the 4 three-request cases of `ops/fixtures/compound_probe_cases.jsonl`
(hash `875acb4c73ae`), 10 repetitions each, on the probe's synthetic warehouse. Criteria committed beforehand in `docs/preregistration.md`,
section 4. Command: `python -m ops.probe_compound_requests --models groq:openai/gpt-oss-120b --only triple --repeats 10 --cap 3 --run-id triple-cap3-groq --out <rows>.jsonl`.

The tables are the probe's own report, unedited (counts and case ids only; the rows hold synthetic replies and are not committed).
Only the two `cap:` lines and the p95 and cost lines are the point of this run; the lines about two-request cases and controls say "0/0"
because this run has none of them, and read "NOT MET" for that reason, not as a finding.

**How to read it. These figures are partial.** Of the 40 planned turns, 16 were answered and 24 were refused by the provider's rate limit
(recorded as the model being down; the second table is those 24 and its "no criterion applies" line is not a verdict). In the 16 answered
turns the model declared exactly one read each time (0 of 16 [0-19%]), so the cap changed nothing: the limit of the fallback is in what the
model declares (Groq's documentation lists it without parallel tool use), not in how many the code runs.

---

## groq/openai/gpt-oss-120b (cap 3, run ['triple-cap3-groq'], prompt 3.2.1)

| case | covered | declared both/all | exact composition |
|---|---|---|---|
| three_same_tool.es | 0/10 [0-28%] | 0/10 [0-28%] | 10/10 [72-100%] |
| three_same_tool.pt | 0/2 [0-66%] | 0/2 [0-66%] | 2/2 [34-100%] |
| three_things.es | 0/4 [0-49%] | 0/4 [0-49%] | 4/4 [51-100%] |

| criterion | | detail |
|---|---|---|
| 1. 0 unsafe, 0 records sent to the model, 0 traces opened | MET | 0 turns |
| 2. two-request cases: >=76/80 cover both, every case >=9/10, real phrases and their PT equivalents 10/10 | NOT MET | 0/0 [0-0%] |
| 3. simple controls 10/10 per language | NOT MET | 0/0 [0-0%] |
| 5. p95 total <= 5 s | MET | p50 642.2 ms, p95 851.7 ms |
| 5. mean known cost per turn | MET | 0.00023754375 USD over 16 turns; 0 with no known price: cost criterion pending |
| 5. one decision per normal turn, <=2 attempts | MET | max attempts 1 |
| cap: triple declared >=38/40, each case >=9/10 | NOT MET | 0/16 [0-19%] |
| cap: triple answered (cap-3 run) >=38/40, each case >=9/10 | NOT MET | 0/16 [0-19%] |
| model down / guard-derived turns | | 0 / 0 |

## groq:openai/gpt-oss-120b (cap 3, run ['triple-cap3-groq'], prompt 3.2.1)

| case | covered | declared both/all | exact composition |
|---|---|---|---|
| three_same_tool.pt | 0/8 [0-32%] | 0/8 [0-32%] | 0/0 [0-0%] |
| three_things.es | 0/6 [0-39%] | 0/6 [0-39%] | 0/0 [0-0%] |
| three_things.pt | 0/10 [0-28%] | 0/10 [0-28%] | 0/0 [0-0%] |
no model answered (down, or without its key): no criterion applies
