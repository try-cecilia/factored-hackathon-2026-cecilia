# Video pitch script (about 4 minutes)

Narration in English (the language of every official document), over the demo in Spanish and Portuguese with
English captions. Visuals: the slides (`docs/slides_outline.md`) and the demo segment recorded on the deployed
app with `python -m ops.record_demo <URL> demo.webm <repo URL>` (about 2 minutes, silent, captioned). The numbers
come from `eval/reports/SYSTEM_EVAL.md`, `SYSTEM_EVAL_ADVERSARIAL.md` and `SYSTEM_EVAL_LIVE.md` (2026-10-02); if a
report is regenerated, copy them again from it, never from memory.

1. **Hook (20 s).** "More than a third of this bank's contacts are filed as transactional: account and payment questions.
   Agents already resolve 91.5% of them on the first contact, yet customers rate the service under 3 out of 5, and
   every one of those calls starts with two minutes in a queue. We built the assistant that answers them in
   seconds, that only says what it can verify, that acts once and only on the customer's yes, and that hands over
   to a person, with the evidence, when it should not act." (Do not say the wait causes the score: the data's wait is
   120 s for every reason, so it cannot show that.)

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
   - an adversarial model that obeys injections and invents figures: 0 unsafe outcomes in 548 cases;
   - the privacy judge, which reads every request sent to the model: 0 of 548 cases sent a customer record,
     and 0 of the 138 of the live run, in every run of both models;
   - the action: 20 traces opened on 22 confirmations, each one read back from the tracing service before it is
     announced, none opened after a "no"; live, Sonnet 5 traced 4 of 6 and left the other 2 proposed.

6. **The live evaluation (30 s).** 138 held-out cases, three of every case type in each language, on each model,
   three runs each. In the first run, Claude Sonnet 5: 95.0% safe automated resolution, 68.1% containment, 1.9 s
   p50 and 4.2 s p95 per case, USD 0.0034 per safe resolution; Claude Haiku 4.5: 78.3%, 73.9%, 1.1 s and 4.2 s,
   USD 0.0079. Across the three runs, safe automated resolution stayed between 95.0 and 96.7% on Sonnet 5 and
   between 76.7 and 78.3% on Haiku 4.5; 0.7% and 2.2% of cases changed outcome. Sonnet 5 had 0 unsafe outcomes in
   every run; Haiku 4.5 had one, in one run: a reply outside the templates, which the judge flags as unsafe by
   itself. Sonnet 5, the model the demo runs, also has the lower cost per safe resolution of the two. Groq's
   gpt-oss-120b did not run (no key). The scripted ideal model stays labeled as an upper bound (99.2%).

7. **Engineering (15 s).** Contracts with a quarantine gate, lineage and a late-arrival fixture; every
   classifier selection and evaluation run tracked in MLflow, with its model, prompt hash and data hashes; 1,400
   hermetic tests; CI builds the container and boots it the way the host does; `make all` rebuilds every number.

8. **Honest limits and next (15 s).** Synthetic data with no real text and no Portuguese, the team wrote every
   utterance; a test identity provider; text channels only, while 85% of contacts are calls. Next: voice, and
   disputes on the same spine.
