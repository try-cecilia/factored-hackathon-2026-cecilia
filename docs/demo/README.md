# Submission deliverables: slides and video

## Slides (6)

Built as a Slides deck: https://claude.ai/artifact/L223gAp5njs6vAxMdDopes
(private until shared from its Share menu; exports to PPTX/PDF). Every
figure comes from `eval/reports/` and `docs/evidence/`. The outline and
speaker notes are in `docs/slides_outline.md`.

1. Cover: "Un asistente que solo dice lo que puede verificar", with three headline numbers.
2. The problem, measured: 35% of contacts, 91.5% FCR, 221 + 120 s, CSAT 2.91.
3. Architecture: the model proposes, the code decides, plus the adversarial stress test.
4. Results vs humans vs the keyword bot on 432 cases.
5. Data and evaluation rigor.
6. What it takes to make it real, and the labeled projection.

## Video

`demo_app.webm` (77 s, 1280×720, captioned in Spanish, no audio) is a
recording of the **real app** on the full warehouse:
- test-PIN login;
- a balance question in Spanish and in Portuguese;
- a fraud report escalated before the LLM, then the ticket as the human agent sees it (rule, evidence, open questions, no token);
- an out-of-scope request;
- a closing results card.

The build sandbox blocks the LLM provider, so the clip shows the **degraded
mode** (deterministic answers where safe). The first caption says so.

The submission asks for a pitch video with voice explaining the solution and
the architectural decisions. That needs a human recording:
1. Start the server with `GROQ_API_KEY` in a network that allows `api.groq.com`.
2. Re-record the walkthrough with `python -m ops.record_demo`, adding the
   multi-turn clarification and the injection attempt that need the live model.
3. Record the voice-over following `docs/video_pitch_script.md` (≈4 min),
   using this clip and the slides as the visuals.
