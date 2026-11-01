"""Turn a pipeline run directory into static site data (JSON + web-sized images).

    python -m src.sitedata out/runs/<run_id> site/data/<slug> [--mode replay|live]

The site reads ONLY these files. Nothing secret is copied: run JSON never contains
the API key, and prompts are not exported.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from .alerts import HEALTH
from .pipeline import CASES

HEALTH_PUBLISHERS = {k: v["publisher"].split(" (")[0] for k, v in HEALTH["sources"].items()}

MODELS_USED = [
    {"stage": "2 Localize", "model": "muse-spark-1.3", "what": "vision: find haze/plume boxes and points"},
    {"stage": "3 Segment", "model": "sam-3.1", "what": "box + point prompts → pixel masks (two passes)"},
    {"stage": "4 Agent", "model": "muse-spark-1.3", "what": "tool calling: gathers wind, FIRMS, USGS status, geometry; cites every result"},
    {"stage": "5 Alerts", "model": "muse-spark-1.3", "what": "5-language alerts from official guidance only"},
    {"stage": "5 Cards", "model": "muse-image-1.0", "what": "text-free background illustration"},
]
TITLES = {
    "kilauea_20261017": {"en": "Kīlauea vog plume · Oct 17, 2026",
                         "vi": "Vệt vog Kīlauea · 17/10/2026"},
    "maui_20230808": {"en": "Maui wildfire smoke · Aug 8, 2023",
                      "vi": "Khói cháy rừng Maui · 8/8/2023"},
    "mauna_loa_20221201": {"en": "Mauna Loa eruption · Dec 1, 2022 (honest uncertainty)",
                           "vi": "Phun trào Mauna Loa · 1/12/2022 (không chắc chắn, trung thực)"},
    "live": {"en": "Live now", "vi": "Trực tiếp"},
}


def _summarize_tool(name: str, out: dict) -> str:
    """One readable line per tool result for the site's agent trace."""
    if not out.get("ok"):
        return "error: " + str(out.get("error"))[:120]
    r = out.get("result") or {}
    try:
        if name == "get_wind":
            return f"{r.get('speed_kmh')} km/h from {r.get('from_deg')}° ({r.get('time')})"
        if name == "get_volcano_status":
            er = {"yes": "erupting", "no": "not erupting", "episodic_pause": "paused between episodes",
                  "unknown": "status unclear"}
            return "; ".join(f"{'Kīlauea' if k == 'kilauea' else 'Mauna Loa'} {v.get('alert_level')}/"
                             f"{v.get('aviation_color')}, {er.get(v.get('erupting'), v.get('erupting'))}"
                             for k, v in r.get("volcanoes", {}).items())
        if name == "get_firms":
            fc = r.get("fire_clusters", [])
            vt = r.get("volcanic_thermal") or {}
            top = ", ".join(f"{c['near']} ({c['n']})" for c in fc[:3])
            return (f"{len(fc)} fire cluster(s)" + (f": {top}" if top else "")
                    + (f"; summit glow excluded: {', '.join(f'{z} {n}' for z, n in vt.items())}" if vt else ""))
        if name == "distance_to_vents":
            d = r.get("distance_km") or r.get("upwind_end_distance_km") or {}
            return (f"upwind end {d.get('kilauea_summit')} km from Kīlauea, {d.get('mauna_loa_summit')} km "
                    f"from Mauna Loa; area {r.get('area_km2')} km², length {r.get('length_km')} km")
        if name == "land_fraction":
            isl = ", ".join(f"{k} {v:.0%}" for k, v in (r.get("islands_covered") or {}).items())
            return f"{r.get('land_frac', 0):.0%} of mask over land" + (f" ({isl})" if isl else "")
    except Exception:  # noqa: BLE001
        pass
    return json.dumps(r, ensure_ascii=False)[:140]


def _jpg(src: Path | Image.Image, dst: Path, width: int = 1000, q: int = 74) -> str:
    im = src if isinstance(src, Image.Image) else Image.open(src)
    im = im.convert("RGB")
    im.thumbnail((width, width))
    im.save(dst, quality=q, optimize=True, progressive=True)
    return dst.name


