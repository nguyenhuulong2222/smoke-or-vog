"""Meta Model API stages: Muse Spark localisation, SAM 3.1 segmentation,
Muse Spark classification. Request shapes follow dev.meta.ai/docs.
"""

from __future__ import annotations

import asyncio
import json

from PIL import Image

from meta_sam_parser import (
    FramePrompt, PromptBox, PromptObject, PromptPoint,
    build_object_prompt, decode_mask_to_raster, image_segmentation_format,
    parse_responses_stream,
)

from .common import SAM_PER_IMAGE, async_client, client, log_cost, spark_cost, to_data_url

SPARK = "muse-spark-1.3"
SAM = "sam-3.1"
CLASSES = ["vog_kilauea", "vog_mauna_loa", "wildfire_smoke", "dust", "cloud", "uncertain"]


def _spark_json(run_id: str, stage: str, content: list, schema: dict, name: str,
                effort: str = "medium") -> tuple[dict, dict]:
    r = client().responses.create(
        model=SPARK,
        input=[{"type": "message", "role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
        reasoning={"effort": effort},
    )
    cost, toks = spark_cost(r.usage)
    log_cost(f"pipeline:{stage}", r.model, cost, note=f"run={run_id}", **toks)
    return json.loads(r.output_text), {"model": r.model, "effort": effort,
                                       "cost_usd": round(cost, 6), **toks}


# ------------------------------------------------------------ stage 2: localise

_BOX = {"type": "object", "additionalProperties": False,
        "properties": {k: {"type": "integer"} for k in ("x_min", "y_min", "x_max", "y_max")},
        "required": ["x_min", "y_min", "x_max", "y_max"]}
_PT = {"type": "object", "additionalProperties": False,
       "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
       "required": ["x", "y"]}

LOCALIZE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "scene_description": {"type": "string"},
        "cloud_cover": {"type": "string", "enum": ["clear", "partly", "mostly", "overcast"]},
        "plumes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "label": {"type": "string"},
                "visual_description": {"type": "string"},
                "bbox": _BOX,
                "origin_point": _PT,
                "inside_point": _PT,
                "visibility": {"type": "string", "enum": ["clear", "faint", "very_faint"]},
            },
            "required": ["label", "visual_description", "bbox", "origin_point",
                         "inside_point", "visibility"]}},
    },
    "required": ["scene_description", "cloud_cover", "plumes"],
}


def spark_localize(run_id: str, im: Image.Image, hints: str) -> tuple[dict, dict]:
    prompt = (
        "You are an object grounding expert looking at a true-color satellite image of the "
        "main Hawaiian Islands (plate carrée, lon -161 to -154 left to right, lat 23 to 18 "
        "top to bottom). Find every visible haze, smoke, or volcanic plume. Do not miss any, "
        "but do not label ordinary white cumulus/cirrus cloud, sun glint, or open ocean as a "
        "plume. For each plume give a tight bounding box, the point where it appears to "
        "originate, and one point clearly inside the plume. The label must be a short neutral visual description (e.g. 'thin gray streak southwest of the large island'); do NOT name or guess a source (no 'vog', 'Kīlauea', 'fire', 'smoke') — attribution happens later. All coordinates on a 0-1000 grid "
        "with (0,0) at top-left, x to the right, y down. If there is no plume, return an "
        "empty list.\n\nContext (pixel positions on the same 0-1000 grid):\n" + hints
    )
    return _spark_json(run_id, "localize", [
        {"type": "input_text", "text": prompt},
        {"type": "input_image", "image_url": to_data_url(im, "JPEG")},
    ], LOCALIZE_SCHEMA, "plume_localization")


# ------------------------------------------------------------ stage 3: SAM

async def _sam_stream(im: Image.Image, text: str):
    c = async_client()
    stream = await c.responses.create(
        model=SAM,
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": text},
            {"type": "input_image", "image_url": to_data_url(im, "JPEG")},
        ]}],
        metadata={"include_confidence": "true"},
        stream=True,
    )
    usage = {}

    async def tee():
        async for ev in stream:
            if ev.type in ("response.completed", "response.incomplete"):
                u = getattr(ev.response, "usage", None)
                usage["images_processed"] = getattr(u, "images_processed", None)
            yield ev

    async with stream:
        parsed = parse_responses_stream(tee(), image_segmentation_format())
        async for _ in parsed:
            pass
        result = await parsed.final_result()
    await c.close()
    return result, usage


