"""Stage 5: multilingual alerts + cards.

    python -m src.alerts out/runs/<run_id>

- Muse Spark writes one short alert in English, Vietnamese, Ilocano, Tagalog and
  ʻŌlelo Hawaiʻi for the run's overall verdict. Health actions must come ONLY
  from assets/health_sources.json: the model picks excerpts by index, and we
  attach the verbatim English excerpt + source URL to every action.
- Muse Image paints a text-free background; all text is rendered by PIL with
  Noto Sans (bundled, OFL), which covers Vietnamese diacritics and the Hawaiian
  ʻokina/kahakō.
- Output: <run>/alerts/alerts.json, background.png, alert_<lang>.png
"""

from __future__ import annotations

import base64
import re
import io
import json
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import geo
from .common import MUSE_IMAGE_PER_IMAGE, ROOT, check_budget, client, log_cost
from .models import _spark_json

ASSETS = ROOT / "assets"
FONT_REG = ASSETS / "fonts" / "NotoSans-Regular.ttf"
FONT_BOLD = ASSETS / "fonts" / "NotoSans-Bold.ttf"
HEALTH = json.loads((ASSETS / "health_sources.json").read_text())
OVERRIDES = json.loads((ASSETS / "translation_overrides.json").read_text())
MODES = ("live", "replay")
REPLAY_COLOR = (150, 40, 190)

LANGS = {"en": "English", "vi": "Vietnamese (Tiếng Việt)", "ilo": "Ilocano (Ilokano)",
         "tl": "Tagalog", "haw": "ʻŌlelo Hawaiʻi"}
NEEDS_REVIEW = {"ilo", "tl", "haw"}
VERDICTS = ["wildfire_smoke", "vog_kilauea", "vog_mauna_loa", "dust", "uncertain", "no_plume"]
DISCLAIMER_EN = "Satellite estimate, not an official warning."


HAWAIIAN_NAMES = ["Kaʻū", "Nāʻālehu", "Pāhala", "Pāhoa", "Kīlauea", "Kīhei", "Lānaʻi", "Molokaʻi",
                  "Oʻahu", "Kauaʻi", "Hawaiʻi", "Līhuʻe", "Kahoʻolawe", "Niʻihau", "Mokuʻāweoweo",
                  "Halemaʻumaʻu"]
_PLAIN = str.maketrans("āēīōūĀĒĪŌŪ", "aeiouAEIOU")


def fix_place_names(text: str) -> str:
    """Restore the official spelling of Hawaiian place names (ʻokina U+02BB, kahakō) when a
    model wrote them without diacritics or with an ASCII/curly apostrophe."""
    import re

    for name in HAWAIIAN_NAMES:
        base = name.translate(_PLAIN)
        variants = {base, base.replace("ʻ", "'"), base.replace("ʻ", "‘"), base.replace("ʻ", "’"),
                    base.replace("ʻ", ""), name.replace("ʻ", "'"), name.replace("ʻ", "‘"),
                    name.replace("ʻ", "’"), name.replace("ʻ", "")}
        for v in sorted(variants - {name}, key=len, reverse=True):
            # never touch a fully unmarked short form (e.g. "Kau" is also a Hawaiian word)
            if len(v) >= 3 and not (len(name) < 5 and "ʻ" not in v and v == v.translate(_PLAIN)
                                    and not any(c in v for c in "'‘’")):
                text = re.sub(rf"(?<![\wʻ']){re.escape(v)}(?![\wʻ'])", name, text)
    return text


_VI_VOG = re.compile(r"(?:vog \(sương mù núi lửa\)|sương mù núi lửa \(vog\)|khói mù núi lửa \(vog\)"
                     r"|khói mù núi lửa|sương mù núi lửa|\bvog\b)", re.IGNORECASE)


def normalize_vi_vog(texts: list[str]) -> list[str]:
    """Vietnamese vog terminology: the first mention across `texts` (in order) becomes
    'vog (sương mù núi lửa)', every later mention 'vog'. Sentence-initial capitals are kept."""
    seen = False
    out = []
    for text in texts:
        def sub(m):
            nonlocal seen
            rep_ = "vog" if seen else "vog (sương mù núi lửa)"
            seen = True
            return rep_[0].upper() + rep_[1:] if m.group(0)[0].isupper() else rep_
        out.append(_VI_VOG.sub(sub, text))
    return out


