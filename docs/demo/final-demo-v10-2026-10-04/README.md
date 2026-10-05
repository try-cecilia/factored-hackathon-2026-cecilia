# Cecilia narrated pitch · expanded results

2:43.2, 1080p at 30 fps. English ElevenLabs Sarah narration over the deployed Spanish and Portuguese app.

V10 removes the production-readiness checklist and its narration. The results now explain the 26.9 percentage-point improvement over the keyword baseline, complete operator context in all 171 handoffs, and end-to-end evaluation case times of 1.43 seconds at the median and 2.99 seconds at the 95th percentile. These numbers come from the Sonnet 5 first run in the October 4 live-model evaluation. The resolution comparison uses the same 238 in-scope cases. Timing covers the synthetic evaluation cases, not deployed-app latency.

The added results lead into the seven selected deployed scenarios and the invitation to try the customer app and bank console. New Sarah recordings cover the added statistics and the shorter closing. The full voiceover is mastered as one continuous track beneath the visual transitions. The gentle 0.6-second scene dissolves, 0.4-second app-view dissolves, native Chrome recordings, Cecilia fonts and palette remain. The closing gets a two-second tail so the link and QR stay readable.

- [Final video](cecilia-3min-en.mp4), 163.2 seconds. The historical filename is retained.
- [Separate narration](cecilia-3min-en.m4a) and [English captions](cecilia-3min-en.srt).
- [Editable Remotion project](cecilia-remotion-project.zip).
- [Recorded script](script.json), [timeline](timeline.json), [caption timing](captions.json).
- [Validation](validation.json), [provenance](provenance.json), [deployment check](deployment-check.json), [artifact hashes](artifact-manifest.json).

Sources: [live-model evaluation](../../../eval/reports/SYSTEM_EVAL_LIVE.md) and [keyword baseline](../../../eval/reports/SYSTEM_EVAL.md). Exact measurements and scope are also recorded in the provenance.

Working project: `~/Development/cecilia-video-remotion`. Extract the archive, run `npm ci`, then `npm run dev -- --port=3010`. Open `http://localhost:3010/Cecilia3Minutes`. `npm run render` exports using bundled assets without an ElevenLabs call.

The app recordings and deployment verification are unchanged from V8, captured on 4 October 2026. Customer data is synthetic. Source edits trim waits and hold frames; they do not measure service latency. The outage remains explicitly simulated. The evaluation's denominator and missed escalation remain in the narration.

The [six-slide PDF](cecilia-presentation.pdf), [editable HTML](cecilia-presentation.html) and [slide sources](slide-sources.json) are included here. Only this final delivery is retained.

Public repository: https://github.com/try-cecilia/factored-hackathon-2026-cecilia. The approved media retain the earlier repository placeholder. The video and presentation are unchanged from the approved exports.
