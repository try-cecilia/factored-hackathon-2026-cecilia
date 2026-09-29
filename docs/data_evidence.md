# Why account & payment inquiries

The full, regenerable numbers are in [`evidence/baseline_metrics.md`](evidence/baseline_metrics.md)
(`make analysis`). The argument, in four measurements:

1. **Largest demand.** "Transaccional" is 35.0% of 686,296 contacts. The next
   reason, Producto, is 22.0%. The median is 6,701 contacts a month, or 411
   agent-hours of handle time.
2. **Already simple.** It has the highest first-contact resolution (91.5%) and
   the shortest handle time (221 s vs 266–540 s for other reasons). The answers
   are facts the bank already holds (balances, movements, arrears, rates). That
   makes it the safest workflow to automate: read-only, no money movement, no
   credit judgment.
3. **Still a bad experience.** CSAT is 2.91/5 and NPS −70, and each of these
   contacts waits 120 s in the queue before a 3.7-minute call. The data does not
   say why the score is low: the wait is 120 s for every reason and segment (a
   constant of the synthetic data), so it cannot explain a difference between
   them. Automation removes the queue and the call either way.
4. **Reachable now on text channels.** 15.0% of these contacts come by
   chat/WhatsApp/app/email/web, about 1,005 a month. The remaining 85% are phone
   calls and need speech I/O (LIMITATIONS.md).

**Runner-up: transaction disputes.** The `complaints` table shows "Cargo no
reconocido" and "Cobro indebido" as the top subcategories (about 36% of 67K
complaints), with 20% SLA breaches. Disputes are lower volume, higher effort,
and legally sensitive. The escalation path built here (fraud evidence packs)
is the bridge to that workflow. Its data needs work first: each of the 44,570
complaints that names an affected product names a product of another customer,
and none links to the contact it came from (Matías Enrique's audit of the
dataset; this pipeline does not load complaints), so a disputes workflow could
trust neither link.
