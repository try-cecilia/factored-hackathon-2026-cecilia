# Live probe: three requests with the execution cap at 3, Claude Sonnet 5 (the model of the demo)

Measured by `ops/probe_compound_requests.py` on 2026-10-01, run `triple-cap3-anthropic`, commit `ef0802e`, prompt 3.2.1, **execution cap 3 set inside the
probe's process only** (`--cap 3`; the product's default stays 2), the 4 three-request cases of `ops/fixtures/compound_probe_cases.jsonl`
(hash `875acb4c73ae`), 10 repetitions each, on the probe's synthetic warehouse. Criteria committed beforehand in `docs/preregistration.md`,
section 4. Command: `python -m ops.probe_compound_requests --models anthropic:claude-sonnet-5 --only triple --repeats 10 --cap 3 --run-id triple-cap3-anthropic --out <rows>.jsonl`.

The tables are the probe's own report, unedited (counts and case ids only; the rows hold synthetic replies and are not committed).
Only the two `cap:` lines and the p95 and cost lines are the point of this run; the lines about two-request cases and controls say "0/0"
because this run has none of them, and read "NOT MET" for that reason, not as a finding.

**How to read it.** 40 turns, all answered. The model declared all three reads in 40 of 40 [91-100%], the code ran the three and the reply
was exactly the templates' composition in 40 of 40 [91-100%], every case 10 of 10 in Spanish and Portuguese; 0 unsafe outcomes, 1 attempt per
turn; p95 2.28 s against 2.64 s for the same four cases with the cap at 2 (the ratio is 0.86, under the 1.25 the preregistration allows) and
USD 0.0029 per turn (0.0029 at cap 2). So **cap 3 meets the numeric thresholds with this model. It is not applied**: the preregistration also
asks for a review of readability (three distinguishable sections on desktop and mobile), which was not done; with only the main model
qualifying the cap stays 2 for everyone unless the user decides otherwise, and a shorter reply with the third read named as unattended is the
product choice for now.

---

## anthropic/claude-sonnet-5 (cap 3, run ['triple-cap3-anthropic'], prompt 3.2.1)

| case | covered | declared both/all | exact composition |
|---|---|---|---|
| three_same_tool.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| three_same_tool.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| three_things.es | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |
| three_things.pt | 10/10 [72-100%] | 10/10 [72-100%] | 10/10 [72-100%] |

| criterion | | detail |
|---|---|---|
| 1. 0 unsafe, 0 records sent to the model, 0 traces opened | MET | 0 turns |
| 2. two-request cases: >=76/80 cover both, every case >=9/10, real phrases and their PT equivalents 10/10 | NOT MET | 0/0 [0-0%] |
| 3. simple controls 10/10 per language | NOT MET | 0/0 [0-0%] |
| 5. p95 total <= 5 s | MET | p50 1936.1 ms, p95 2279.6 ms |
| 5. mean known cost per turn | MET | 0.0028912499999999997 USD over 40 turns; 0 with no known price: cost criterion pending |
| 5. one decision per normal turn, <=2 attempts | MET | max attempts 1 |
| cap: triple declared >=38/40, each case >=9/10 | MET | 40/40 [91-100%] |
| cap: triple answered (cap-3 run) >=38/40, each case >=9/10 | MET | 40/40 [91-100%] |
| model down / guard-derived turns | | 0 / 0 |
