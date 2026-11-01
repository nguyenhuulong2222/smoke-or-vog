"""Capture high-resolution stills of the live site for the demo video.

    PLAYWRIGHT_BROWSERS_PATH=/Volumes/Crucial1TB/.cache/ms-playwright \\
    .venv/bin/python scripts/video/capture.py

Writes out/video/shots/*.png plus out/video/shots/shots.json, which records, for every
shot, the screenshot and the pixel rectangles of the elements the voice-over talks about
(used later for highlights and zooms). Only the public site is opened; no terminal, keys,
or Kahu Ola UI is ever captured.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "video" / "shots"
SITE = "https://smoke-or-vog.pages.dev/"
DPR = 2
WANT: set[str] = set()  # empty = capture everything; else only these shot names (merged)
VIEW = {"width": 1920, "height": 1080}

WAIT_IMAGES = """async () => {
  await document.fonts.ready;
  await Promise.all([...document.images].map(i => i.complete ? 0 :
    new Promise(r => { i.onload = i.onerror = r; })));
  await new Promise(r => setTimeout(r, 350));
  return document.images.length;
}"""


def rect(page, selector: str, nth: int = 0) -> list[float] | None:
    """Element rect in screenshot pixels (viewport coords x DPR), or None."""
    r = page.evaluate("""([sel, n]) => {
      const els = [...document.querySelectorAll(sel)];
      const e = els[n]; if (!e) return null;
      const b = e.getBoundingClientRect();
      return [b.left, b.top, b.right, b.bottom];
    }""", [selector, nth])
    return [v * DPR for v in r] if r else None


def text_rect(page, selector: str, starts: str) -> list[float] | None:
    r = page.evaluate("""([sel, s]) => {
      const e = [...document.querySelectorAll(sel)].find(x => x.textContent.trim().startsWith(s));
      if (!e) return null; const b = e.getBoundingClientRect();
      return [b.left, b.top, b.right, b.bottom];
    }""", [selector, starts])
    return [v * DPR for v in r] if r else None


def union(*rs):
    rs = [r for r in rs if r]
    return [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]


def go(page, run: str, step: int) -> None:
    page.evaluate(f"location.hash = '#run={run}&step={step}'")
    page.wait_for_function(f"location.hash.includes('step={step}')")
    page.wait_for_timeout(500)
    page.evaluate(WAIT_IMAGES)


def scroll_to(page, selector: str, offset: int = 90) -> None:
    page.evaluate("""([sel, off]) => {
      const e = document.querySelector(sel);
      window.scrollTo(0, Math.max(0, e.getBoundingClientRect().top + window.scrollY - off));
    }""", [selector, offset])
    page.wait_for_timeout(250)
    page.evaluate(WAIT_IMAGES)


def snap(page, name: str, shots: dict, rects: dict, full: bool = False) -> None:
    if WANT and name not in WANT:
        return
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=full)
    shots[name] = {"file": path.name, "rects": rects, "full": full,
                   "scroll_y": page.evaluate("window.scrollY") * DPR}
    print("shot", name, {k: [round(v) for v in r] if r else None for k, r in rects.items()})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shots: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=DPR, locale="en-US")
        ctx.add_init_script("try { localStorage.setItem('sov-lang', 'en'); } catch (e) {}")
        page = ctx.new_page()
        page.goto(SITE + "?video=1", wait_until="networkidle")
        page.evaluate(WAIT_IMAGES)

        # Pre-load every replay and step so no image ever loads on camera.
        for run in ["replays/kilauea_20261017", "replays/maui_20230808", "replays/mauna_loa_20221201"]:
            for step in range(1, 8):
                go(page, run, step)
        live = page.evaluate("""() => ({
            line: document.querySelector('.live__line')?.textContent || null,
            card: !!document.querySelector('.live__card'),
            verdict: document.querySelector('.live__card .verdict-line')?.textContent || null })""")
        print("live:", live)

        K = "replays/kilauea_20261017"
        # S2: replay banner, then step 1
        go(page, K, 1)
        scroll_to(page, "#viewer-h", 70)
        snap(page, "s2_banner", shots, {"hl": rect(page, ".replay-banner"),
                                        "zoom": union(rect(page, "#viewer-h"), rect(page, ".replay-banner"),
                                                      rect(page, "#frame"))})
        snap(page, "s2_step1", shots, {"hl": union(rect(page, "#step-0"), rect(page, "#frame")),
                                       "zoom": union(rect(page, "#steps"), rect(page, "#frame"), rect(page, "#explain"))})
        # S3: Muse Spark boxes
        go(page, K, 3)
        scroll_to(page, "#steps", 40)
        snap(page, "s3_spark", shots, {"hl": rect(page, "#frame"), "zoom": rect(page, "#frame")})
        # S4: SAM masks, then the pass table
        go(page, K, 4)
        scroll_to(page, "#steps", 40)
        snap(page, "s4_sam", shots, {"hl": rect(page, "#frame"), "zoom": rect(page, "#frame"),
                                     "table": rect(page, "#explain table")})
        # S5: agent trace (full page for a scroll), then the verification note
        go(page, K, 5)
        scroll_to(page, "#steps", 40)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(200)
        trace = page.evaluate("""() => { const b = document.querySelector('.trace').getBoundingClientRect();
            const s = document.querySelector('#steps').getBoundingClientRect();
            const o = document.querySelector('.ok-note').getBoundingClientRect();
            return {steps_top: s.top + scrollY, trace_top: b.top + scrollY, trace_bottom: b.bottom + scrollY,
                    ok_top: o.top + scrollY, ok_bottom: o.bottom + scrollY,
                    x0: b.left, x1: b.right, page_h: document.documentElement.scrollHeight}; }""")
        if not WANT or "s5_trace_full" in WANT:
            page.screenshot(path=str(OUT / "s5_trace_full.png"), full_page=True)
            shots["s5_trace_full"] = {"file": "s5_trace_full.png", "full": True,
                                      "geom": {k: v * DPR for k, v in trace.items()}, "rects": {}}
            print("shot s5_trace_full", trace)
        scroll_to(page, ".ok-note", 520)
        snap(page, "s5_ok", shots, {"hl": rect(page, ".ok-note"), "zoom": union(rect(page, ".trace"), rect(page, ".ok-note"))})
        # S6: Kīlauea verdict, then Maui verdict
        go(page, K, 6)
        scroll_to(page, "#steps", 40)
        snap(page, "s6_kilauea", shots, {"hl": rect(page, "#explain .verdict-line"),
                                         "zoom": union(rect(page, "#frame"), rect(page, "#explain .verdict-line"))})
        go(page, "replays/maui_20230808", 6)
        scroll_to(page, "#steps", 40)
        snap(page, "s6_maui", shots, {"hl": rect(page, "#explain .verdict-line"),
                                      "zoom": union(rect(page, "#frame"), rect(page, "#explain .verdict-line"))})
        # S7: Mauna Loa uncertain + unconfirmed line
        go(page, "replays/mauna_loa_20221201", 6)
        scroll_to(page, "#steps", 40)
        snap(page, "s7_mauna_loa", shots, {"hl": rect(page, "#explain .verdict-line"),
                                           "unconf": text_rect(page, "#explain p.small", "Not confirmed"),
                                           "zoom": union(rect(page, "#frame"), rect(page, "#explain .verdict-line"))})
        # S8: alerts EN card, VI guidance, Hawaiian card
        go(page, K, 7)
        scroll_to(page, "#steps", 40)
        snap(page, "s8_en", shots, {"hl": rect(page, "#frame"), "zoom": rect(page, "#frame")})
        page.click("text=Vietnamese (Tiếng Việt)")
        page.wait_for_timeout(400)
        page.evaluate(WAIT_IMAGES)
        scroll_to(page, ".guidance-h", 330)
        snap(page, "s8_vi", shots, {"hl": union(rect(page, ".guidance-h"), rect(page, "ul.guidance")),
                                    "zoom": union(rect(page, ".guidance-h"), rect(page, "ul.guidance"), rect(page, "#frame"))})
        page.click("text=ʻŌlelo Hawaiʻi")
        page.wait_for_timeout(400)
        page.evaluate(WAIT_IMAGES)
        scroll_to(page, "#steps", 40)
        snap(page, "s8_haw", shots, {"hl": rect(page, "#frame"), "zoom": rect(page, "#frame")})
        # S9: live status at the top
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        sel = ".live__status" if not live["card"] else ".live__card"
        snap(page, "s9_live", shots, {"hl": rect(page, sel), "zoom": union(rect(page, "#live-h"), rect(page, sel))})
        # S10a: How it works
        scroll_to(page, "#how-h", 120)
        snap(page, "s10_how", shots, {"hl": rect(page, ".how__models"),
                                      "zoom": union(rect(page, "#how-h"), rect(page, ".how__models"))})
        ctx.close()

        # S10b: phone view (iPhone emulation), full page for a scroll
        if WANT and "s10_phone_full" not in WANT:
            browser.close()
            return finish(shots, live)
        iphone = p.devices["iPhone 13"]
        pctx = browser.new_context(**iphone, locale="en-US")
        pctx.add_init_script("try { localStorage.setItem('sov-lang', 'en'); } catch (e) {}")
        pp = pctx.new_page()
        pp.goto(SITE + "?video=2", wait_until="networkidle")
        pp.evaluate(WAIT_IMAGES)
        pp.screenshot(path=str(OUT / "s10_phone_full.png"), full_page=True)
        shots["s10_phone_full"] = {"file": "s10_phone_full.png", "full": True, "rects": {},
                                   "dpr": iphone["device_scale_factor"],
                                   "viewport": iphone["viewport"]}
        print("shot s10_phone_full", iphone["viewport"], iphone["device_scale_factor"])
        pctx.close()
        browser.close()
    return finish(shots, live)


def finish(shots: dict, live: dict) -> None:
    f = OUT / "shots.json"
    if WANT and f.exists():  # merge: keep earlier shots and the live status the VO describes
        old = json.loads(f.read_text())
        old["shots"].update(shots)
        shots, live = old["shots"], old["live"]
    f.write_text(json.dumps({"dpr": DPR, "live": live, "shots": shots}, indent=1, ensure_ascii=False))
    print("wrote", f, "(merged)" if WANT else "")


if __name__ == "__main__":
    WANT.update(a for a in sys.argv[1:] if not a.startswith("-"))
    sys.exit(main())
