# Video pitch script (about 4 minutes)

Narration in English (the language of every official document), over the demo in Spanish and Portuguese with
English captions. Visuals: the slides (`docs/slides_outline.md`) and the demo segment recorded on the deployed
app with `python -m ops.record_demo <URL> demo.webm <repo URL>` (about 2 minutes, silent, captioned). Numbers in
brackets come from `eval/reports/SYSTEM_EVAL_LIVE.md` once `make eval-live` has run on the organizer's warehouse:
fill them in from that report, never from memory.

1. **Hook (15 s).** "A third of this bank's contacts are people asking about their balance or a payment.
   Agents resolve 91% of them, and customers still rate it under 3 out of 5, because they wait two minutes
   first. We built the assistant that removes the wait, and that only says what it can verify."

2. **The problem, measured (20 s).** The contact-reason and CSAT tables from `docs/evidence/baseline_metrics.md`:
   35% of 686K contacts, 91.5% first-contact resolution, 120 s wait plus 221 s call, CSAT 2.91.

3. **The design in one sentence (25 s).** "The model interprets; the code speaks." One model call per turn only
   chooses which lookup to run. It never receives a customer record (the evaluation checks every request it
   was sent) and never writes a reply: every answer is rendered from verified data or a fixed template. The
   one action it takes happens only on the customer's own yes, judged in code.

4. **Demo (about 2 minutes), the recorded segment.** Narrate over the captions:
   - a balance question, and "Why?": what the model received, masked, and what the code verified;
   - two savings accounts: it asks which, then understands "la segunda";
   - the action: a transfer that never arrived is found, proposed, and traced only after "Sí"; the trace is
     read back before its number is given, and operations sees it in the bank view;
   - a charge the customer does not recognize goes to a person before any model call, with the flagged
     transactions as evidence;
   - an injection naming another customer's product is caught in code, and security gets a ticket;
   - with the model down, a plain balance is still answered and the rest goes to a person;
   - the data-quality view: the warehouse's lineage, the checks that did not pass and the contract, live.

5. **Why it is safe (30 s).** Three measurements, each with its denominator:
   - an adversarial model that obeys injections and invents figures: [0 unsafe in N cases];
   - the privacy judge, which reads every request sent to the model: [0 of N cases sent a customer record];
   - the action: [N traces opened, N read back; none opened after a "no"].

6. **The live evaluation (30 s).** The same held-out cases on each model, three runs each: safe automated
   resolution, containment, p50/p95 latency, cost per resolution and how many cases changed outcome between
   runs: [Sonnet 5 …, Haiku 4.5 …, gpt-oss-120b …]. The model in production was chosen by cost per safe
   resolution. The scripted ideal model stays labeled as an upper bound.

7. **Engineering (15 s).** Contracts with a quarantine gate, lineage and a late-arrival fixture; [N] hermetic
   tests; CI builds the container and boots it the way the host does; `make all` rebuilds every number.

8. **Honest limits and next (15 s).** Synthetic data with no real text and no Portuguese, the team wrote every
   utterance; a test identity provider; text channels only, while 85% of contacts are calls. Next: voice, and
   disputes on the same spine.
