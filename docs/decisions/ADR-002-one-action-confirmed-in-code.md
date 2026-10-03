# ADR-002: one verified action, confirmed in code

- **Status:** accepted, 2026-09-27
- **Context:** the workflow was read-only. The brief lists Act and Verify among
  the minimum capabilities and asks to "report only actions whose outcomes the
  system has verified". Money movement and credit decisions are out of scope
  by the brief.

## Decision

The system takes exactly one kind of action: it opens a **trace request** for
a movement of the customer's that is still pending (a transfer, payment or
deposit that did not arrive). The data grounds it: 58,234 movements in the
organizer's dataset are Pending (1.99%).

1. **The model proposes nothing it can execute.** It only picks the
   `request_trace` tool. The tool finds the customer's pending movements that
   match what they said, with ownership checked in SQL, and opens nothing.
2. **The code asks, with the facts.** With one match, the reply shows the
   movement (kind, amount, date, product) and asks for a plain yes or no. The
   proposal is stored server side, never sent to the model, and lives for one
   turn.
3. **The customer's yes is judged in code.** `router.confirmation` accepts only
   a message that *is* a yes or a no ("sí", "dale", "confirmo", "sim", "no",
   "não, obrigado"). Anything else, such as "no, me clonaron la tarjeta", lets
   the proposal lapse and goes through the usual pre-LLM checks. The model is
   never asked whether the customer agreed.
4. **Still eligible at the yes.** The proposal is one turn old, so before opening,
   the code asks the same tool again: if the movement is no longer pending, nothing
   is opened and a person takes over.
5. **Announce only what reads back.** After the yes, the trace is opened in the
   tracing service and read back; only a record that reads back, for this
   customer and this movement, is announced with its number and deadline. If
   it does not read back, the customer is not told it exists and a person
   opens it (a ticket to payments operations).
6. **Idempotent.** The trace id derives from the customer and the movement
   (64 bits of SHA-256): asking again returns the same trace instead of a
   second one. Lookups and the read-back check the customer and the movement
   field by field, so even a colliding id can never make one customer hear
   another customer's trace number.
7. **Several matches are listed**, and a plain answer with the number ("la
   segunda", "2") is resolved in code from the list kept server side, like
   the yes; the model never saw the list. The customer can also give the
   amount or the date, which the model passes to the tool.

## Consequences

- The action works even with the model down: the yes needs no model.
- The evaluation can judge the action against the service's own records:
  announcing a trace the service does not have, opening one after a no, or
  opening any other is an unsafe outcome.
- The tracing service is a sandbox mock (JSONL next to the human queue), and
  the 2-business-day deadline is a synthetic policy. A bank would plug in its
  payments-operations API behind the same `open`/`get` calls.
  *Superseded 2026-10-03 (country payment rules):* the deadline now comes only
  from a reviewed country rule that the trace snapshots when it is opened; with
  none (the catalog ships empty) the trace is opened, read back and announced
  without a deadline. Records written before keep the synthetic 2, and no
  reader shows it (LIMITATIONS.md, "Payment conditions").
- Only a plain yes counts. A customer who answers "sí, ábrelo y además dime mi
  saldo" gets the proposal dropped and has to ask again: stricter than a
  person would be, by design.
- The pre-LLM intent classifier predates the action and reads 1 of 12
  team-written trace requests as a possible dispute: that customer goes to a
  person, which is safe but not self-served (LIMITATIONS.md).
