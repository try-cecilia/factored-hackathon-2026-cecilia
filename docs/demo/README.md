# Submission deliverables: slides and video

## Slides (5)

Outline and bracketed numbers to fill from the live evaluation: `docs/slides_outline.md`. The first deck
(a private claude.ai artifact, 6 slides) described design v2 and is superseded.

## Video

The submission asks for a pitch video with voice that explains the solution and the architectural decisions.
- **Script:** `docs/video_pitch_script.md` (about 4 minutes, English narration).
- **Demo segment:** `python -m ops.record_demo <deployed URL> demo.webm <public repo URL>` records the jury demo
  (DEMO_MODE=1) through its guided scenarios, about 110 s, 1280×720, silent, with English captions. It was
  checked against a local server with Claude Sonnet 5 on 2026-09-28.
- **Edit:** the voice-over over the demo segment and the slides.

`demo_app.webm` in this folder is the first recording (design v2, degraded mode, no voice). It is kept here
for the record and left out of the public repository.
