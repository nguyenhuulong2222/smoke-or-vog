"""Smoke or Vog? detection chain.

    python -m src.pipeline --case live
    python -m src.pipeline --case kilauea_20261017
    python -m src.pipeline --case maui_20230808

Stages (each writes its output to out/runs/<case>_<UTC timestamp>/):
  0 imagery + context   true-color image on a fixed lon/lat grid, FIRMS, wind
  1 ADP signal          Kahu Ola smoke-sat mask -> candidate regions (live only)
  2 Spark localise      Muse Spark vision -> plume boxes / points (JSON)
  3 SAM 3.1             box, box+point, and concept prompts -> masks; scored
  4 Spark classify      vog_kilauea | vog_mauna_loa | wildfire_smoke | dust | cloud | uncertain
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import geo, land, models, sources
from .aggregate import aggregate
from .common import OUT, SAM_PER_IMAGE, check_budget, total_spend

CASES = {
    "live": {"layer": "GOES-West_ABI_GeoColor", "time": None, "historical": False},
    "kilauea_20261017": {"layer": "GOES-West_ABI_GeoColor", "time": "2026-10-17T21:00:00Z",
                         "historical": True},
    "maui_20230808": {"layer": "MODIS_Terra_CorrectedReflectance_TrueColor",
                      "time": "2023-08-08", "approx_utc": "2023-08-08T21:00:00Z",
                      "historical": True},
    "mauna_loa_20221201": {"layer": "MODIS_Aqua_CorrectedReflectance_TrueColor",
                           "time": "2022-12-01", "approx_utc": "2022-12-01T23:30:00Z",
                           "historical": True,
                           "note": "Mauna Loa NE rift eruption (Nov 27-Dec 10 2022); Kīlauea "
                                   "summit was also erupting until Dec 9 2022"},
}
CONCEPTS = ["smoke", "volcanic plume", "haze"]
RUN_COST_CAP = 0.50
CLASSIFY_EFFORT = "medium"
REFINE_MARGIN = 0.15
CLASS_COLORS = {
    "vog_kilauea": (255, 140, 0), "vog_mauna_loa": (255, 90, 160),
    "wildfire_smoke": (230, 40, 40), "dust": (200, 170, 90),
    "cloud": (120, 200, 255), "uncertain": (190, 190, 190),
}


def _font(size: int):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _save_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


# ------------------------------------------------------------------ metrics

def _mask_area(m: Image.Image) -> int:
    return m.histogram()[255] if m.mode == "L" else 0


def _union(masks: list[Image.Image], size) -> Image.Image:
    u = Image.new("L", size, 0)
    for m in masks:
        u = ImageChops.lighter(u, m)
    return u


def _boxes_mask(boxes: list[list[int]], size) -> Image.Image:
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for b in boxes:
        d.rectangle(b, fill=255)
    return m


def _overlap(a: Image.Image, b: Image.Image) -> int:
    return _mask_area(ImageChops.multiply(a, b))


def score_sam(res: dict, spark_boxes: list[list[int]], adp_mask, land_like: list[Image.Image],
              size) -> dict:
    masks = [o["mask"] for o in res["objects"]]
    u = _union(masks, size)
    area = _mask_area(u)
    sb = _boxes_mask(spark_boxes, size) if spark_boxes else None
    s = {"objects": len(masks), "mask_px": area,
         "mean_confidence": round(sum(o["confidence"] or 0 for o in res["objects"]) / len(masks), 3)
         if masks else None}
    if sb is not None and area:
        s["frac_inside_spark_boxes"] = round(_overlap(u, sb) / area, 3)
        s["spark_box_fill"] = round(_overlap(u, sb) / max(1, _mask_area(sb)), 3)
    if adp_mask is not None and area:
        inter, adp_a = _overlap(u, adp_mask), _mask_area(adp_mask)
        s["iou_vs_adp"] = round(inter / max(1, area + adp_a - inter), 3)
    return s


def plume_geometry(mask: Image.Image, wind_from_deg: float | None) -> dict:
    """Centroid, extent, area, and upwind end of a full-frame plume mask."""
    bbox = mask.getbbox()
    if not bbox:
        return {}
    px = mask.load()
    xs = ys = n = 0
    area_km2 = 0.0
    # Upwind direction unit vector in image space (x east, y south).
    if wind_from_deg is not None:
        ux, uy = math.sin(math.radians(wind_from_deg)), -math.cos(math.radians(wind_from_deg))
    best, best_pt = -1e18, None
    step = 2
    for y in range(bbox[1], bbox[3], step):
        lat = geo.px_to_lonlat(0, y)[1]
        a = geo.pixel_area_km2(lat) * step * step
        for x in range(bbox[0], bbox[2], step):
            if px[x, y]:
                xs += x
                ys += y
                n += 1
                area_km2 += a
                if wind_from_deg is not None:
                    proj = x * ux + y * uy
                    if proj > best:
                        best, best_pt = proj, (x, y)
    if not n:
        return {}
    cx, cy = xs / n, ys / n
    clon, clat = geo.px_to_lonlat(cx, cy)
    nlon, nlat = geo.px_to_lonlat(bbox[0], bbox[1])
    slon, slat = geo.px_to_lonlat(bbox[2], bbox[3])
    g = {"centroid": {"lat": round(clat, 3), "lon": round(clon, 3)},
         "bbox_lonlat": [round(nlon, 3), round(slat, 3), round(slon, 3), round(nlat, 3)],
         "area_km2": round(area_km2), "length_km": round(geo.haversine_km(nlat, nlon, slat, slon))}
    if best_pt:
        ulon, ulat = geo.px_to_lonlat(*best_pt)
        g["upwind_end"] = {"lat": round(ulat, 3), "lon": round(ulon, 3)}
        g["upwind_end_px"] = list(best_pt)
    return g


# ------------------------------------------------------------------ two-pass SAM

def refine_box(mask: Image.Image, margin: float = REFINE_MARGIN) -> list[int] | None:
    """Mask bounding box expanded by `margin` of its width/height on every side."""
    bb = mask.getbbox()
    if not bb:
        return None
    x1, y1, x2, y2 = bb[0], bb[1], bb[2] - 1, bb[3] - 1
    dx, dy = (x2 - x1 + 1) * margin, (y2 - y1 + 1) * margin
    return geo.Box(x1 - dx, y1 - dy, x2 + dx, y2 + dy).clip(*mask.size).as_list()


def mask_quality(mask: Image.Image) -> dict:
    """Area, coherence (largest component share), bbox share of frame, edge contact."""
    area = _mask_area(mask)
    if not area:
        return {"area_px": 0, "coherence": 0.0, "bbox_frac": 0.0, "edges_touched": 0}
    small = mask.resize((mask.width // 2, mask.height // 2), Image.NEAREST)
    comps = sources.components(small, min_px=1)
    total = sum(n for _, n in comps) or 1
    bb = mask.getbbox()
    w, h = mask.size
    edges = sum([bb[0] <= 0, bb[1] <= 0, bb[2] >= w, bb[3] >= h])
    return {"area_px": area, "coherence": round(comps[0][1] / total, 3) if comps else 0.0,
            "bbox_frac": round((bb[2] - bb[0]) * (bb[3] - bb[1]) / (w * h), 4),
            "edges_touched": edges}


def choose_pass(q1: dict, q2: dict, max_growth: float = 3.0, max_bbox_frac: float = 0.25,
                min_coherence: float = 0.85) -> tuple[str, str]:
    """Keep pass 2 only if it is larger, coherent, and shows no ocean-wide spill."""
    if not q2 or not q2.get("area_px"):
        return "pass1", "pass 2 returned no mask"
    if q2["area_px"] <= q1["area_px"] * 1.02:
        return "pass1", "pass 2 not larger"
    if q2["coherence"] < min_coherence:
        return "pass1", f"pass 2 fragmented (coherence {q2['coherence']})"
    if q2["area_px"] > q1["area_px"] * max_growth:
        return "pass1", f"pass 2 grew >{max_growth}x (spill)"
    if q2["bbox_frac"] > max_bbox_frac:
        return "pass1", f"pass 2 bbox covers {q2['bbox_frac']:.0%} of frame (spill)"
    if q2["edges_touched"] > max(1, q1["edges_touched"]):
        return "pass1", "pass 2 runs off multiple frame edges (spill)"
    return "pass2", f"pass 2 larger ({q2['area_px'] / max(1, q1['area_px']):.2f}x) and coherent"


# ------------------------------------------------------------------ overlay

def render_overlay(im: Image.Image, title: str, plumes: list[dict], spark_boxes, adp_mask,
                   firms_clusters, wind: dict, classification: dict | None) -> Image.Image:
    base = im.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f, fs = _font(18), _font(14)
    per = {p["plume_id"]: p for p in (classification or {}).get("per_plume", [])}
    if adp_mask is not None:
        tint = Image.new("RGBA", base.size, (255, 255, 0, 90))
        layer.paste(tint, (0, 0), adp_mask)
    for p in plumes:
        cls = per.get(p["plume_id"], {}).get("class", "uncertain")
        color = CLASS_COLORS.get(cls, (190, 190, 190))
        if (per.get(p["plume_id"], {}).get("confidence") or 0) < 0.70:
            cls = cls + "?"
        fill = Image.new("RGBA", base.size, color + (110,))
        layer.paste(fill, (0, 0), p["mask"])
        bb = p["mask"].getbbox()
        if bb:
            conf = per.get(p["plume_id"], {}).get("confidence")
            label = f"#{p['plume_id']} {cls}" + (f" {conf:.2f}" if conf is not None else "")
            if p.get("geometry", {}).get("land", {}).get("land_spill"):
                label += " [LAND SPILL]"
            d.text((bb[0] + 4, max(0, bb[1] - 20)), label, fill=color + (255,), font=f,
                   stroke_width=2, stroke_fill=(0, 0, 0, 255))
        ue = p.get("geometry", {}).get("upwind_end_px")
        if ue:
            d.ellipse([ue[0] - 5, ue[1] - 5, ue[0] + 5, ue[1] + 5], outline=(255, 255, 255, 255), width=2)
    for b in spark_boxes:
        d.rectangle(b, outline=(255, 255, 255, 200), width=1)
    for name, (lat, lon) in geo.SOURCES.items():
        x, y = geo.lonlat_to_px(lon, lat)
        d.polygon([(x, y - 9), (x - 8, y + 6), (x + 8, y + 6)], outline=(255, 255, 255, 255),
                  fill=(120, 0, 0, 255))
        w = wind.get("sites", {}).get(name)
        if w and w.get("from_deg") is not None:
            # Arrow points downwind (where air is going).
            ang = math.radians(w["from_deg"] + 180)
            L = 18 + w["speed_kmh"] * 1.5
            x2, y2 = x + L * math.sin(ang), y - L * math.cos(ang)
            d.line([(x, y), (x2, y2)], fill=(0, 255, 200, 255), width=3)
            d.text((x2 + 4, y2), f"{w['speed_kmh']:.0f} km/h", fill=(0, 255, 200, 255), font=fs,
                   stroke_width=2, stroke_fill=(0, 0, 0, 255))
    for c in firms_clusters[:15]:
        x, y = geo.lonlat_to_px(c["lon"], c["lat"])
        r = 4 + min(8, math.log2(1 + c["n"]))
        d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 30, 30, 255), width=3)
    out = Image.alpha_composite(base, layer)
    d = ImageDraw.Draw(out)
    head = title
    if classification:
        ov = classification.get("overall") or classification
        head += f"  |  verdict: {ov['class']} ({ov['confidence']:.2f})"
        unc = [u for u in classification.get("overall", {}).get("unconfirmed", [])]
        if unc:
            head += "  |  unconfirmed: " + ", ".join(
                f"#{u['plume_id']} {u['class']} {u['confidence']:.2f}" for u in unc)
    d.rectangle([0, 0, out.width, 30], fill=(0, 0, 0, 180))
    d.text((10, 5), head, fill=(255, 255, 255, 255), font=f)
    legend = ("triangle=summit  red ring=FIRMS fire  cyan=wind (downwind)  white box=Spark  "
              "yellow=ADP  white dot=plume upwind end")
    d.rectangle([0, out.height - 24, out.width, out.height], fill=(0, 0, 0, 180))
    d.text((10, out.height - 21), legend, fill=(230, 230, 230, 255), font=fs)
    return out.convert("RGB")


# ------------------------------------------------------------------ run

def run(case: str, classify_effort: str = CLASSIFY_EFFORT, concepts: bool = True) -> Path:
    cfg = CASES[case]
    check_budget(RUN_COST_CAP)
    spend_start = total_spend()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{case}_{stamp}"
    rd = OUT / "runs" / run_id
    rd.mkdir(parents=True, exist_ok=True)
    log = {"run_id": run_id, "case": case, "stages": {}}
    print(f"== {run_id}")

    # ---- stage 0: imagery + context
    t = cfg["time"] or sources.gibs_latest_time(cfg["layer"])
    im, img_meta = sources.fetch_imagery(cfg["layer"], t)
    im.save(rd / "00_image.jpg", quality=92)
    when = datetime.fromisoformat((cfg.get("approx_utc") or t).replace("Z", "+00:00"))
    if not cfg["historical"]:
        img_meta["star_reference"] = sources.fetch_star_latest()
    firms = sources.fetch_firms_gibs(t[:10]) if cfg["historical"] else sources.fetch_firms_live()
    wind_pts = dict(geo.SOURCES)
    for i, c in enumerate(firms["clusters"][:3]):
        wind_pts[f"fire_cluster_{i + 1}"] = (c["lat"], c["lon"])
    wind = sources.fetch_wind(wind_pts, None if not cfg["historical"] else when)
    volcano = sources.fetch_volcano_status(None if not cfg["historical"] else when)
    ctx0 = {"image": img_meta, "firms": firms, "wind": wind, "volcano_status": volcano}
    _save_json(rd / "00_context.json", ctx0)
    log["stages"]["0_context"] = {"image_time": t, "firms_clusters": len(firms["clusters"])}
    print(f"  0 image {cfg['layer']} @ {t}; FIRMS clusters {len(firms['clusters'])}; HVO " +
          ", ".join(f"{k}={v.get('alert_level')}/{v.get('aviation_color')}/{v.get('erupting')}"
                    for k, v in volcano["volcanoes"].items()))

    # ---- stage 1: ADP
    if cfg["historical"]:
        adp = {"state": "unavailable", "reason": "Kahu Ola ADP frames are live-only (historical keys 404)",
               "candidates": [], "mask": None}
    else:
        adp = sources.fetch_adp_live()
    adp_mask = adp.pop("mask", None)
    if adp_mask is not None:
        adp_mask.save(rd / "01_adp_mask.png")
    _save_json(rd / "01_adp.json", adp)
    log["stages"]["1_adp"] = {"state": adp.get("state"), "candidates": len(adp["candidates"])}
    print(f"  1 ADP state={adp.get('state')} candidates={len(adp['candidates'])}")

    # ---- stage 2: Spark localise
    hints = []
    for name, (lat, lon) in geo.SOURCES.items():
        x, y = geo.px_to_norm1000(*geo.lonlat_to_px(lon, lat))
        hints.append(f"- {name.replace('_', ' ')} at (x={x}, y={y})")
    for c in firms["clusters"][:6]:
        x, y = geo.px_to_norm1000(*geo.lonlat_to_px(c["lon"], c["lat"]))
        hints.append(f"- satellite fire detections near {c['near']} at (x={x}, y={y})")
    for zone, n in firms.get("volcanic_thermal", {}).items():
        hints.append(f"- active volcanic thermal signal (summit glow) in {zone}: {n} detections")
    for b in adp["candidates"]:
        x1, y1 = geo.px_to_norm1000(b[0], b[1])
        x2, y2 = geo.px_to_norm1000(b[2], b[3])
        hints.append(f"- aerosol (ADP) detection region box [{x1},{y1},{x2},{y2}]")
    if not adp["candidates"]:
        hints.append(f"- aerosol detection product: {adp.get('state')} (absence does not mean no haze)")
    loc, loc_meta = models.spark_localize(run_id, im, "\n".join(hints))
    plumes_px = []
    for p in loc["plumes"]:
        b = p["bbox"]
        x1, y1 = geo.norm1000_to_px(b["x_min"], b["y_min"])
        x2, y2 = geo.norm1000_to_px(b["x_max"], b["y_max"])
        box = geo.Box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)).clip().as_list()
        ix, iy = geo.norm1000_to_px(p["inside_point"]["x"], p["inside_point"]["y"])
        plumes_px.append({"label": p["label"], "box": box,
                          "inside": [min(max(0, round(ix)), im.width - 1),
                                     min(max(0, round(iy)), im.height - 1)]})
    _save_json(rd / "02_spark_localize.json", {"hints": hints, "result": loc, "pixels": plumes_px,
                                              "meta": loc_meta})
    spark_boxes = [p["box"] for p in plumes_px]
    log["stages"]["2_localize"] = {"plumes": len(plumes_px), **loc_meta}
    print(f"  2 Spark localise: {len(plumes_px)} plume(s), ${loc_meta['cost_usd']:.4f}")

    # ---- stage 3: SAM prompt styles
    concept_list = CONCEPTS if concepts else []
    planned = (2 if plumes_px else 0) + len(concept_list)
    check_budget(planned * SAM_PER_IMAGE)
    variants = []
    if plumes_px:
        variants.append(("box", models.object_prompt(im, plumes_px, with_points=False)))
        variants.append(("box+point", models.object_prompt(im, plumes_px, with_points=True)))
    variants += [(f"concept:{c}", c) for c in concept_list]
    sam_results, sam_summary = {}, {}
    for label, text in variants:
        res = models.sam_segment(run_id, im, label, text)
        sam_results[label] = res
        sc = score_sam(res, spark_boxes, adp_mask, [], im.size) if not res.get("error") else {}
        sam_summary[label] = {"prompt": res.get("prompt"), "outcome": res.get("outcome"),
                              "error": res.get("error"), "score": sc,
                              "objects": [{"object_id": o["object_id"], "confidence": o["confidence"],
                                           "box": o["box"], "mask_px": _mask_area(o["mask"])}
                                          for o in res["objects"]]}
        u = _union([o["mask"] for o in res["objects"]], im.size)
        tint = Image.new("RGBA", im.size, (255, 80, 80, 120))
        prev = im.convert("RGBA")
        prev.paste(tint, (0, 0), u)
        ImageDraw.Draw(prev).text((10, 8), f"SAM {label}: {sc.get('objects', 0)} obj",
                                  fill=(255, 255, 255, 255), font=_font(20),
                                  stroke_width=2, stroke_fill=(0, 0, 0, 255))
        prev.convert("RGB").save(rd / f"03_sam_{label.replace(':', '_').replace(' ', '_').replace('+', 'p')}.jpg",
                                 quality=88)
        print(f"  3 SAM {label:24s} -> {sc}")

    # Choose pass-1 masks: box+point if it produced masks, else box, else best concept.
    chosen = next((k for k in ("box+point", "box") if sam_results.get(k, {}).get("objects")), None)
    if chosen is None:
        concept_ok = [k for k in sam_results if k.startswith("concept") and sam_results[k]["objects"]]
        chosen = max(concept_ok, key=lambda k: sam_summary[k]["score"].get("frac_inside_spark_boxes", 0),
                     default=None)

    # ---- stage 3b: two-pass refinement (box prompts only)
    final_objs = list(sam_results[chosen]["objects"]) if chosen else []
    refine_log = []
    if chosen in ("box", "box+point"):
        p1 = {o["object_id"]: o for o in final_objs}
        pass2_px = []
        for i, pp in enumerate(plumes_px, start=1):
            o = p1.get(str(i))
            nb = refine_box(o["mask"]) if o else None
            pass2_px.append({**pp, "box": nb or pp["box"]})
        check_budget(SAM_PER_IMAGE)
        res2 = models.sam_segment(run_id, im, f"{chosen}:pass2",
                                  models.object_prompt(im, pass2_px, with_points=chosen == "box+point"))
        p2 = {o["object_id"]: o for o in res2["objects"]}
        final_objs = []
        before_after = im.convert("RGBA")
        d_ba = ImageDraw.Draw(before_after)
        for i in range(1, len(plumes_px) + 1):
            o1, o2 = p1.get(str(i)), p2.get(str(i))
            if not o1 and not o2:
                continue
            q1 = mask_quality(o1["mask"]) if o1 else {"area_px": 0, "edges_touched": 0}
            q2 = mask_quality(o2["mask"]) if o2 else {}
            if o1:
                q1["land"] = land.land_stats(o1["mask"])
            if o2:
                q2["land"] = land.land_stats(o2["mask"])
            pick, why = choose_pass(q1, q2) if o1 else ("pass2", "pass 1 had no mask")
            if pick == "pass2" and o1 and o2:
                spill = land.pass2_adds_land(q1["land"], q2["land"])
                if spill:
                    pick, why = "pass1", spill
            final_objs.append(o2 if pick == "pass2" else o1)
            refine_log.append({"plume_id": i, "spark_box": plumes_px[i - 1]["box"],
                               "pass2_box": pass2_px[i - 1]["box"], "pass1": q1, "pass2": q2,
                               "kept": pick, "reason": why})
            for o, col in ((o1, (255, 80, 80, 255)), (o2, (80, 220, 255, 255))):
                if o:
                    edge = o["mask"].filter(ImageFilter.FIND_EDGES)
                    before_after.paste(Image.new("RGBA", im.size, col), (0, 0), edge)
            d_ba.rectangle(pass2_px[i - 1]["box"], outline=(80, 220, 255, 200), width=1)
            d_ba.rectangle(plumes_px[i - 1]["box"], outline=(255, 255, 255, 200), width=1)
        ImageDraw.Draw(before_after).text(
            (10, 8), "red = pass 1 mask, cyan = pass 2 mask (box = mask bbox +15%)",
            fill=(255, 255, 255, 255), font=_font(20), stroke_width=2, stroke_fill=(0, 0, 0, 255))
        before_after.convert("RGB").save(rd / "03_sam_two_pass.jpg", quality=88)
        for r in refine_log:
            print(f"  3b plume {r['plume_id']}: pass1 {r['pass1']['area_px']} px -> "
                  f"pass2 {r['pass2'].get('area_px', 0)} px; kept {r['kept']} ({r['reason']})")
    _save_json(rd / "03_sam.json", {"variants": sam_summary, "chosen_for_classification": chosen,
                                    "two_pass": refine_log})
    log["stages"]["3_sam"] = {"chosen": chosen, "two_pass": [
        {k: r[k] for k in ("plume_id", "kept", "reason")} | {"pass1_px": r["pass1"]["area_px"],
                                                            "pass2_px": r["pass2"].get("area_px", 0)}
        for r in refine_log], "variants": {k: v["score"] for k, v in sam_summary.items()}}

    # ---- geometry for classification
    plumes = []
    for i, o in enumerate(final_objs, start=1):
        # Use the wind sample nearest to the plume's centroid for its upwind end.
        g0 = plume_geometry(o["mask"], None)
        if not g0:
            continue
        site = min(wind_pts, key=lambda n: geo.haversine_km(
            g0["centroid"]["lat"], g0["centroid"]["lon"], *wind_pts[n]))
        g = plume_geometry(o["mask"], wind["sites"].get(site, {}).get("from_deg"))
        g["wind_site_used"] = site
        if not g:
            continue
        ue = g.get("upwind_end") or g["centroid"]
        g["upwind_end_distance_km"] = {
            name: round(geo.haversine_km(ue["lat"], ue["lon"], lat, lon), 1)
            for name, (lat, lon) in geo.SOURCES.items()}
        g["nearest_fire_clusters"] = sorted(
            ({"near": c["near"], "n": c["n"], "nearest_summit_km": c.get("nearest_summit_km"),
              "distance_km": round(geo.haversine_km(ue["lat"], ue["lon"], c["lat"], c["lon"]), 1)}
             for c in firms["clusters"]), key=lambda c: c["distance_km"])[:3]
        label = plumes_px[int(o["object_id"]) - 1]["label"] if chosen in ("box", "box+point") \
            and o["object_id"].isdigit() and int(o["object_id"]) <= len(plumes_px) else chosen
        g["land"] = land.land_stats(o["mask"])
        o["mask"].save(rd / f"plume_{i}_mask.png", optimize=True)
        plumes.append({"plume_id": i, "spark_label": label, "sam_confidence": o["confidence"],
                       "geometry": g, "mask": o["mask"]})

    # ---- stage 4: classify
    cls_ctx = {
        "image": {"layer": cfg["layer"], "time": t},
        "spark_scene": {"description": loc["scene_description"], "cloud_cover": loc["cloud_cover"],
                        "plumes": [{"label": p["label"], "visual_description": p["visual_description"],
                                    "visibility": p["visibility"]} for p in loc["plumes"]]},
        "segmentation_prompt_used": chosen,
        "plumes": [{k: v for k, v in p.items() if k != "mask"} for p in plumes],
        "volcanic_summits": {k: {"lat": v[0], "lon": v[1]} for k, v in geo.SOURCES.items()},
        "firms": {"source": firms["source"], "fire_clusters": firms["clusters"][:8],
                  "note": firms.get("note"),
                  "volcanic_thermal_excluded": firms.get("volcanic_thermal"),
                  "volcanic_note": firms.get("volcanic_note")},
        "case_note": cfg.get("note"),
        "volcano_status": volcano,
        "wind_10m": wind,
        "adp": {k: adp.get(k) for k in ("state", "haze_pixels", "note", "meaning_of_absence")
                if k in adp},
    }
    for p in cls_ctx["plumes"]:
        p["geometry"].pop("upwind_end_px", None)
    if plumes or loc["plumes"]:
        cls, cls_meta = models.spark_classify(run_id, im, cls_ctx, effort=classify_effort)
    else:
        cls = {"detection": "no_plume", "class": "uncertain", "confidence": 0.0,
               "evidence": ["no plume localised by Muse Spark or segmented by SAM"],
               "source_hint": "none", "per_plume": [], "caveats": "No plume found; nothing to classify."}
        cls_meta = {"skipped": True, "cost_usd": 0}
    cls["model_overall_class"] = cls.pop("class")
    cls["model_overall_confidence"] = cls.pop("confidence")
    unreliable = {p["plume_id"]: r for p in plumes
                  if (r := land.unreliable_reason(p["geometry"].get("land", {})))}
    cls["overall"] = aggregate(cls["per_plume"], unreliable=unreliable)
    _save_json(rd / "04_classify.json", {"context": cls_ctx, "result": cls, "meta": cls_meta})
    log["stages"]["4_classify"] = {"overall": cls["overall"], **cls_meta}
    ov = cls["overall"]
    print(f"  4 classify: overall {ov['class']} ({ov['confidence']}); per plume " + ", ".join(
        f"#{p['plume_id']} {p['class']} {p['confidence']}" for p in cls["per_plume"]) +
        f"; ${cls_meta.get('cost_usd', 0):.4f}")

    # ---- overlay + summary
    title = f"Smoke or Vog? {case} | {cfg['layer']} {t}"
    ov = render_overlay(im, title, plumes, spark_boxes, adp_mask, firms["clusters"], wind, cls)
    ov.save(rd / "overlay.png")
    log["cost_usd"] = round(total_spend() - spend_start, 6)
    log["total_spend_usd"] = round(total_spend(), 4)
    log["classification"] = cls
    _save_json(rd / "run.json", log)
    print(f"  overlay: {rd / 'overlay.png'}   run cost ${log['cost_usd']:.4f}   "
          f"total ${log['total_spend_usd']:.4f}")
    return rd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=list(CASES), default="live")
    ap.add_argument("--no-concepts", action="store_true",
                    help="skip SAM concept prompts (they return nothing on satellite imagery)")
    ap.add_argument("--classify-effort", default=CLASSIFY_EFFORT,
                    choices=["minimal", "low", "medium", "high"])
    a = ap.parse_args()
    run(a.case, a.classify_effort, concepts=not a.no_concepts)


if __name__ == "__main__":
    main()
