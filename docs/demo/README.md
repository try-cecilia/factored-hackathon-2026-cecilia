# Final presentation and video pitch

The approved delivery is in [final-demo-v10-2026-10-04](final-demo-v10-2026-10-04/README.md).

- [Video pitch](final-demo-v10-2026-10-04/cecilia-3min-en.mp4), 2:43.2, 1080p at 30 fps. Continuous English Sarah narration, real deployed Spanish/Portuguese Chrome footage, animated results and gentle transitions.
- [Presentation PDF](final-demo-v10-2026-10-04/cecilia-presentation.pdf), six slides, and [editable HTML](final-demo-v10-2026-10-04/cecilia-presentation.html). Use **Edit text** and **Save HTML** to edit the deck.
- [Editable Remotion project](final-demo-v10-2026-10-04/cecilia-remotion-project.zip), [narration](final-demo-v10-2026-10-04/cecilia-3min-en.m4a) and [captions](final-demo-v10-2026-10-04/cecilia-3min-en.srt).
- [Exact script](final-demo-v10-2026-10-04/script.json), [deployment check](final-demo-v10-2026-10-04/deployment-check.json), [video validation](final-demo-v10-2026-10-04/validation.json) and [artifact hashes](final-demo-v10-2026-10-04/artifact-manifest.json).

Demo: https://cecil-ai.onrender.com. Public repository: https://github.com/try-cecilia/factored-hackathon-2026-cecilia.
The approved media retain the repository placeholder from recording time. Customer data is synthetic; the outage is deliberately simulated.
Only the final delivery is retained. Earlier pitch exports and the legacy silent recording have been removed.

## UI development evidence

The screenshots below document local UI development and are not final deployment/model evidence.

## Operator console (web)

`operador-kit-*.png` are screenshots of the `/operador/*` web console built on the UI kit, in Spanish and Portuguese, desktop
(1440×900) and mobile (390×844): login, queue, ticket in each state (unassigned, taken, version conflict 409, decided),
monitoring, traces, read-only session, empty result, filters, expired session, missing ticket and API down.
`paper-operator-queue.jpg` and `paper-operator-ticket-states.jpg` are the approved Paper artboards ("Operator · Queue" and
"Operator · Ticket states") they were checked against. They come from a local run on synthetic data:
`python -m ops.seed_operator_demo`, then the API and `pnpm --dir web dev`, driven with Playwright. The setup and the key
handling are in `docs/integracion.md` (frontier 2).

## Customer web app

`cliente-*.png` are the customer screens (home, sign in, chat, in Spanish and Portuguese, on desktop and phone), from a local run
with `make serve-all-fixture` (the API on the tests' warehouse, a keyword stand-in for the model, `DEMO_MODE=1`), driven with Playwright.
They show each kind of message the chat draws, the sidebar with its cases and its rail, the drawer on a phone, and the
delivery states; `cliente-*-sin-demo-*` are the same chat with `DEMO_MODE=0`, where the demo panel does not exist. The
design they follow is the Paper file "Cecil.ai" (`UI · Chat messages`, `UI · Sidebars`, `UI · Loaders`). `cliente-27-*` and `cliente-28-*` show the phone drawer and the demo panel with the focus already inside (Chromium, normal animations). `ui-kit-*.png` are the
component gallery (`/dev/ui`). The figures and ids on screen are the fixture's.