def _spark_boxes(image: Image.Image, loc: dict) -> Image.Image:
    im = image.convert("RGB").copy()
    d = ImageDraw.Draw(im)
    for i, p in enumerate(loc.get("pixels", []), start=1):
        d.rectangle(p["box"], outline=(255, 255, 255), width=3)
        x, y = p["inside"]
        d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=(0, 255, 200), width=3)
        d.text((p["box"][0] + 6, p["box"][1] + 4), f"#{i}", fill=(255, 255, 255))
    return im


def _zoom(im: Image.Image, boxes: list[list[float]], margin: float = 0.35,
          aspect: float = 1.4, min_w: int = 420) -> Image.Image:
    """Crop to the union of boxes (+margin), at the frame's aspect ratio, so small
    plumes are legible on a phone. Returns the image unchanged if there are no boxes."""
    if not boxes:
        return im
    x1 = min(b[0] for b in boxes); y1 = min(b[1] for b in boxes)
    x2 = max(b[2] for b in boxes); y2 = max(b[3] for b in boxes)
    w, h = (x2 - x1) * (1 + 2 * margin), (y2 - y1) * (1 + 2 * margin)
    w = max(w, h * aspect, min_w)
    h = w / aspect
    if w >= im.width or h >= im.height:
        return im
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    left = min(max(0, cx - w / 2), im.width - w)
    top = min(max(0, cy - h / 2), im.height - h)
    return im.crop((round(left), round(top), round(left + w), round(top + h)))


def _adp_overlay(image: Image.Image, mask_path: Path) -> Image.Image:
    base = image.convert("RGBA")
    mask = Image.open(mask_path).convert("L")
    tint = Image.new("RGBA", base.size, (255, 230, 0, 140))
    base.paste(tint, (0, 0), mask)
    return base.convert("RGB")


