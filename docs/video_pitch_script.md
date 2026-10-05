# Final video pitch

[Watch the 2:43.2 video](demo/final-demo-v10-2026-10-04/cecilia-3min-en.mp4). English ElevenLabs Sarah narration over the deployed Spanish and Portuguese app. The [editable Remotion project](demo/final-demo-v10-2026-10-04/cecilia-remotion-project.zip) includes the footage, fonts, narration, animation and rendering scripts.

The opening introduces Cecilia and its audience. Verified lookups lead to confirmed actions, human handoff, safety checks and measured results. The closing invites viewers to try the app. The production checklist is removed.

Statistics come from [baseline metrics](evidence/baseline_metrics.md) and the [live-model evaluation](../eval/reports/SYSTEM_EVAL_LIVE.md), Sonnet 5 run 1. The keyword comparison uses 238 in-scope cases. Latency is measured over synthetic evaluation cases.

## 0:00.0 · Cecilia

Cecilia answers account and payment questions for Spanish- and Portuguese-speaking bank customers, straight from verified bank data. Customers check a balance or chase a pending transfer in their own language, and see where each figure came from. Anything sensitive goes to a person.

## 0:16.8 · Why it matters

These everyday questions make up thirty-five percent of contacts in the bank's synthetic history. Customers queue for about two minutes, and satisfaction sits at two point nine out of five.

## 0:28.6 · How it stays honest

But nobody wants a model inventing a balance. In Cecilia, the model only chooses which lookup to run. Code checks ownership, reads the bank record and writes the reply. Customer records never enter the model request.

## 0:43.1 · Español · Balance

Here's how that looks in Spanish. Ask for a balance, and Cecilia returns the recorded balances with their source and date. Open Why to see the lookup the model chose and the checks the code ran.

## 0:54.9 · Português · Card payments

Portuguese gets the same treatment. Ask about late card payments, and the reply comes back in Portuguese, with the same source and date.

## 1:03.4 · Español · Pending transfer

Those were lookups. For a pending transfer, Cecilia finds the movement and asks before acting. Only after a clear yes does code open a trace and read it back from the service. The receipt says the trace is open, not that the money arrived. The bank console shows the same request.

## 1:21.4 · Human handoff

Some cases belong with a person. An unrecognized charge goes to the bank before any model call. In that same console, the operator gets verified evidence, open questions and a suggested next step, then takes the case. Cecilia doesn't block cards or decide disputes.

## 1:39.3 · Privacy + fallback

Nor will it hand over someone else's data. Ask for another customer's balance, and it opens a security case. When we deliberately simulate a model outage, verified balances keep working, and anything that needs the model goes to a person.

## 1:54.5 · Measured

A demo only shows the cases we picked. So we wrote five hundred forty-eight tests in Spanish and Portuguese. On the two hundred thirty-eight in scope, Cecilia on Sonnet five resolved ninety-seven point one percent safely, versus seventy point two for keywords. Three runs, zero unsafe outcomes, though the first run missed one required escalation.

## 2:17.7 · What the results mean

That's twenty-six point nine percentage points above keywords. All one hundred seventy-one handoffs included the required context for an operator. Speed mattered too: half of responses took under one point five seconds, and ninety-five percent took under three in that test run.

## 2:34.7 · Try Cecilia

The deployed demo passed the seven scenarios we selected. Try the customer app and the bank console today.

The [timeline](demo/final-demo-v10-2026-10-04/timeline.json), [captions](demo/final-demo-v10-2026-10-04/captions.json), [provenance](demo/final-demo-v10-2026-10-04/provenance.json) and [validation](demo/final-demo-v10-2026-10-04/validation.json) accompany the recording. To render, extract the Remotion archive and run `npm ci` then `npm run render`. Rendering uses bundled assets and makes no ElevenLabs call.
