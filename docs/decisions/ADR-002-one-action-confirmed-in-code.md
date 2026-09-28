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
4. **Announce only what reads back.** After the yes, the trace is opened in the
   tracing service and read back; only a record that reads back, for this
   customer and this movement, is announced with its number and deadline. If
   it does not read back, the customer is not told it exists and a person
   opens it (a ticket to payments operations).
5. **Idempotent.** The trace id derives from the customer and the movement:
   asking again returns the same trace instead of a second one.

## Consequences

- The action works even with the model down: the yes needs no model.
- The evaluation can judge the action against the service's own records:
  announcing a trace the service does not have, opening one after a no, or
  opening any other is an unsafe outcome.
- The tracing service is a sandbox mock (JSONL next to the human queue), and
  the 2-business-day deadline is a synthetic policy. A bank would plug in its
  payments-operations API behind the same `open`/`get` calls.
- Only a plain yes counts. A customer who answers "sí, ábrelo y además dime mi
  saldo" gets the proposal dropped and has to ask again: stricter than a
  person would be, by design.
- The pre-LLM intent classifier predates the action and reads 1 of 12
  team-written trace requests as a possible dispute: that customer goes to a
  person, which is safe but not self-served (LIMITATIONS.md).
