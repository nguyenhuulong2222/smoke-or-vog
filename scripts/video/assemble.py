"""Assemble the 3-minute demo: shots + voice-over + burned-in captions -> MP4.

    .venv/bin/python scripts/video/assemble.py

Inputs: out/video/shots/ (capture.py), out/video/audio/ (tts.py), docs/VIDEO_SCRIPT.md.
Output: out/video/smoke-or-vog-demo.mp4 (1920x1080, 30 fps, H.264 + AAC, exactly 180 s).
Frames are rendered in Python (eased zoom/pan on 2x screenshots, highlight spotlights,
captions in Noto Sans so ʻokina and kahakō render correctly) and piped to FFmpeg.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenes import ROOT, TOTAL, scenes  # noqa: E402

VID = ROOT / "out" / "video"
SHOTS = VID / "shots"
AUDIO = VID / "audio"
OUT_MP4 = VID / "smoke-or-vog-demo.mp4"
W, H, FPS = 1920, 1080, 30
FONT_B = ROOT / "assets" / "fonts" / "NotoSans-Bold.ttf"
FONT_R = ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"
NAVY, GOLD, INK = (18, 58, 94), (255, 205, 60), (12, 18, 28)
TARGET_WPM = 140
VO_LEAD, VO_TAIL = 0.25, 0.35
TITLE_S, END_S = 2.0, 4.0
LAST = 11  # final scene (ends with the end card)
HOOK_IMAGE = ROOT / "out" / "runs" / "kilauea_20261017_20261101T012112Z" / "00_image.jpg"


def font(size, bold=True):
    return ImageFont.truetype(str(FONT_B if bold else FONT_R), size)


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ffprobe_dur(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


# ------------------------------------------------------------------ audio

def prepare_audio(sc: list[dict]) -> list[dict]:
    """Trim silence, nudge tempo toward TARGET_WPM, guarantee each clip fits its slot."""
    (VID / "audio_proc").mkdir(exist_ok=True)
    placed = []
    for s in sc:
        src = AUDIO / f"scene_{s['n']:02d}.wav"
        trimmed = VID / "audio_proc" / f"t_{s['n']:02d}.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af",
                        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                        "silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                        "-ar", "48000", "-ac", "1", str(trimmed)], check=True)
        d = ffprobe_dur(trimmed)
        start = s["start"] + (TITLE_S if s["n"] == 1 else 0) + VO_LEAD
        end_limit = s["end"] - (END_S if s["n"] == LAST else 0) - VO_TAIL
        budget = end_limit - start
        words = len(s["vo"].split())
        f = d / (words / TARGET_WPM * 60)           # >1 = speed up
        f = min(1.25, max(1.0, f))                   # never slow down (keeps the voice natural)
        f = max(f, d / budget)                       # must fit the slot
        if f > 1.35:
            raise SystemExit(f"scene {s['n']}: needs tempo {f:.2f} to fit; shorten the line")
        out = VID / "audio_proc" / f"p_{s['n']:02d}.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(trimmed), "-af", f"atempo={f:.4f}",
                        "-ar", "48000", "-ac", "1", str(out)], check=True)
        dd = ffprobe_dur(out)
        placed.append({**s, "audio": out, "a0": start, "a1": start + dd, "tempo": round(f, 3),
                       "wpm": round(words / dd * 60)})
    # One 180 s track: place each clip at its start, mix, normalise loudness, pad/trim.
    args = ["ffmpeg", "-y", "-v", "error"]
    for p in placed:
        args += ["-i", str(p["audio"])]
    filt = "".join(f"[{i}:a]adelay={int(p['a0'] * 1000)}:all=1[a{i}];" for i, p in enumerate(placed))
    filt += "".join(f"[a{i}]" for i in range(len(placed)))
    filt += (f"amix=inputs={len(placed)}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,"
             f"apad=whole_dur={TOTAL},atrim=0:{TOTAL}[out]")
    args += ["-filter_complex", filt, "-map", "[out]", "-ar", "48000", "-ac", "2",
             str(VID / "voiceover.wav")]
    subprocess.run(args, check=True)
    return placed


# ------------------------------------------------------------------ captions

def caption_chunks(p: dict) -> list[dict]:
    """Split a scene's VO into ≤2-line chunks, timed by character share of the clip."""
    f = font(40)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    max_w = 1480
    sentences = re.split(r"(?<=[.!?:;])\s+", p["vo"])
    pieces = []
    for sent in sentences:
        words, line, lines = sent.split(), "", []
        for w in words:
            t = (line + " " + w).strip()
            if probe.textlength(t, font=f) <= max_w:
                line = t
            else:
                lines.append(line)
                line = w
        if line:
            lines.append(line)
        for i in range(0, len(lines), 2):
            pieces.append(lines[i:i + 2])
    total = sum(len(" ".join(x)) for x in pieces)
    t = p["a0"]
    out = []
    for lines in pieces:
        dur = (p["a1"] - p["a0"]) * len(" ".join(lines)) / total
        out.append({"t0": t, "t1": t + dur, "lines": lines})
        t += dur
    out[-1]["t1"] = p["a1"] + 0.25
    return out