def build(run_dir: Path, out_dir: Path, mode: str | None = None) -> dict:
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    run = json.loads((run_dir / "run.json").read_text())
    ctx0 = json.loads((run_dir / "00_context.json").read_text())
    adp = json.loads((run_dir / "01_adp.json").read_text())
    loc = json.loads((run_dir / "02_spark_localize.json").read_text())
    sam = json.loads((run_dir / "03_sam.json").read_text())
    cls = json.loads((run_dir / "04_classify.json").read_text())
    case = run["case"]
    mode = mode or ("replay" if CASES[case]["historical"] else "live")
    image = Image.open(run_dir / "00_image.jpg")
    res = cls["result"]

    steps: dict = {}
    steps["image"] = {"src": _jpg(image, out_dir / "image.jpg"),
                      "layer": ctx0["image"]["layer"], "time": ctx0["image"]["time"],
                      "source": ctx0["image"]["source"]}
    adp_mask = run_dir / "01_adp_mask.png"
    steps["adp"] = {
        "state": adp.get("state"), "candidates": len(adp.get("candidates", [])),
        "reason": adp.get("reason"), "meaning_of_absence": adp.get("meaning_of_absence"),
        "src": _jpg(_adp_overlay(image, adp_mask), out_dir / "adp.jpg") if adp_mask.exists() else None,
    }
    steps["spark"] = {
        "src": _jpg(_zoom(_spark_boxes(image, loc), [p["box"] for p in loc.get("pixels", [])]),
                    out_dir / "spark_boxes.jpg"),
        "scene": loc["result"]["scene_description"], "cloud_cover": loc["result"]["cloud_cover"],
        "plumes": [{"label": p["label"], "visual_description": p["visual_description"],
                    "visibility": p["visibility"]} for p in loc["result"]["plumes"]],
        "model": loc["meta"].get("model"), "cost_usd": loc["meta"].get("cost_usd"),
    }
    tp = run_dir / "03_sam_two_pass.jpg"
    steps["sam"] = {
        "src": _jpg(_zoom(Image.open(tp), [b for r in sam.get("two_pass", [])
                                           for b in (r["spark_box"], r["pass2_box"])]),
                    out_dir / "sam_two_pass.jpg") if tp.exists() else None,
        "prompt_used": sam.get("chosen_for_classification"),
        "variants": {k: {"objects": len(v.get("objects", [])), "score": v.get("score")}
                     for k, v in sam["variants"].items()},
        "two_pass": [{"plume_id": r["plume_id"], "pass1_px": r["pass1"]["area_px"],
                      "pass2_px": r["pass2"].get("area_px", 0), "kept": r["kept"],
                      "reason": r["reason"]} for r in sam.get("two_pass", [])],
    }
    c = cls["context"]
    steps["classify"] = {
        "overlay": _jpg(run_dir / "overlay.png", out_dir / "overlay.jpg", width=1200),
        "per_plume": res.get("per_plume", []), "caveats": res.get("caveats"),
        "plumes": [{"plume_id": p["plume_id"], "label": p.get("spark_label"),
                    "area_km2": p["geometry"].get("area_km2"),
                    "length_km": p["geometry"].get("length_km"),
                    "upwind_end_distance_km": p["geometry"].get("upwind_end_distance_km"),
                    "nearest_fire_clusters": p["geometry"].get("nearest_fire_clusters"),
                    "land": p["geometry"].get("land")} for p in c.get("plumes", [])],
        "wind": c.get("wind_10m"),
        "firms": {"source": c["firms"].get("source"),
                  "fire_clusters": c["firms"].get("fire_clusters", c["firms"].get("clusters", []))[:6],
                  "volcanic_thermal_excluded": c["firms"].get("volcanic_thermal_excluded")},
        "volcano_status": c.get("volcano_status"),
    }
    trace_f = run_dir / "04_agent_trace.json"
    compare_f = run_dir / "04_compare.json"
    if trace_f.exists():
        tr = json.loads(trace_f.read_text())
        cmp_ = json.loads(compare_f.read_text()) if compare_f.exists() else {}
        steps["agent"] = {
            "used": cls.get("meta", {}).get("classifier") == "agent",
            "valid": tr.get("valid"), "rejected": tr.get("rejected"),
            "rounds": tr["meta"].get("rounds"), "cost_usd": tr["meta"].get("cost_usd"),
            "calls": [{"cite": t.get("cite"), "round": t["round"], "name": t["name"],
                       "arguments": json.loads(t["arguments"] or "{}"),
                       "ok": t["output"].get("ok"), "summary": _summarize_tool(t["name"], t["output"])}
                      for t in tr["trace"]],
            "compare": {k: (v.get("overall") or {}).get("class") if isinstance(v, dict) else None
                        for k, v in cmp_.items()},
        }
    else:
        steps["agent"] = {"used": False, "calls": []}
    alerts_dir = run_dir / "alerts"
    if (alerts_dir / "alerts.json").exists():
        al = json.loads((alerts_dir / "alerts.json").read_text())
        (out_dir / "cards").mkdir()
        items = []
        for a in al["alerts"]:
            card = alerts_dir / a["card"]
            items.append({k: a[k] for k in ("lang", "language", "headline", "summary",
                                            "confidence_label", "disclaimer", "disclaimer_en",
                                            "machine_translated", "needs_community_review",
                                            "official_source_url", "replay_banner",
                                            "replay_banner_en")}
                         | {"actions": [{"text": x["text"], "source_url": x["url"],
                                         "excerpt_en": x["excerpt_en"],
                                         "verbatim": bool(x.get("verbatim")),
                                         "label": x.get("label"),
                                         "publisher": HEALTH_PUBLISHERS.get(x["source_id"], x["source_id"]),
                                         "reviewed": bool(x.get("reviewed_override"))}
                                        for x in a["actions"]],
                            "card": "cards/" + _jpg(card, out_dir / "cards" / (card.stem + ".jpg"),
                                                    width=900, q=80) if card.exists() else None})
        steps["alerts"] = {"available": True, "mode": al["mode"], "places": al.get("places"),
                           "health_sources": al.get("health_sources"), "items": items}
    else:
        steps["alerts"] = {"available": False}

    doc = {
        "slug": out_dir.name, "case": case, "mode": mode, "run_id": run["run_id"],
        "title": TITLES.get(case, {"en": case, "vi": case}),
        "image_time": ctx0["image"]["time"], "layer": ctx0["image"]["layer"],
        "verdict": res.get("overall"), "detection": res.get("detection"),
        "cost_usd": run.get("cost_usd"), "models": MODELS_USED, "steps": steps,
    }
    (out_dir / "run.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--mode", choices=["replay", "live"])
    a = ap.parse_args()
    d = build(Path(a.run_dir), Path(a.out_dir), a.mode)
    print(f"{a.out_dir}: {d['case']} {d['mode']} verdict={d['verdict'] and d['verdict']['class']}")


if __name__ == "__main__":
    main()
