# Submission deliverables: slides and video

## Slides (6: a cover and 5)

The v3 deck is a private claude.ai artifact (downloadable as PDF or PPTX), built on 2026-09-28 from
`docs/slides_outline.md` with the measured numbers. Still to fill before sending: the team name, the deployed
URL and the public repository's URL. The first deck (6 slides) described design v2 and is superseded.

## Video

The submission asks for a pitch video with voice that explains the solution and the architectural decisions.
- **Script:** `docs/video_pitch_script.md` (about 4 minutes, English narration).
- **Demo segment:** `python -m ops.record_demo <deployed URL> demo.webm <public repo URL>` records the jury demo
  (DEMO_MODE=1) through its guided scenarios and its data-quality view, about 2 minutes, 1280×720, silent, with
  English captions. It was checked against a local server with Claude Sonnet 5 on 2026-09-28 (109 s), and again
  after the data-quality view was added, in degraded mode (114 s; a live model adds its latency).
- **Edit:** the voice-over over the demo segment and the slides.

`demo_app.webm` in this folder is the first recording (design v2, degraded mode, no voice). It is kept here
for the record and left out of the public repository.

## Operator console (web)

`operador-kit-*.png` are screenshots of the `/operador/*` web console built on the UI kit, in Spanish and Portuguese, desktop
(1440×900) and mobile (390×844): login, queue, ticket in each state (unassigned, taken, version conflict 409, decided),
monitoring, traces, read-only session, empty result, filters, expired session, missing ticket and API down.
`paper-operator-queue.jpg` and `paper-operator-ticket-states.jpg` are the approved Paper artboards ("Operator · Queue" and
"Operator · Ticket states") they were checked against. They come from a local run on synthetic data:
`python -m ops.seed_operator_demo`, then the API and `pnpm --dir web dev`, driven with Playwright. The setup and the key
handling are in `docs/integracion.md` (frontier 2).
