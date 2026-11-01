"""Plume motion tracking with SAM 3.1 video (behind the --track flag).

A trailing ~3 h window of GOES-West GeoColor frames (10-min cadence) ending at the scan
time is encoded as an MP4 and sent to SAM 3.1 video, seeded with each plume's box on the
scan frame. Per-frame masks give a centroid track; a least-squares fit gives the drift
direction and speed; the mask's far end against the drift is the inferred source end.

Only GOES-West (10-minute) imagery can be tracked. Daily MODIS/VIIRS replays return
{"available": False}.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import geo, sources
from .common import SAM_PER_IMAGE, async_client, log_cost  # noqa: F401

from meta_sam_parser import (FramePrompt, PromptBox, PromptObject, build_object_prompt,
                             decode_mask_to_raster, parse_responses_stream,
                             video_segmentation_format)

TRACKABLE_LAYERS = {"GOES-West_ABI_GeoColor"}
WINDOW_MIN, STEP_MIN = 180, 10
SAM_VIDEO_PER_FRAME = 0.20 / 1000
MIN_BILLED_FRAMES = 50
UNAVAILABLE = "tracking not available for archived MODIS days (daily imagery, no 10-minute frames)"
_FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NotoSans-Bold.ttf"


# ------------------------------------------------------------------ math (pure, tested)

def bearing_deg(lat0, lon0, lat1, lon1) -> float:
    """Initial bearing from point 0 to point 1, degrees clockwise from north."""
    p0, p1 = math.radians(lat0), math.radians(lat1)
    dl = math.radians(lon1 - lon0)
    y = math.sin(dl) * math.cos(p1)
    x = math.cos(p0) * math.sin(p1) - math.sin(p0) * math.cos(p1) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def fit_motion(points: list[tuple[float, float, float]]) -> dict | None:
    """points: (t_hours, lat, lon). Least-squares velocity of the centroid.
    Returns speed_kmh, toward_deg, r2 (fraction of positional variance explained), n."""
    if len(points) < 4:
        return None
    lat_ref = sum(p[1] for p in points) / len(points)
    kx = 111.32 * math.cos(math.radians(lat_ref))
    ts = [p[0] for p in points]
    xs = [(p[2]) * kx for p in points]  # km east
    ys = [(p[1]) * 111.32 for p in points]  # km north
    n = len(points)
    tm, xm, ym = sum(ts) / n, sum(xs) / n, sum(ys) / n
    stt = sum((t - tm) ** 2 for t in ts)
    if stt == 0:
        return None
    vx = sum((t - tm) * (x - xm) for t, x in zip(ts, xs)) / stt
    vy = sum((t - tm) * (y - ym) for t, y in zip(ts, ys)) / stt
    res = sum((x - (xm + vx * (t - tm))) ** 2 + (y - (ym + vy * (t - tm))) ** 2
              for t, x, y in zip(ts, xs, ys))
    tot = sum((x - xm) ** 2 + (y - ym) ** 2 for x, y in zip(xs, ys))
    speed = math.hypot(vx, vy)
    return {"speed_kmh": round(speed, 1),
            "toward_deg": round((math.degrees(math.atan2(vx, vy)) + 360) % 360, 0),
            "r2": round(1 - res / tot, 2) if tot > 0 else 0.0, "n": n}


def angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def wind_agreement(track_toward: float, wind_from: float) -> dict:
    """Compare drift direction with wind (wind blows TOWARD from+180)."""
    toward = (wind_from + 180) % 360
    d = angle_diff(track_toward, toward)
    return {"wind_toward_deg": round(toward), "diff_deg": round(d),
            "agrees": d <= 45, "label": "agrees" if d <= 45 else ("partly" if d <= 90 else "disagrees")}


def is_blank(im: Image.Image) -> bool:
    """GIBS answers missing times with an empty (black/transparent) image."""
    small = im.convert("L").resize((70, 50))
    return max(small.getdata()) < 8


# ------------------------------------------------------------------ frames + SAM video

def frame_times(scan_time: str) -> list[datetime]:
    end = datetime.fromisoformat(scan_time.replace("Z", "+00:00"))
    return [end - timedelta(minutes=WINDOW_MIN - i * STEP_MIN) for i in range(WINDOW_MIN // STEP_MIN + 1)]


def fetch_frames(scan_time: str, out_dir: Path) -> list[tuple[datetime, Path]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    got = []
    for t in frame_times(scan_time):
        f = out_dir / f"src_{t:%Y%m%dT%H%MZ}.png"
        if not f.exists():
            try:
                im = sources._gibs_map("GOES-West_ABI_GeoColor", t.strftime("%Y-%m-%dT%H:%M:00Z")).convert("RGB")
            except Exception:  # noqa: BLE001 - a missing frame is skipped
                continue
            if is_blank(im):
                continue
            im.save(f)
        got.append((t, f))
    return got


def encode_mp4(frames: list[Path], path: Path) -> int:
    """One video frame per source image (numbered sequence at 6 fps); returns the frame count
    and fails if the encoder added or dropped frames, so SAM frame indices map 1:1 to times."""
    seq = path.parent / "seq"
    seq.mkdir(exist_ok=True)
    for old in seq.glob("*.png"):
        old.unlink()
    for i, f in enumerate(frames):
        (seq / f"{i:03d}.png").write_bytes(f.read_bytes())
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "6", "-i", str(seq / "%03d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-movflags", "+faststart",
                    str(path)], check=True)
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                          "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    n = int(out.stdout.strip())
    if n != len(frames):
        raise RuntimeError(f"encoded {n} frames for {len(frames)} images")
    return n


async def _sam_video(mp4: Path, prompt: str):
    c = async_client()
    url = "data:video/mp4;base64," + base64.b64encode(mp4.read_bytes()).decode()
    stream = await c.responses.create(
        model="sam-3.1", stream=True, metadata={"include_confidence": "true"},
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt}, {"type": "input_video", "video_url": url}]}])
    usage = {}

    async def tee():
        async for ev in stream:
            if ev.type in ("response.completed", "response.incomplete"):
                usage["frames"] = getattr(getattr(ev.response, "usage", None), "video_frames_processed", None)
            yield ev

    async with stream:
        parsed = parse_responses_stream(tee(), video_segmentation_format())
        async for _ in parsed:
            pass
        res = await parsed.final_result()
    await c.close()
    return res, usage


def _mask_full(rec, size) -> Image.Image:
    raster = decode_mask_to_raster(rec.mask)
    m = Image.frombytes("L", (rec.mask.width, rec.mask.height), bytes(v * 255 for v in raster))
    b = rec.bounds
    bw, bh = max(1, round(b.right - b.left)), max(1, round(b.bottom - b.top))
    if m.size != (bw, bh):
        m = m.resize((bw, bh), Image.NEAREST)
    full = Image.new("L", size, 0)
    full.paste(m, (round(b.left), round(b.top)))
    return full


def _centroid(mask: Image.Image) -> tuple[float, float, int] | None:
    bb = mask.getbbox()
    if not bb:
        return None
    px = mask.load()
    sx = sy = n = 0
    for y in range(bb[1], bb[3], 2):
        for x in range(bb[0], bb[2], 2):
            if px[x, y]:
                sx += x
                sy += y
                n += 1
    return (sx / n, sy / n, n * 4) if n else None


def source_end(mask: Image.Image, toward_deg: float) -> tuple[float, float] | None:
    """Mask pixel furthest AGAINST the drift (upwind end = likely source side)."""
    bb = mask.getbbox()
    if not bb:
        return None
    ux, uy = math.sin(math.radians(toward_deg)), -math.cos(math.radians(toward_deg))
    px = mask.load()
    best, pt = 1e18, None
    for y in range(bb[1], bb[3], 2):
        for x in range(bb[0], bb[2], 2):
            if px[x, y]:
                v = x * ux + y * uy
                if v < best:
                    best, pt = v, (x, y)
    return pt


def track_run(run_dir: Path, scan_time: str, layer: str, plumes_px: list[dict], run_id: str) -> dict:
    """Track every segmented plume through the trailing 3 h window. Writes 05_track.json and
    track/ frames with the tracked outline drawn. plumes_px: [{plume_id, box:[x1,y1,x2,y2]}]."""
    run_dir = Path(run_dir)
    if layer not in TRACKABLE_LAYERS:
        out = {"available": False, "reason": UNAVAILABLE}
        (run_dir / "05_track.json").write_text(json.dumps(out, indent=1))
        return out
    if not plumes_px:
        out = {"available": False, "reason": "no plume to track"}
        (run_dir / "05_track.json").write_text(json.dumps(out, indent=1))
        return out
    tdir = run_dir / "track"
    frames = fetch_frames(scan_time, tdir)
    if len(frames) < 6:
        out = {"available": False, "reason": f"only {len(frames)} GOES-West frames in the window"}
        (run_dir / "05_track.json").write_text(json.dumps(out, indent=1))
        return out
    mp4 = tdir / "clip.mp4"
    encode_mp4([f for _, f in frames], mp4)
    size = Image.open(frames[-1][1]).size
    seed = len(frames) - 1  # the scan frame
    objs = [PromptObject(id=p["plume_id"], prompts=[FramePrompt(
        frame=seed, box=PromptBox(p["box"][0], p["box"][1], p["box"][2] + 1, p["box"][3] + 1))])
        for p in plumes_px[:16]]
    prompt = build_object_prompt(size=size, objects=objs)
    res, usage = asyncio.run(_sam_video(mp4, prompt))
    billed = max(MIN_BILLED_FRAMES, usage.get("frames") or 0)
    log_cost("pipeline:track", "sam-3.1", billed * SAM_VIDEO_PER_FRAME, units=f"{billed} frames",
             note=f"run={run_id}; video {len(frames)} frames")
    t_end = frames[-1][0]
    masks: dict[int, dict[int, Image.Image]] = {}
    for r in res.records:
        if r.kind == "mask" and r.frame is not None and r.frame.frame_index < len(frames):
            masks.setdefault(int(r.object_id), {})[r.frame.frame_index] = _mask_full(r, size)
    plumes = []
    for p in plumes_px[:16]:
        pid = p["plume_id"]
        per = masks.get(pid, {})
        pts, rows = [], []
        for fi in sorted(per):
            c = _centroid(per[fi])
            if not c:
                continue
            lon, lat = geo.px_to_lonlat(c[0], c[1])
            th = (frames[fi][0] - t_end).total_seconds() / 3600
            pts.append((th, lat, lon))
            rows.append({"frame": fi, "time": frames[fi][0].strftime("%Y-%m-%dT%H:%MZ"),
                         "lat": round(lat, 4), "lon": round(lon, 4), "area_px": c[2]})
        motion = fit_motion(pts)
        entry = {"plume_id": pid, "frames_tracked": len(rows), "frames_total": len(frames),
                 "track": rows, "motion": motion}
        if motion and seed in per:
            se = source_end(per[seed], motion["toward_deg"])
            if se:
                lon, lat = geo.px_to_lonlat(*se)
                entry["source_end"] = {"lat": round(lat, 4), "lon": round(lon, 4),
                                       "distance_km": {n: round(geo.haversine_km(lat, lon, *ll), 1)
                                                       for n, ll in geo.SOURCES.items()}}
        plumes.append(entry)
    render_track_frames(frames, masks, plumes, tdir)
    out = {"available": True, "layer": layer, "window_min": WINDOW_MIN, "step_min": STEP_MIN,
           "scan_time": scan_time, "frames": [t.strftime("%Y-%m-%dT%H:%MZ") for t, _ in frames],
           "billed_frames": billed, "cost_usd": round(billed * SAM_VIDEO_PER_FRAME, 4),
           "plumes": plumes,
           "note": "Centroid drift of a plume still attached to its source is slower than the "
                   "air; direction is the main signal, speed is approximate."}
    (run_dir / "05_track.json").write_text(json.dumps(out, indent=1))
    return out


def render_track_frames(frames, masks, plumes, tdir: Path) -> None:
    """Draw each frame with every tracked mask outline and the centroid path so far."""
    colors = [(0, 255, 210), (255, 205, 60), (255, 120, 200), (120, 200, 255)]
    f = ImageFont.truetype(str(_FONT), 30)
    paths = {p["plume_id"]: [(r["frame"], geo.lonlat_to_px(r["lon"], r["lat"])) for r in p["track"]]
             for p in plumes}
    for fi, (t, src) in enumerate(frames):
        im = Image.open(src).convert("RGBA")
        k = im.width / 1400
        lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for j, (pid, per) in enumerate(sorted(masks.items())):
            col = colors[j % len(colors)]
            m = per.get(fi)
            if m is not None:
                from PIL import ImageFilter
                edge = m.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
                lay.paste(Image.new("RGBA", im.size, col + (255,)), (0, 0), edge)
                lay.paste(Image.new("RGBA", im.size, col + (50,)), (0, 0), m)
            pts = [xy for ff, xy in paths.get(pid, []) if ff <= fi]
            if len(pts) > 1:
                d.line(pts, fill=(255, 255, 255, 230), width=max(2, round(3 * k)))
            if pts:
                x, y = pts[-1]
                r = 6 * k
                d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255))
        out = Image.alpha_composite(im, lay).convert("RGB")
        ImageDraw.Draw(out).text((14 * k, 10 * k), f"{t:%H:%M} UTC", font=f, fill=(255, 255, 255),
                                 stroke_width=3, stroke_fill=(0, 0, 0))
        out.save(tdir / f"t_{fi:02d}.jpg", quality=82)
