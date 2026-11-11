"""Drive the real Fine Print app on camera, one clip per narration section.

Each section gets its own browser context, so Playwright writes one .webm per
beat. A demo beat records the whole analysis (including the real 40-70s wait)
and then tours the finished result; assemble.py keeps only the tail of that
clip, so the visible video is the result and never the spinner.

  .venv/bin/python video/record.py            # all sections
  .venv/bin/python video/record.py s4_doctored
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

from playwright.async_api import Page, async_playwright

ROOT = Path(__file__).resolve().parent
APP = "http://127.0.0.1:8077/"
VIDEO_DIR = Path("/tmp/fpvid")
STAMPS = ("SAFE TO PAY", "DO NOT PAY", "CHECK IT YOURSELF", "NOTHING TO PAY", "STOPPED")

SAMPLE_TEXT = {
    "bill_clean": "exactly what it claims",
    "bill_doctored": "does not add up",
    "notice_injection": "final notice with instructions",
    "letter_insurance": "hospital letter",
}

SMOOTH = """
async (dy) => {
  const start = window.scrollY, t0 = performance.now(), ms = 650;
  await new Promise(res => {
    function step(t) {
      const k = Math.min(1, (t - t0) / ms);
      const e = k < 0.5 ? 2*k*k : -1 + (4 - 2*k) * k;
      window.scrollTo(0, start + dy * e);
      k < 1 ? requestAnimationFrame(step) : res();
    }
    requestAnimationFrame(step);
  });
}
"""


async def body_text(page: Page) -> str:
    try:
        return (await page.inner_text("body")).upper()
    except Exception:
        return ""


async def wait_stamp(page: Page, timeout_s: float = 150) -> str | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        txt = await body_text(page)
        for s in STAMPS:
            if s in txt:
                return s
        await page.wait_for_timeout(700)
    return None


async def smooth(page: Page, dy: int) -> None:
    await page.evaluate(SMOOTH, dy)
    await page.wait_for_timeout(120)


async def fill(page: Page, deadline: float) -> None:
    """Keep the frame alive with slow scrolling until an absolute deadline."""
    down = True
    while time.monotonic() < deadline - 0.9:
        await smooth(page, 80 if down else -80)
        down = not down
        await page.wait_for_timeout(320)


async def tour(page: Page, deadline: float, steps: list[tuple[int, float]]) -> None:
    """Walk down the result, pausing on each step, then idle to the deadline."""
    for dy, pause in steps:
        if time.monotonic() > deadline - 1.5:
            break
        await smooth(page, dy)
        await page.wait_for_timeout(int(pause * 1000))
    if time.monotonic() < deadline:
        await fill(page, deadline)


async def landing(page: Page, audio: float) -> None:
    deadline = time.monotonic() + audio + 0.5
    await page.goto(APP, wait_until="networkidle")
    await page.wait_for_timeout(1200)
    await smooth(page, 60)
    await page.wait_for_timeout(900)
    await smooth(page, -60)
    await fill(page, deadline)


async def beat(page: Page, sample: str, audio: float, steps: list[tuple[int, float]]) -> None:
    """Wait out the real analysis, then tour the result for exactly the line."""
    await page.goto(APP, wait_until="networkidle")
    await page.wait_for_timeout(800)
    started = time.monotonic()
    await page.locator("button", has_text=SAMPLE_TEXT[sample]).first.click()
    stamp = await wait_stamp(page, 170)
    print(f"    stamp={stamp} after {time.monotonic() - started:5.1f}s")
    # hold on the verdict stamp long enough for the narration to land it
    await page.wait_for_timeout(2600)
    await tour(page, time.monotonic() + audio - 2.6, steps)


async def s1_problem(page: Page, audio: float) -> None:
    await landing(page, audio)


async def s2_solution(page: Page, audio: float) -> None:
    await beat(page, "bill_clean", audio, [(200, 1.4), (240, 1.4), (240, 1.4)])


async def s3_clean(page: Page, audio: float) -> None:
    await beat(page, "bill_clean", audio, [(170, 1.2), (250, 1.1), (250, 1.1), (250, 1.1)])


async def s4_doctored(page: Page, audio: float) -> None:
    await beat(page, "bill_doctored", audio, [(190, 1.4), (260, 1.3), (250, 1.2)])


async def s5_injection(page: Page, audio: float) -> None:
    await beat(page, "notice_injection", audio, [(150, 1.6), (180, 1.6)])


async def s6_letter(page: Page, audio: float) -> None:
    await beat(page, "letter_insurance", audio, [(170, 1.3), (240, 1.3)])


async def s7_close(page: Page, audio: float) -> None:
    await page.goto(APP, wait_until="networkidle")
    await page.wait_for_timeout(1500)


SECTIONS = {
    "s1_problem": s1_problem,
    "s2_solution": s2_solution,
    "s3_clean": s3_clean,
    "s4_doctored": s4_doctored,
    "s5_injection": s5_injection,
    "s6_letter": s6_letter,
    "s7_close": s7_close,
}


async def main(names: list[str]) -> None:
    beats = {b["name"]: b["seconds"] for b in json.loads((ROOT / "narration.json").read_text())}
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    for n in names:
        for p in VIDEO_DIR.glob(f"{n}*.webm"):
            p.unlink()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome", args=["--hide-scrollbars"])
        for name in names:
            audio = beats[name]
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                device_scale_factor=2,
                record_video_dir=str(VIDEO_DIR),
                record_video_size={"width": 1280, "height": 720},
            )
            page = await ctx.new_page()
            before = set(VIDEO_DIR.glob("*.webm"))
            t0 = time.monotonic()
            try:
                await SECTIONS[name](page, audio)
            except Exception as exc:
                print(f"  ! {name}: {type(exc).__name__}: {exc}")
            await ctx.close()
            new = sorted(set(VIDEO_DIR.glob("*.webm")) - before)
            label = "MISSING"
            if new:
                dest = VIDEO_DIR / f"{name}.webm"
                shutil.move(str(new[0]), dest)
                label = f"{dest.name} ({dest.stat().st_size // 1024}K)"
            print(f"{name:14s} audio {audio:5.1f}s  shot {time.monotonic() - t0:5.1f}s  {label}")
        await browser.close()


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(SECTIONS)
    asyncio.run(main(wanted))
