"""Records the demo segment of the pitch video: the jury demo, driven through its guided scenarios, with captions.

    python -m ops.record_demo BASE_URL OUT.webm [REPO_URL]

BASE_URL is the deployed app (or a local `uvicorn api.main:app` with DEMO_MODE=1 and a model key). The result is
a silent 1280x720 video, about two minutes, with English captions over the Spanish and Portuguese chat: the voice-over
and the slides are added when the pitch is edited (docs/video_pitch_script.md). Needs Playwright
(`pip install playwright`); PW_CHANNEL picks an installed browser ("msedge", "chrome"), otherwise Playwright's own
Chromium (`playwright install chromium`).
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

CARD = """<html><body style="margin:0;height:100vh;display:flex;flex-direction:column;justify-content:center;
padding:0 96px;background:#0e2f2b;color:#f2f4f1;font-family:system-ui,sans-serif">{body}</body></html>"""
CAPTION_JS = """t => {
  let c = document.getElementById('__cap');
  if (!c) { c = document.createElement('div'); c.id = '__cap';
    c.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);max-width:1120px;background:rgba(14,47,43,.95);'
      + 'color:#f2f4f1;font:600 21px/1.4 system-ui,sans-serif;padding:12px 22px;border-radius:12px;z-index:9999;text-align:center';
    document.body.appendChild(c); }
  c.textContent = t; }"""


def caption(page, text: str, ms: int = 4000) -> None:
    page.evaluate(CAPTION_JS, text)
    page.wait_for_timeout(ms)


def run_scenario(page, title: str, first: str, why: bool = False, then: str | None = None, after: str | None = None) -> None:
    """Run one guided scenario by its exact title; caption before the first step, optionally after each step."""
    card = page.locator("article.scard").filter(has=page.locator(".stitle", has_text=re.compile("^" + re.escape(title) + "$")))
    card.get_by_role("button").click()
    page.wait_for_function("t => document.querySelector('#steps .steps-head strong')?.textContent === t", arg=title)
    caption(page, first, 3500)
    steps = page.locator("#steps li").count()
    for i in range(steps):
        before = page.locator(".msg.bot").count()
        page.locator("#steps li button").first.click()
        page.wait_for_function(f"document.querySelectorAll('.msg.bot').length > {before}", timeout=90000)
        page.wait_for_timeout(1200)
        if i == 0 and then and steps > 1:
            caption(page, then, 4500)
    if why:
        page.locator(".msg.bot .linkbtn").last.click()
        page.wait_for_timeout(800)
    if after:
        caption(page, after, 6000)


def main(base: str, out: Path, repo: str) -> None:
    tmp = tempfile.mkdtemp(prefix="demo_video_")
    with sync_playwright() as p:
        channel = os.environ.get("PW_CHANNEL")
        browser = p.chromium.launch(channel=channel) if channel else p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=tmp,
                                  record_video_size={"width": 1280, "height": 720}, color_scheme="light")
        page = ctx.new_page()
        page.set_content(CARD.format(body="""
          <p style="font-size:19px;letter-spacing:3px;text-transform:uppercase;color:#7fd1c4;font-weight:600">Factored AI &amp; Data Hackathon 2026 · team Marvaq</p>
          <h1 style="font-size:52px;line-height:1.1;margin:12px 0">An account &amp; payments assistant<br>that only says what it can verify</h1>
          <p style="font-size:24px;color:#c6d3cf;line-height:1.45">The deployed app, with a live language model. Synthetic data only.</p>"""))
        page.wait_for_timeout(5000)

        page.goto(base)
        page.wait_for_selector("article.scard")
        caption(page, "Guided scenarios on the left, the customer's chat in the middle, what the bank's teams receive on the right.", 5000)
        run_scenario(page, "Balance question", "A balance question, in Spanish.", why=True,
                     after="The model only chose the lookup. It received the customer's words, masked, and never the balances shown here.")
        run_scenario(page, "Which account? (two turns)", "Two savings accounts match.",
                     then="It asks which one instead of guessing…",
                     after="…and understands “la segunda” from the conversation.")
        run_scenario(page, "Trace a pending transfer (two turns)", "The one action it takes: tracing a transfer that never arrived.",
                     then="It finds the pending transfer and asks for a plain yes. Nothing is opened yet.", why=True,
                     after="The yes is judged in code, not by the model. The trace is opened, read back, and only then announced. Operations sees it on the right.")
        run_scenario(page, "Unrecognized charge", "A charge the customer does not recognize.",
                     after="Fraud goes to a person before any model call, with the flagged transactions, open questions and the next step. No transcript.")
        run_scenario(page, "Prompt injection naming another customer's product", "An injection naming another customer's product.", why=True,
                     after="Caught in code before the model: nothing about that product is revealed, and security gets a ticket.")
        run_scenario(page, "The language model goes down", "Now the language model goes down.",
                     then="A plain balance is still answered from verified data…",
                     after="…and anything that needs understanding goes to a person.")
        page.set_content(CARD.format(body=f"""
          <h2 style="font-size:42px;margin:0 0 22px">Every reply is verified data or a fixed template.</h2>
          <p style="font-size:25px;color:#c6d3cf;line-height:1.5">No customer record ever reaches the model.<br>
          Its one action happens only on the customer's own yes, and is announced only after it reads back.</p>
          <p style="font-size:21px;color:#7fd1c4;margin-top:26px">Code, evaluation and limits: {repo}</p>"""))
        page.wait_for_timeout(6000)
        ctx.close()
        browser.close()
    videos = list(Path(tmp).glob("*.webm"))
    assert len(videos) == 1, videos
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(videos[0], out)
    print(f"saved {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/"), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "github.com/marvaq-ai")