def caption_image(lines: list[str]) -> Image.Image:
    f = font(40)
    d0 = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    tw = max(d0.textlength(l, font=f) for l in lines)
    lh = 54
    bw, bh = int(tw + 56), int(lh * len(lines) + 30)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0 = (W - bw) // 2, H - 56 - bh
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=14, fill=(0, 0, 0, 175))
    for i, l in enumerate(lines):
        lw = d.textlength(l, font=f)
        d.text(((W - lw) / 2, y0 + 12 + i * lh), l, font=f, fill=(255, 255, 255, 255))
    return im


def anchor(chunks: list[dict], word: str, default: float) -> float:
    for c in chunks:
        if word.lower() in " ".join(c["lines"]).lower():
            return c["t0"]
    return default


# ------------------------------------------------------------------ shot renderers

class Still:
    """A screenshot with an eased zoom from `start_win` to the 16:9 window around `zoom`,
    and highlight rectangles that fade in."""

    def __init__(self, img: Path | Image.Image, zoom=None, hl=None, zoom_in=0.45, pad=0.12,
                 start_win=None, drift=0.03, dim=0.42, hl_delay=0.35):
        self.im = img if isinstance(img, Image.Image) else Image.open(img).convert("RGB")
        self.iw, self.ih = self.im.size
        full = (0.0, 0.0, float(self.iw), float(self.ih))
        self.w0 = start_win or full
        self.w1 = self.window(zoom, pad) if zoom else full
        self.zoom_in, self.drift, self.dim, self.hl_delay = zoom_in, drift, dim, hl_delay
        self.hl = [r for r in (hl or []) if r]
        self._cache = {}

    def window(self, r, pad):
        x0, y0, x1, y1 = r
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w = (x1 - x0) * (1 + 2 * pad)
        h = (y1 - y0) * (1 + 2 * pad)
        w = max(w, h * 16 / 9, self.iw * 0.28)
        w = min(w, self.iw, self.ih * 16 / 9)
        h = w * 9 / 16
        x = min(max(0, cx - w / 2), self.iw - w)
        y = min(max(0, cy - h / 2), self.ih - h)
        return (x, y, x + w, y + h)

    def win_at(self, u):
        k = ease(u / self.zoom_in) if self.zoom_in > 0 else 1.0
        win = tuple(a + (b - a) * k for a, b in zip(self.w0, self.w1))
        if self.drift and u > self.zoom_in:  # slow push-in during the hold
            z = 1 - self.drift * ease((u - self.zoom_in) / (1 - self.zoom_in))
            cx, cy = (win[0] + win[2]) / 2, (win[1] + win[3]) / 2
            hw, hh = (win[2] - win[0]) * z / 2, (win[3] - win[1]) * z / 2
            win = (cx - hw, cy - hh, cx + hw, cy + hh)
        return win

    def frame(self, u: float, dur: float) -> Image.Image:
        win = self.win_at(u)
        key = tuple(round(v, 1) for v in win)
        base = self._cache.get(key)
        if base is None:
            base = self.im.resize((W, H), Image.LANCZOS, box=win)
            self._cache = {key: base}
        out = base.convert("RGBA")
        a = ease((u * dur - self.hl_delay) / 0.5)
        if self.hl and a > 0:
            sx, sy = W / (win[2] - win[0]), H / (win[3] - win[1])
            boxes = [((r[0] - win[0]) * sx, (r[1] - win[1]) * sy,
                      (r[2] - win[0]) * sx, (r[3] - win[1]) * sy) for r in self.hl]
            if self.dim:
                mask = Image.new("L", (W, H), int(255 * self.dim * a))
                md = ImageDraw.Draw(mask)
                for b in boxes:
                    md.rounded_rectangle([b[0] - 10, b[1] - 10, b[2] + 10, b[3] + 10], radius=16, fill=0)
                out = Image.composite(Image.new("RGBA", (W, H), INK + (255,)), out, mask)
            d = ImageDraw.Draw(out)
            for b in boxes:
                d.rounded_rectangle([b[0] - 10, b[1] - 10, b[2] + 10, b[3] + 10], radius=16,
                                    outline=GOLD + (int(255 * a),), width=5)
        return out