def sam_segment(run_id: str, im: Image.Image, label: str, text: str) -> dict:
    """Run one SAM request; return per-object full-frame masks + metadata."""
    try:
        result, usage = asyncio.run(_sam_stream(im, text))
    except Exception as e:  # noqa: BLE001
        log_cost("pipeline:sam", SAM, 0.0, status="error", note=f"run={run_id}; {label}; {e}")
        return {"label": label, "error": str(e)[:300], "objects": []}
    log_cost("pipeline:sam", SAM, SAM_PER_IMAGE, units="1 image",
             note=f"run={run_id}; {label}; outcome={result.outcome.status}")
    boxes = {r.object_id: r for r in result.records if r.kind == "box"}
    objects = []
    for rec in result.records:
        if rec.kind != "mask":
            continue
        raster = decode_mask_to_raster(rec.mask)
        m = Image.frombytes("L", (rec.mask.width, rec.mask.height),
                            bytes(v * 255 for v in raster))
        b = rec.bounds
        bw, bh = max(1, round(b.right - b.left)), max(1, round(b.bottom - b.top))
        if m.size != (bw, bh):
            m = m.resize((bw, bh), Image.NEAREST)
        full = Image.new("L", im.size, 0)
        full.paste(m, (round(b.left), round(b.top)))
        bx = boxes.get(rec.object_id)
        objects.append({
            "object_id": rec.object_id,
            "confidence": rec.confidence,
            "box": [bx.left, bx.top, bx.right, bx.bottom] if bx else None,
            "mask": full,
        })
    return {"label": label, "prompt": text if len(text) < 300 else text[:300] + "…",
            "outcome": result.outcome.status, "images_processed": usage.get("images_processed"),
            "diagnostics": [str(d) for d in result.diagnostics], "objects": objects}


def object_prompt(im: Image.Image, plumes_px: list[dict], with_points: bool) -> str:
    objs = []
    for i, p in enumerate(plumes_px, start=1):
        x1, y1, x2, y2 = p["box"]
        fp = FramePrompt(frame=0, box=PromptBox(x1, y1, x2 + 1, y2 + 1),
                         points=(PromptPoint(*p["inside"]),) if with_points else ())
        objs.append(PromptObject(id=i, prompts=[fp]))
    return build_object_prompt(size=im.size, objects=objs)


# ------------------------------------------------------------ stage 4: classify

CLASSIFY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "class": {"type": "string", "enum": CLASSES},
        "confidence": {"type": "number"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "source_hint": {"type": "string"},
        "per_plume": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "plume_id": {"type": "integer"},
                "class": {"type": "string", "enum": CLASSES},
                "confidence": {"type": "number"},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "source_hint": {"type": "string"},
            },
            "required": ["plume_id", "class", "confidence", "evidence", "source_hint"]}},
        "caveats": {"type": "string"},
    },
    "required": ["class", "confidence", "evidence", "source_hint", "per_plume", "caveats"],
}


def spark_classify(run_id: str, im: Image.Image, context: dict) -> tuple[dict, dict]:
    prompt = (
        "Classify the haze in this true-color satellite image of the Hawaiian Islands. "
        "Allowed classes: vog_kilauea, vog_mauna_loa, wildfire_smoke, dust, cloud, uncertain. "
        "Use the image AND the measured context below (plume geometry from segmentation, "
        "distance from each plume's upwind end to volcanic summits and to satellite fire "
        "detections, and 10 m wind). Reason from evidence: vog plumes are usually thin, "
        "bluish-gray, and trail downwind from an active summit vent; wildfire smoke trails "
        "downwind from fire detections away from the summits and is often browner; cloud is "
        "bright white with texture. Never force a class: if the evidence conflicts or is "
        "weak, use 'uncertain' and say why. Confidence is 0 to 1. 'class' is the overall "
        "answer for the dominant plume or 'uncertain'. Give per_plume entries using the "
        "plume ids from the context.\n\nCONTEXT (JSON):\n" + json.dumps(context, ensure_ascii=False)
    )
    return _spark_json(run_id, "classify", [
        {"type": "input_text", "text": prompt},
        {"type": "input_image", "image_url": to_data_url(im, "JPEG")},
    ], CLASSIFY_SCHEMA, "haze_classification")
