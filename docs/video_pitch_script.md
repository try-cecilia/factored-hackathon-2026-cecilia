# Video pitch script draft (short, mandatory per submission requirements)

Target length: 3–4 minutes. Beats below, not a verbatim script — adapt to
whoever's presenting.

1. **Hook (15s).** "35% of every call this bank gets is someone asking about
   their balance or a payment. That's not a hard AI problem — it's a
   volume problem. We built the system that should own it."

2. **The data case (30s).** Show the contact-reason table. Explain briefly
   why we picked this workflow over disputes/cards/credit — data-backed,
   not a guess.

3. **Live demo (90s).**
   - Normal case: ask for balance in Spanish → grounded answer, cite the
     tool call in the logs.
   - Ambiguous/out-of-scope: ask to block a card → system correctly abstains
     and explains it's out of scope.
   - Security case: attempt a prompt injection asking for another
     customer's balance → blocked, logged as an unauthorized-access
     attempt, escalated — show the ticket in `/admin/human_queue`.
   - Portuguese: same balance question in Portuguese → same correctness.

4. **Why it's safe (30s).** One sentence on the architecture: the model
   proposes, the code disposes — ownership and escalation are enforced
   outside the prompt, which is why the injection attempt above didn't work.

5. **Honesty about gaps (20s).** What's not done yet (live-LLM validation,
   real identity provider, monitoring) and why — this is a 10-day
   prototype, not a claim of production-readiness.

6. **Close (15s).** What this is worth automating first, and what it would
   take to extend the same spine to the other three candidate workflows.