class Pan:
    """Vertical scroll over a full-page screenshot (3840 wide at 2x)."""

    def __init__(self, img: Path, y0: float, y1: float, hl=None, hold=0.12):
        self.im = Image.open(img).convert("RGB")
        self.y0, self.y1, self.hold = y0, y1, hold
        self.hl = hl
        self.vw, self.vh = self.im.size[0], self.im.size[0] * 9 / 16

    def frame(self, u, dur):
        k = ease((u - self.hold) / (1 - 2 * self.hold))
        y = self.y0 + (self.y1 - self.y0) * k
        y = min(max(0, y), self.im.size[1] - self.vh)
        win = (0, y, self.vw, y + self.vh)
        out = self.im.resize((W, H), Image.LANCZOS, box=win).convert("RGBA")
        if self.hl:
            s = W / self.vw
            x0, ya, x1, yb = self.hl
            d = ImageDraw.Draw(out)
            d.rounded_rectangle([(x0) * s - 10, (ya - y) * s - 10, x1 * s + 10, (yb - y) * s + 10],
                                radius=16, outline=GOLD + (255,), width=5)
        return out


class Phone:
    """iPhone-sized viewport scrolling over a full-page phone screenshot, centered on dark."""

    def __init__(self, img: Path, view_h_px: int, y_end_frac=0.42):
        self.im = Image.open(img).convert("RGB")
        self.vw, self.vh = self.im.size[0], view_h_px
        self.y_end = (self.im.size[1] - self.vh) * y_end_frac
        self.scale = 900 / self.vh
        self.bg = Image.new("RGBA", (W, H), (15, 26, 38, 255))
        pw, ph = int(self.vw * self.scale), int(self.vh * self.scale)
        self.pw, self.ph = pw, ph
        self.px, self.py = (W - pw) // 2, (H - ph) // 2 - 10
        d = ImageDraw.Draw(self.bg)
        d.rounded_rectangle([self.px - 18, self.py - 18, self.px + pw + 18, self.py + ph + 18],
                            radius=48, fill=(8, 10, 14, 255), outline=(70, 80, 95, 255), width=3)
        self.mask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(self.mask).rounded_rectangle([0, 0, pw, ph], radius=34, fill=255)

    def frame(self, u, dur):
        y = self.y_end * ease((u - 0.1) / 0.8)
        crop = self.im.resize((self.pw, self.ph), Image.LANCZOS, box=(0, y, self.vw, y + self.vh))
        out = self.bg.copy()
        out.paste(crop, (self.px, self.py), self.mask)
        return out


class Card:
    def __init__(self, im: Image.Image):
        self.im = im.convert("RGBA")

    def frame(self, u, dur):
        return self.im