def vi_terms(a: dict) -> None:
    """Apply normalize_vi_vog to a Vietnamese alert in place (headline, summary, then
    machine-translated guidance lines). Reviewed translations are never changed."""
    parts = [a["headline"], a["summary"]] + [x["text"] for x in a["actions"] if not x.get("reviewed_override")]
    fixed = normalize_vi_vog(parts)
    a["headline"], a["summary"] = fixed[0], fixed[1]
    it = iter(fixed[2:])
    for x in a["actions"]:
        if not x.get("reviewed_override"):
            x["text"] = next(it)


def replay_banner_en(date_label: str) -> str:
    return f"REPLAY · {date_label} · not a current alert"


def date_label(image_time: str) -> str:
    d = datetime.fromisoformat((image_time if "T" in image_time else image_time + "T00:00:00Z")
                               .replace("Z", "+00:00"))
    return f"{d:%b} {d.day}, {d.year}"
CARD_W, CARD_H = 1200, 675
VERDICT_COLORS = {
    "wildfire_smoke": (200, 40, 30), "vog_kilauea": (230, 120, 0), "vog_mauna_loa": (200, 70, 130),
    "dust": (170, 130, 60), "uncertain": (90, 100, 115), "no_plume": (40, 120, 90),
}
BACKGROUND_PROMPTS = {
    "wildfire_smoke": "a Hawaiian island coastline under a sky with drifting gray-brown wildfire "
                      "smoke haze, distant hills, muted warm tones",
    "vog_kilauea": "a Hawaiian volcanic coastline with a thin pale blue-gray volcanic haze over "
                   "the ocean, soft light",
    "vog_mauna_loa": "a broad Hawaiian shield volcano under a thin pale blue-gray volcanic haze, "
                     "soft light",
    "dust": "a dry Hawaiian landscape under a pale tan dusty sky, soft light",
    "uncertain": "a Hawaiian coastline under a soft hazy overcast sky, calm, neutral tones",
    "no_plume": "a calm Hawaiian coastline with clear blue sky and a few light clouds",
}
NO_TEXT = ("Simple flat editorial illustration, wide landscape composition, large calm empty "
           "areas suitable for overlaying text. Absolutely no text, no letters, no words, no "
           "numbers, no signs, no logos, no watermarks, no people.")

PLACES = {  # place names kept in Hawaiian spelling
    "Kīlauea summit": (19.406, -155.283), "Volcano": (19.430, -155.234),
    "Pāhala (Kaʻū)": (19.203, -155.479), "Nāʻālehu (Kaʻū)": (19.065, -155.587),
    "Ocean View (Kaʻū)": (19.110, -155.770), "Pāhoa (Puna)": (19.494, -154.946),
    "Hilo": (19.707, -155.085), "Kailua-Kona": (19.640, -155.997), "Waimea": (20.023, -155.672),
    "Kohala": (20.230, -155.800), "Mauna Loa summit": (19.475, -155.608),
    "Lahaina (Maui)": (20.878, -156.677), "Kula (Maui)": (20.790, -156.326),
    "Kīhei (Maui)": (20.764, -156.445), "Kahului (Maui)": (20.889, -156.474),
    "Lānaʻi City": (20.828, -156.920), "Kaunakakai (Molokaʻi)": (21.090, -157.022),
    "Honolulu (Oʻahu)": (21.307, -157.858), "Līhuʻe (Kauaʻi)": (21.981, -159.371),
}


# ------------------------------------------------------------------ inputs

def verdict_of(cls_result: dict) -> tuple[str, float, int | None]:
    if cls_result.get("detection") == "no_plume":
        return "no_plume", 0.0, None
    ov = cls_result["overall"]
    return ov["class"], float(ov.get("confidence") or 0.0), ov.get("plume_id")


NEAR_KM = 15.0


def places_near_mask(mask: Image.Image, km: float = NEAR_KM, step: int = 4) -> list[str]:
    """Places within `km` of any plume pixel (mask sampled every `step` px)."""
    small = mask.resize((mask.width // step, mask.height // step), Image.NEAREST)
    px = small.load()
    pts = [geo.px_to_lonlat((x + 0.5) * step, (y + 0.5) * step)
           for y in range(small.height) for x in range(small.width) if px[x, y]]
    near = []
    for name, (lat, lon) in PLACES.items():
        if any(abs(plon - lon) < 0.3 and abs(plat - lat) < 0.3 and
               geo.haversine_km(lat, lon, plat, plon) <= km for plon, plat in pts):
            near.append(name)
    return near


def affected_places(plume: dict | None, mask: Image.Image | None = None,
                    margin_deg: float = 0.15) -> dict:
    """Places within NEAR_KM of the plume mask (or, without a saved mask, inside its
    lon/lat box + margin, which over-reaches for diagonal plumes), and the place
    nearest to its upwind end (source side)."""
    if not plume:
        return {"near": [], "source_side": None}
    g = plume["geometry"]
    if mask is not None:
        near, method = places_near_mask(mask), f"within {NEAR_KM:.0f} km of plume mask"
    else:
        w, s, e, n = g["bbox_lonlat"]
        near = [name for name, (lat, lon) in PLACES.items()
                if w - margin_deg <= lon <= e + margin_deg and s - margin_deg <= lat <= n + margin_deg]
        method = "plume bounding box + 0.15 deg (approximate)"
    ue = g.get("upwind_end") or g["centroid"]
    src = min(PLACES, key=lambda k: geo.haversine_km(ue["lat"], ue["lon"], *PLACES[k]))
    return {"near": near, "method": method, "source_side": src,
            "source_side_km": round(geo.haversine_km(ue["lat"], ue["lon"], *PLACES[src]))}


# ------------------------------------------------------------------ guidance (deterministic)

def guidance_for(verdict: str) -> list[dict]:
    """The curated official lines for a verdict, resolved verbatim from the source file.
    Depends ONLY on the verdict; no model is involved. Raises if a curated line is missing."""
    out = []
    for g in HEALTH["verdict_guidance"][verdict]:
        src = HEALTH["sources"][g["source_id"]]
        hits = [i for i, t in enumerate(src["excerpts"]) if t.startswith(g["starts_with"])]
        if len(hits) != 1:
            raise ValueError(f"curated guidance {g} matches {len(hits)} official lines (need exactly 1)")
        out.append({"source_id": g["source_id"], "index": hits[0],
                    "excerpt_en": src["excerpts"][hits[0]], "url": src["url"]})
    return out


# ------------------------------------------------------------------ Spark

def alerts_schema(verdict: str) -> dict:
    alert = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "lang": {"type": "string", "enum": list(LANGS)},
            "headline": {"type": "string"},
            "summary": {"type": "string"},
            "actions": {"type": "array", "items": {"type": "string"}},
            "disclaimer": {"type": "string"},
            "confidence_label": {"type": "string"},
            "replay_banner": {"type": "string"},
        },
        "required": ["lang", "headline", "summary", "actions", "disclaimer", "confidence_label",
                     "replay_banner"],
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {"alerts": {"type": "array", "items": alert}},
        "required": ["alerts"],
    }