def title_card() -> Image.Image:
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    for txt, f, y, col in [("Smoke or Vog?", font(132), 370, (255, 255, 255)),
                           ("Meta Global AI Developer Hackathon", font(52, False), 620, (230, 236, 242))]:
        tw = d.textlength(txt, font=f)
        d.text(((W - tw) / 2, y), txt, font=f, fill=col)
    d.rectangle([(W - 160) // 2, 584, (W + 160) // 2, 590], fill=GOLD)  # accent between title and subtitle
    return im


def end_card() -> Image.Image:
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    rows = [("Smoke or Vog?", font(120), 300, (255, 255, 255)),
            ("smoke-or-vog.pages.dev", font(64), 470, GOLD),
            ("Satellite estimate, not an official warning", font(46, False), 600, (235, 240, 245)),
            ("Built during the Meta Global AI Developer Hackathon · Hawaiʻi", font(36, False), 690, (200, 212, 225)),
            ("AI voice-over (OpenAI TTS)", font(32, False), 770, (190, 200, 214))]
    for txt, f, y, col in rows:
        tw = d.textlength(txt, font=f)
        d.text(((W - tw) / 2, y), txt, font=f, fill=col)
    return im


# ------------------------------------------------------------------ timeline

def build_timeline(placed: list[dict], caps: dict[int, list[dict]], meta: dict) -> list[tuple]:
    S = meta["shots"]
    R = lambda n: S[n]["rects"]  # noqa: E731
    img = lambda n: SHOTS / S[n]["file"]  # noqa: E731
    sc = {p["n"]: p for p in placed}
    tl = []

    def add(t0, t1, r):
        tl.append((t0, t1, r))

    # 1 — title card, then hook push-in on the Kīlauea true-color image
    add(0, TITLE_S, Card(title_card()))
    hook = Image.open(HOOK_IMAGE).convert("RGB")  # 1400x1000 pipeline image of Oct 17 2026
    hw, hh = hook.size
    start = (0, (hh - hw * 9 / 16) / 2, hw, (hh + hw * 9 / 16) / 2)
    plume = (930, 700, 1290, 990)  # haze south of Hawaiʻi Island (from the run's SAM mask bbox)
    add(TITLE_S, sc[1]["end"], Still(hook, zoom=plume, pad=0.9, start_win=start, zoom_in=0.95, drift=0, hl=None))
    # Scene boundaries come from docs/VIDEO_SCRIPT.md.
    B = {p["n"]: (p["start"], p["end"]) for p in placed}

    def St(name, key="zoom", hl="hl", **kw):
        r = R(name)
        return Still(img(name), zoom=r[key], hl=[r[hl]] if hl and r.get(hl) else None, **kw)

    # 2 — replay banner, then step 1
    s0, s1 = B[2]
    t = anchor(caps[2], "labelled", s0 + 4)
    add(s0, t, St("s2_banner", pad=0.06))
    add(t, s1, St("s2_step1", pad=0.04, dim=0.3))
    # 3 — Muse Spark box, then SAM still masks (switch on "SAM")
    s0, s1 = B[3]
    t = anchor(caps[3], "SAM", s0 + 6)
    add(s0, t, St("s3_spark", pad=0.05, zoom_in=0.35, dim=0.0, hl_delay=1.0))
    add(t, s1, St("s4_sam", pad=0.05, zoom_in=0.3, dim=0.0, hl_delay=0.8))
    # 4 — time-lapse: first frame, last frame (on "It drifts"), then the motion line (on "roughly")
    s0, s1 = B[4]
    t1 = anchor(caps[4], "It drifts", s0 + 7)
    t2 = anchor(caps[4], "roughly", s0 + 12)
    if t2 <= t1 + 1.5:
        t2 = min(s1 - 2.5, t1 + 3.0)
    add(s0, t1, St("s4_lapse0", pad=0.04, zoom_in=0.3, dim=0.0, hl_delay=0.6))
    add(t1, t2, St("s4_lapse", pad=0.04, zoom_in=0.0, dim=0.0, hl=None))
    lz = Still(img("s4_lapse")).window(R("s4_lapse")["zoom"], 0.04)
    add(t2, s1, Still(img("s4_lapse"), zoom=R("s4_lapse")["motion"], hl=[R("s4_lapse")["motion"]],
                      pad=0.35, start_win=lz, zoom_in=0.3))
    # 5 — agent trace scroll, then the verification note (on "Every claim")
    s0, s1 = B[5]
    g = S["s5_trace_full"]["geom"]
    t = anchor(caps[5], "Every claim", s0 + 13)
    add(s0, t, Pan(img("s5_trace_full"), y0=g["steps_top"] - 120, y1=g["ok_bottom"] - 2160 + 260,
                   hl=(g["x0"], g["trace_top"], g["x1"], g["trace_bottom"])))
    ok = R("s5_ok")
    add(t, s1, Still(img("s5_ok"), zoom=ok["hl"], hl=[ok["hl"]], pad=1.2, zoom_in=0.3))
    # 6 — Kīlauea verdict, then Maui (on "Maui")
    s0, s1 = B[6]
    t = anchor(caps[6], "Maui", s0 + 7)
    add(s0, t, St("s6_kilauea", pad=0.04))
    add(t, s1, St("s6_maui", pad=0.04))
    # 7 — Mauna Loa uncertain, then the Muse Wonder second-opinion box (on "Muse Wonder")
    s0, s1 = B[7]
    t = anchor(caps[7], "Muse Wonder", s0 + 7)
    add(s0, t, St("s7_mauna_loa", pad=0.04))
    add(t, s1, St("s7_wonder", pad=0.08, dim=0.25))
    # 8 — EN card, VI quoted guidance (on "Health guidance"), Hawaiian card (on "The AI only")
    s0, s1 = B[8]
    t1 = anchor(caps[8], "Health guidance", s0 + 4)
    t2 = anchor(caps[8], "The AI only", s0 + 9)
    add(s0, t1, St("s8_en", pad=0.04, dim=0.0, hl_delay=0.8))
    add(t1, t2, St("s8_vi", key="hl", pad=0.06))
    add(t2, s1, St("s8_haw", pad=0.04, dim=0.0, hl_delay=0.5))
    # 9 — History calendar, then accuracy table (on "The lesson"), then the no-plume finding (on "So no plume")
    s0, s1 = B[9]
    t1 = anchor(caps[9], "The lesson", s0 + 7)
    t2 = anchor(caps[9], "So no plume", s0 + 13)
    add(s0, t1, St("s9_history", pad=0.05, dim=0.2))
    add(t1, t2, St("s9_accuracy", key="table", hl="table", pad=0.1, dim=0.25))
    add(t2, s1, St("s9_accuracy", pad=0.05, dim=0.35))
    # 10 — Ask: languages + mic, then the answer (on "Muse Voice Transcribe")
    s0, s1 = B[10]
    t = anchor(caps[10], "Muse Voice Transcribe", s0 + 7)
    a = R("s10_ask")
    add(s0, t, Still(img("s10_ask"), zoom=a["zoom"], hl=[a["langs"], a["mic"]], pad=0.06, dim=0.3))
    add(t, s1, Still(img("s10_ask"), zoom=a["answer"], hl=[a["answer"]], pad=0.15, dim=0.3,
                     start_win=Still(img("s10_ask")).window(a["zoom"], 0.06), zoom_in=0.3))
    # 11 — How it works (models), phone view (on "Everything you saw"), end card
    s0, s1 = B[11]
    t = anchor(caps[11], "Everything you saw", s0 + 9)
    add(s0, t, St("s10_how", pad=0.06))
    ph = S["s10_phone_full"]
    add(t, TOTAL - END_S, Phone(img("s10_phone_full"), int(ph["viewport"]["height"] * ph["dpr"])))
    add(TOTAL - END_S, TOTAL, Card(end_card()))
    return tl


def main() -> None:
    meta = json.loads((SHOTS / "shots.json").read_text())
    sc = scenes()
    placed = prepare_audio(sc)
    caps = {p["n"]: caption_chunks(p) for p in placed}
    tl = build_timeline(placed, caps, meta)
    # sanity: contiguous 0..180
    tl.sort(key=lambda x: x[0])
    assert abs(tl[0][0]) < 1e-6 and abs(tl[-1][1] - TOTAL) < 1e-6
    for a, b in zip(tl, tl[1:]):
        assert abs(a[1] - b[0]) < 1e-6, (a[:2], b[:2])
    cap_list = [(c["t0"], c["t1"], caption_image(c["lines"])) for n in caps for c in caps[n]]
    (VID / "timeline.json").write_text(json.dumps({
        "audio": [{k: p[k] for k in ("n", "a0", "a1", "tempo", "wpm")} for p in placed],
        "shots": [(round(a, 2), round(b, 2), type(r).__name__) for a, b, r in tl],
        "captions": [{"t0": round(c["t0"], 2), "t1": round(c["t1"], 2), "text": " / ".join(c["lines"])}
                     for n in caps for c in caps[n]]}, indent=1, ensure_ascii=False))

    nframes = int(TOTAL * FPS)
    enc = subprocess.Popen([
        "ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", str(FPS), "-i", "-", "-i", str(VID / "voiceover.wav"),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{TOTAL:.3f}", "-movflags", "+faststart", str(OUT_MP4)], stdin=subprocess.PIPE)
    si = 0
    for i in range(nframes):
        t = i / FPS
        while not (tl[si][0] <= t < tl[si][1]):
            si += 1
        a, b, r = tl[si]
        fr = r.frame((t - a) / (b - a), b - a)
        if t >= TITLE_S:
            for c0, c1, ci in cap_list:
                if c0 <= t < c1:
                    fr = Image.alpha_composite(fr.convert("RGBA"), ci)
                    break
        enc.stdin.write(fr.convert("RGB").tobytes())
        if i % (FPS * 15) == 0:
            print(f"  rendered {t:5.1f}s / {TOTAL:.0f}s", flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print("wrote", OUT_MP4)


if __name__ == "__main__":
    main()