def build_prompt(verdict: str, confidence: float, places: dict, when_hst: str,
                 unconfirmed: list[dict], mode: str = "live", replay_date: str = "") -> str:
    facts = {
        "mode": mode, "replay_date": replay_date if mode == "replay" else None,
        "verdict": verdict, "confidence": round(confidence, 2), "image_time_hst": when_hst,
        "areas_within_15km_of_detected_plume": places.get("near"),
        "unconfirmed_other_plumes": [{"class": u.get("class"), "confidence": u.get("confidence")}
                                     for u in unconfirmed],
    }
    return (
        "Write a short public air-quality alert for Hawaiʻi based on a SATELLITE ESTIMATE, in "
        "these languages: " + ", ".join(f"{k} = {v}" for k, v in LANGS.items()) + ". "
        "Return one alert per language (exactly 5).\n\n"
        "RULES\n"
        "1. Health guidance is fixed in advance and is never chosen or written by you. "
        "'actions' must hold the OFFICIAL GUIDANCE LINES below, in the same order, one per "
        "line: in English copy each line verbatim; in other languages give a faithful "
        "translation of each line, adding and removing nothing. If there are no lines, return "
        "an empty list. Do NOT write any health or medical advice anywhere else. The headline "
        "and summary only describe what the satellite shows, where and when.\n"
        "2. headline <= 60 characters; summary <= 200 characters. Guidance lines have NO length "
        "limit: translate each one completely, sentence by sentence, without shortening.\n"
        "3. Say what the satellite suggests and where, using the facts only. Never say the air is "
        "safe. Do not exaggerate. For 'uncertain', say the satellite could not confirm the haze "
        "source. For 'no_plume', say no haze plume was detected in the satellite image, which "
        "does not guarantee clean air.\n"
        "4. Keep Hawaiian place names exactly as written, with ʻokina (ʻ) and kahakō (ā ē ī ō ū).\n"
        "5. disclaimer = the sentence 'Satellite estimate, not an official warning.' translated "
        "into the alert's language. confidence_label = 'Confidence: N%' translated (N = "
        "confidence x 100, rounded).\n"
        "6. Vietnamese must use full diacritics. Ilocano, Tagalog and ʻŌlelo Hawaiʻi: write "
        "natural, simple sentences; they will be reviewed by community speakers.\n"
        "7. Glossary for Vietnamese: the first mention of vog is 'vog (sương mù núi lửa)', later "
        "mentions just 'vog'; wildfire smoke = 'khói cháy rừng'. Other languages may keep the "
        "word 'vog', which is widely used in Hawaiʻi.\n"
        "8. Mention only the areas listed in the facts; do not name other towns or regions.\n"
        "9. If mode is 'replay', this is a PAST event shown for demonstration: write the summary "
        "in the past tense, and set replay_banner = 'REPLAY · <replay_date> · not a current "
        "alert' translated into the alert's language (localize the date naturally). If mode is "
        "'live', set replay_banner to an empty string.\n\n"
        "FACTS (JSON):\n" + json.dumps(facts, ensure_ascii=False) + "\n\n"
        f"OFFICIAL GUIDANCE LINES (verbatim, in order; 'actions' must have exactly "
        f"{len(guidance_for(verdict))} item(s) in every language, one per line, never split "
        "or merged):\n"
        + json.dumps([g["excerpt_en"] for g in guidance_for(verdict)], ensure_ascii=False)
    )


def validate_spark_alerts(verdict: str, raw: dict) -> list[dict]:
    """Guidance comes from guidance_for(verdict) only. Checks the model returned exactly
    5 languages and one translated line per curated guidance line."""
    grounded = guidance_for(verdict)
    langs = [a["lang"] for a in raw["alerts"]]
    if sorted(langs) != sorted(LANGS):
        raise ValueError(f"languages {langs} != {list(LANGS)}")
    for a in raw["alerts"]:
        if a["lang"] == "en":
            continue  # English guidance is always the verbatim official text; model lines are discarded
        if len(a["actions"]) != len(grounded):
            raise ValueError(f"{a['lang']}: {len(a['actions'])} lines for {len(grounded)} guidance lines")
    return grounded


GUIDANCE_HEADING = "Official guidance (quoted)"
TRANSLATION_LABEL = "Translation of official guidance, machine-translated"
REVIEWED_LABEL = "Translation of official guidance, reviewed"


def apply_override(lang: str, g: dict, text: str) -> dict:
    """English guidance is always the verbatim official excerpt (model text is discarded).
    Other languages: the model's translation of that excerpt, or a reviewed override."""
    if lang == "en":
        return {"text": g["excerpt_en"], **g, "verbatim": True, "label": GUIDANCE_HEADING}
    o = OVERRIDES.get(lang, {}).get(f"{g['source_id']}#{g['index']}")
    if o:
        return {"text": o["text"], **g, "verbatim": False, "reviewed_override": True,
                "label": REVIEWED_LABEL, "model_text": unicodedata.normalize("NFC", text)}
    return {"text": unicodedata.normalize("NFC", text), **g, "verbatim": False,
            "label": TRANSLATION_LABEL}


def verify_guidance(doc: dict) -> None:
    """Raise unless every guidance line traces to assets/health_sources.json:
    English lines must equal the official excerpt verbatim; translations must point to an
    official excerpt and be labelled as translations. The AI never authors health advice."""
    expected = [(g["source_id"], g["index"]) for g in guidance_for(doc["verdict"])]
    for a in doc["alerts"]:
        allowed = set(HEALTH["verdict_sources"][doc["verdict"]])
        got = [(x.get("source_id"), x.get("index")) for x in a["actions"]]
        if got != expected:
            raise ValueError(f"{a['lang']}: guidance {got} differs from the curated lines for "
                             f"{doc['verdict']} {expected}")
        for act in a["actions"]:
            src = HEALTH["sources"].get(act.get("source_id"))
            idx = act.get("index")
            if act.get("source_id") not in allowed or src is None or not isinstance(idx, int) \
                    or not 0 <= idx < len(src["excerpts"]):
                raise ValueError(f"{a['lang']}: guidance line not traceable to an official source: {act}")
            excerpt = src["excerpts"][idx]
            if act.get("excerpt_en") != excerpt or act.get("url") != src["url"]:
                raise ValueError(f"{a['lang']}: excerpt/url does not match the source file")
            if a["lang"] == "en":
                if act.get("text") != excerpt or not act.get("verbatim"):
                    raise ValueError(f"en: guidance line is not the verbatim official text: {act.get('text')!r}")
            else:
                if act.get("verbatim") or act.get("label") not in (TRANSLATION_LABEL, REVIEWED_LABEL) \
                        or not act.get("text", "").strip():
                    raise ValueError(f"{a['lang']}: translation not labelled as such")


def assemble(run_id: str, verdict: str, confidence: float, places: dict, when_utc: str,
             raw: dict, grounded: list[dict], spark_meta: dict, *, mode: str) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    link = HEALTH["verdict_links"][verdict]
    banner_en = replay_banner_en(date_label(when_utc)) if mode == "replay" else ""
    alerts = []
    for code in LANGS:
        a = next(x for x in raw["alerts"] if x["lang"] == code)
        local_banner = unicodedata.normalize("NFC", a.get("replay_banner", "")).strip()
        alerts.append({
            "lang": code, "language": LANGS[code], "mode": mode,
            "replay_banner": (local_banner or banner_en) if mode == "replay" else "",
            "replay_banner_en": banner_en,
            "headline": fix_place_names(unicodedata.normalize("NFC", a["headline"])),
            "summary": fix_place_names(unicodedata.normalize("NFC", a["summary"])),
            "actions": [apply_override(code, g, t) for t, g in zip(a["actions"], grounded)],
            "confidence": round(confidence, 2),
            "confidence_label": a["confidence_label"],
            "disclaimer": a["disclaimer"], "disclaimer_en": DISCLAIMER_EN,
            "official_source_url": link,
            "machine_translated": code != "en",
            "needs_community_review": code in NEEDS_REVIEW,
            "card": f"alert_{code}.png",
        })
        if code == "vi":
            vi_terms(alerts[-1])
    return {"run_id": run_id, "mode": mode, "replay_banner_en": banner_en,
            "verdict": verdict, "confidence": round(confidence, 2),
            "image_time_utc": when_utc, "places": places,
            "official_source_url": link,
            "health_sources": [HEALTH["sources"][s]["url"] for s in HEALTH["verdict_sources"][verdict]],
            "generated_by": {"text": spark_meta, "background": "muse-image-1.0 (text-free)"},
            "alerts": alerts}


# ------------------------------------------------------------------ Muse Image

def background(verdict: str, run_id: str) -> Image.Image:
    check_budget(MUSE_IMAGE_PER_IMAGE)
    r = client().images.generate(
        model="muse-image-1.0", prompt=BACKGROUND_PROMPTS[verdict] + ". " + NO_TEXT, n=1,
        size="1536x1024", output_format="png",
        extra_body={"reasoning_strength": "low",
                    "tool_enablement": {"enable_web_search": False, "enable_image_search": False,
                                        "enable_shell": False}})
    log_cost("alerts:background", "muse-image-1.0", MUSE_IMAGE_PER_IMAGE, units="1 image",
             note=f"run={run_id}; verdict={verdict}")
    return Image.open(io.BytesIO(base64.b64decode(r.data[0].b64_json))).convert("RGB")


# ------------------------------------------------------------------ rendering

def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REG), size)


def wrap(draw: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=f) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def cover(im: Image.Image, w: int, h: int) -> Image.Image:
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


REPLAY_H = 64


def render_card(bg: Image.Image, alert: dict, verdict: str) -> Image.Image:
    mode = alert.get("mode")
    if mode not in MODES:
        raise ValueError(f"alert has no valid mode ({mode!r}); refusing to render")
    if mode == "replay" and not alert.get("replay_banner_en"):
        raise ValueError("replay alert without replay_banner_en; refusing to render")
    card = cover(bg, CARD_W, CARD_H).convert("RGBA")
    shade = Image.new("RGBA", card.size, (8, 12, 20, 165))
    card = Image.alpha_composite(card, shade)
    d = ImageDraw.Draw(card)
    color = VERDICT_COLORS[verdict]
    pad, inner = 48, CARD_W - 96
    top = 0
    if mode == "replay":
        d.rectangle([0, 0, CARD_W, REPLAY_H], fill=REPLAY_COLOR + (255,))
        en = alert["replay_banner_en"]
        local = alert.get("replay_banner") or en
        if alert["lang"] == "en" or local == en:
            d.text((pad, 14), en.upper(), font=font(28, True), fill=(255, 255, 255, 255))
        else:
            d.text((pad, 6), local.upper(), font=font(24, True), fill=(255, 255, 255, 255))
            d.text((pad, 38), en, font=font(17, True), fill=(235, 220, 245, 255))
        top = REPLAY_H
    d.rectangle([0, top, CARD_W, top + 12], fill=color + (255,))

    badges = []
    if alert["machine_translated"]:
        badges.append("MACHINE-TRANSLATED")
    if alert["needs_community_review"]:
        badges.append("NEEDS COMMUNITY REVIEW")
    bx = pad
    for b in badges:
        bf = font(16, True)
        tw = d.textlength(b, font=bf)
        d.rounded_rectangle([bx, top + 28, bx + tw + 20, top + 56], radius=6,
                            fill=(255, 210, 60, 255))
        d.text((bx + 10, top + 31), b, font=bf, fill=(20, 20, 20, 255))
        bx += tw + 32
    lang_f = font(16, True)
    lt = alert["language"].upper()
    d.text((CARD_W - pad - d.textlength(lt, font=lang_f), top + 31), lt, font=lang_f,
           fill=(220, 225, 235, 255))

    # Fit headline + summary + actions in the body area by shrinking fonts if needed.
    label = "" if not alert["actions"] else GUIDANCE_HEADING if alert["lang"] == "en" else \
        f"{GUIDANCE_HEADING} · {alert['actions'][0].get('label', TRANSLATION_LABEL)}"
    for scale in (1.0, 0.92, 0.85, 0.78, 0.72, 0.66, 0.6, 0.55):
        hf, sf, af = font(int(46 * scale), True), font(int(25 * scale)), font(int(23 * scale))
        lf = font(max(13, int(18 * scale)), True)
        hl = wrap(d, alert["headline"], hf, inner)
        sl = wrap(d, alert["summary"], sf, inner)
        al = [wrap(d, a["text"], af, inner - 30) for a in alert["actions"]]
        h = (len(hl) * hf.size * 1.18 + 14 + len(sl) * sf.size * 1.35 + 18 + lf.size * 1.5 +
             sum(len(x) * af.size * 1.32 + 8 for x in al))
        if h <= 400 - top:
            break
    y = 76 + top
    for line in hl:
        d.text((pad, y), line, font=hf, fill=(255, 255, 255, 255))
        y += hf.size * 1.18
    y += 14
    for line in sl:
        d.text((pad, y), line, font=sf, fill=(228, 232, 240, 255))
        y += sf.size * 1.35
    y += 18
    if label:
        d.text((pad, y), label, font=lf, fill=(255, 214, 102, 255))
        y += lf.size * 1.5
    for lines in al:
        d.ellipse([pad + 4, y + af.size * 0.45, pad + 14, y + af.size * 0.45 + 10], fill=color + (255,))
        for line in lines:
            d.text((pad + 30, y), line, font=af, fill=(245, 245, 245, 255))
            y += af.size * 1.32
        y += 8

    # Footer: confidence, disclaimer (localized + English), official link.
    fy = CARD_H - 132
    d.rectangle([0, fy - 14, CARD_W, CARD_H], fill=(0, 0, 0, 150))
    d.text((pad, fy), alert["confidence_label"], font=font(24, True), fill=color + (255,))
    disc = alert["disclaimer"] if alert["lang"] == "en" else f"{alert['disclaimer']}  ·  {DISCLAIMER_EN}"
    df = font(20, True)
    for line in wrap(d, disc, df, inner)[:2]:
        fy += 32
        d.text((pad, fy), line, font=df, fill=(255, 255, 255, 255))
    srcs = sorted({a["url"] for a in alert["actions"]}) or [alert["official_source_url"]]
    d.text((pad, CARD_H - 38), ("Guidance quoted from: " if alert["actions"] else "Official info: ")
           + ", ".join(srcs), font=font(17), fill=(190, 210, 255, 255))
    tag = "Khói hay vog? · ước tính vệ tinh" if alert["lang"] == "vi" else "Smoke or Vog? · satellite estimate"
    tf = font(16)
    d.text((CARD_W - pad - d.textlength(tag, font=tf), CARD_H - 36), tag, font=tf,
           fill=(170, 175, 185, 255))
    return card.convert("RGB")


# ------------------------------------------------------------------ run

def run_mode(run: dict) -> str:
    """'replay' for historical cases, 'live' otherwise. Unknown cases count as replay
    (the safe default: never present an old image as current)."""
    from .pipeline import CASES

    case = run.get("case") or run["run_id"].rsplit("_", 1)[0]
    cfg = CASES.get(case)
    return "live" if cfg is not None and not cfg["historical"] else "replay"


def run_alerts(run_dir: Path, effort: str = "medium") -> Path:
    run_dir = Path(run_dir)
    cls_file = json.loads((run_dir / "04_classify.json").read_text())
    run = json.loads((run_dir / "run.json").read_text())
    verdict, conf, pid = verdict_of(cls_file["result"])
    plume = next((p for p in cls_file["context"]["plumes"] if p["plume_id"] == pid), None)
    mask_path = run_dir / f"plume_{pid}_mask.png"
    places = affected_places(plume, Image.open(mask_path).convert("L") if mask_path.exists() else None)
    t = cls_file["context"]["image"]["time"]
    t_iso = t if "T" in t else t + "T21:00:00Z"
    when = datetime.fromisoformat(t_iso.replace("Z", "+00:00"))
    when_hst = (when - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M HST") if "T" in t \
        else when.strftime("%Y-%m-%d") + " (daily satellite pass)"
    unconfirmed = cls_file["result"].get("overall", {}).get("unconfirmed", [])
    mode = run_mode(run)

    out = run_dir / "alerts"
    out.mkdir(exist_ok=True)
    prompt = build_prompt(verdict, conf, places, when_hst, unconfirmed, mode, date_label(t))
    for attempt in (1, 2):  # one retry if a translation is misaligned with the fixed lines
        raw, meta = _spark_json(run["run_id"], "alerts", [{"type": "input_text", "text": prompt}],
                                alerts_schema(verdict), "multilingual_alerts", effort=effort)
        try:
            grounded = validate_spark_alerts(verdict, raw)
            break
        except ValueError as e:
            if attempt == 2:
                raise
            print(f"alerts: retrying ({e})")
    doc = assemble(run["run_id"], verdict, conf, places, t, raw, grounded, meta, mode=mode)

    bg_path = out / "background.png"
    if bg_path.exists():  # reuse: one text-free background per run
        bg = Image.open(bg_path).convert("RGB")
        bg_cost = 0.0
    else:
        bg = background(verdict, run["run_id"])
        bg.save(bg_path)
        bg_cost = MUSE_IMAGE_PER_IMAGE
    for a in doc["alerts"]:
        render_card(bg, a, verdict).save(out / a["card"])
    verify_guidance(doc)
    (out / "alerts.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    print(f"alerts: {out}  verdict={verdict} ({conf:.2f})  text ${meta['cost_usd']:.4f} + "
          f"background ${bg_cost:.2f}")
    return out


def rerender(run_dir: Path) -> Path:
    """Re-apply deterministic fixes and re-render cards from a saved alerts.json (no API calls)."""
    out = Path(run_dir) / "alerts"
    doc = json.loads((out / "alerts.json").read_text())
    for a in doc["alerts"]:
        a["headline"], a["summary"] = fix_place_names(a["headline"]), fix_place_names(a["summary"])
        if a["lang"] == "vi":
            vi_terms(a)
    verify_guidance(doc)
    bg = Image.open(out / "background.png").convert("RGB")
    for a in doc["alerts"]:
        render_card(bg, a, doc["verdict"]).save(out / a["card"])
    (out / "alerts.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--rerender":
        for rd in args[1:]:
            print("rerendered", rerender(Path(rd)))
    else:
        for rd in args:
            run_alerts(Path(rd))
