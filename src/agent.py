"""Agentic stage 4: Muse Spark gathers its own evidence with native tool calling.

Muse Spark sees the image and the segmented plumes, decides which tools to call
(and in what order), then classifies. Every evidence item must cite the call_id
of a tool result; a verdict that cites nothing (or cites unknown/failed calls) is
rejected and the pipeline falls back to the fixed classifier.

Tools (executed here, never by the model):
  get_wind(lat, lon, time_utc)                 Open-Meteo 10 m wind
  get_firms(bbox, date)                        FIRMS fires, summit glow split out
  get_volcano_status(time_utc)                 USGS HVO notice valid at that time
  distance_to_vents(plume_id, wind_from_deg?)  plume geometry from its SAM mask
  land_fraction(plume_id)                      Natural Earth land coverage of the mask
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from . import geo, land, sources
from .common import client, log_cost, spark_cost, to_data_url
from .models import CLASSES, SPARK

MAX_ROUNDS = 8
MAX_CALLS = 16

TOOLS = [
    {"type": "function", "name": "get_wind",
     "description": "10 m wind speed and direction (direction the wind blows FROM, degrees) at a "
                    "point and time, from Open-Meteo (forecast for recent times, ERA5 archive for past).",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {"lat": {"type": "number"}, "lon": {"type": "number"},
                                   "time_utc": {"type": "string", "description": "ISO 8601, e.g. 2023-08-08T21:00:00Z"}},
                    "required": ["lat", "lon", "time_utc"]}},
    {"type": "function", "name": "get_firms",
     "description": "NASA FIRMS satellite fire detections inside a lon/lat box on a date. Detections "
                    "inside the Kīlauea and Mauna Loa summit calderas are returned separately as "
                    "volcanic_thermal (summit glow), not as fires.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {"bbox": {"type": "array", "items": {"type": "number"},
                                            "description": "[west, south, east, north] in degrees"},
                                   "date": {"type": "string", "description": "YYYY-MM-DD (UTC)"}},
                    "required": ["bbox", "date"]}},
    {"type": "function", "name": "get_volcano_status",
     "description": "Official USGS Hawaiian Volcano Observatory status of Kīlauea and Mauna Loa "
                    "valid at a time: alert level, aviation color, erupting (yes/no/episodic_pause/"
                    "unknown), activity summary, notice link.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {"time_utc": {"type": "string"}}, "required": ["time_utc"]}},
    {"type": "function", "name": "distance_to_vents",
     "description": "Geometry of a segmented plume (from its SAM mask): centroid, extent, area, and "
                    "its upwind end given a wind direction, with distances from that end to the "
                    "Kīlauea and Mauna Loa summits.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {"plume_id": {"type": "integer"},
                                   "wind_from_deg": {"type": "number",
                                                     "description": "optional; direction wind blows from"}},
                    "required": ["plume_id"]}},
    {"type": "function", "name": "land_fraction",
     "description": "How much of a plume's mask lies over land, and which islands it covers "
                    "(Natural Earth 10m). A mask that swallows an island is unreliable.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {"plume_id": {"type": "integer"}}, "required": ["plume_id"]}},
]

FINAL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "class": {"type": "string", "enum": CLASSES},
        "confidence": {"type": "number"},
        "source_hint": {"type": "string"},
        "caveats": {"type": "string"},
        "per_plume": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "plume_id": {"type": "integer"},
                "class": {"type": "string", "enum": CLASSES},
                "confidence": {"type": "number"},
                "source_hint": {"type": "string"},
                "evidence": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {"text": {"type": "string"},
                                   "cites": {"type": "array", "items": {"type": "string"}}},
                    "required": ["text", "cites"]}},
            },
            "required": ["plume_id", "class", "confidence", "source_hint", "evidence"]}},
    },
    "required": ["class", "confidence", "source_hint", "caveats", "per_plume"],
}


class Toolbox:
    """Executes tool calls against real data for one run; validates every argument."""

    def __init__(self, run_dir: Path, plumes: list[dict], historical: bool, image_time: str):
        self.run_dir, self.historical, self.image_time = Path(run_dir), historical, image_time
        self.plumes = {p["plume_id"]: p for p in plumes}
        self._firms_cache: dict[str, dict] = {}

    @staticmethod
    def _time(s: str) -> datetime:
        s = s.strip()
        if len(s) == 10:
            s += "T21:00:00Z"
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)

    def _mask(self, pid: int):
        f = self.run_dir / f"plume_{pid}_mask.png"
        return Image.open(f).convert("L") if f.exists() else None

    def _plume(self, pid) -> dict:
        if not isinstance(pid, int) or pid not in self.plumes:
            raise ValueError(f"unknown plume_id {pid!r}; valid ids: {sorted(self.plumes)}")
        return self.plumes[pid]

    def get_wind(self, lat, lon, time_utc):
        lat, lon = float(lat), float(lon)
        if not (15 <= lat <= 25 and -165 <= lon <= -150):
            raise ValueError("point must be near Hawaiʻi (lat 15–25, lon -165 to -150)")
        when = self._time(time_utc)
        recent = (datetime.now(timezone.utc) - when).total_seconds() < 3 * 3600 and not self.historical
        w = sources.fetch_wind({"pt": (lat, lon)}, None if recent else when)
        return {**w["sites"]["pt"], "source": w["source"]}

    def get_firms(self, bbox, date):
        if not (isinstance(bbox, list) and len(bbox) == 4):
            raise ValueError("bbox must be [west, south, east, north]")
        w, s, e, n = map(float, bbox)
        date = str(date)[:10]
        key = "live" if not self.historical else date
        if key not in self._firms_cache:
            self._firms_cache[key] = (sources.fetch_firms_gibs(date) if self.historical
                                      else sources.fetch_firms_live())
        f = self._firms_cache[key]
        inside = [c for c in f["clusters"] if w <= c["lon"] <= e and s <= c["lat"] <= n]
        return {"source": f["source"], "fire_clusters": inside[:10],
                "volcanic_thermal": f.get("volcanic_thermal", {}), "note": f.get("note")}

    def get_volcano_status(self, time_utc):
        st = sources.fetch_volcano_status(self._time(time_utc))
        return {"source": st["source"], "valid_at": st["valid_at"], "volcanoes": {
            k: {kk: v.get(kk) for kk in ("alert_level", "aviation_color", "erupting",
                                          "activity_summary", "notice_sent_utc", "notice_url", "error")}
            for k, v in st["volcanoes"].items()}}

    def distance_to_vents(self, plume_id, wind_from_deg=None):
        from .pipeline import plume_geometry  # local import: pipeline imports this module

        p = self._plume(plume_id)
        m = self._mask(plume_id)
        if m is None:  # older runs: geometry computed from the mask at run time
            g = p["geometry"]
            return {"from": "stored mask geometry", **{k: g.get(k) for k in (
                "centroid", "bbox_lonlat", "area_km2", "length_km", "upwind_end",
                "upwind_end_distance_km")}}
        wf = float(wind_from_deg) if wind_from_deg is not None else None
        g = plume_geometry(m, wf)
        end = g.get("upwind_end") or g["centroid"]
        g.pop("upwind_end_px", None)
        g["distance_km"] = {n: round(geo.haversine_km(end["lat"], end["lon"], la, lo), 1)
                            for n, (la, lo) in geo.SOURCES.items()}
        g["wind_from_deg_used"] = wf
        return g

    def land_fraction(self, plume_id):
        p = self._plume(plume_id)
        m = self._mask(plume_id)
        return land.land_stats(m) if m is not None else p["geometry"].get("land", {})

    def call(self, name: str, args_json: str) -> dict:
        try:
            args = json.loads(args_json or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
            fn = {"get_wind": self.get_wind, "get_firms": self.get_firms,
                  "get_volcano_status": self.get_volcano_status,
                  "distance_to_vents": self.distance_to_vents,
                  "land_fraction": self.land_fraction}.get(name)
            if fn is None:
                raise ValueError(f"unknown tool {name}")
            return {"ok": True, "result": fn(**args)}
        except Exception as e:  # noqa: BLE001 - returned to the model as a tool error
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def verify_citations(final: dict, trace: list[dict]) -> str | None:
    """None if every plume has evidence citing successful tool calls, else the reason."""
    ok_ids = {t["cite"] for t in trace if t["output"].get("ok")}
    if not final.get("per_plume"):
        return "no per-plume verdicts"
    for p in final["per_plume"]:
        ev = p.get("evidence") or []
        cited = [c for e in ev for c in e.get("cites", [])]
        if not cited:
            return f"plume {p.get('plume_id')}: evidence cites no tool output"
        bad = [c for c in cited if c not in ok_ids]
        if bad:
            return f"plume {p.get('plume_id')}: cites unknown or failed tool calls {bad}"
        if any(not e.get("cites") for e in ev):
            return f"plume {p.get('plume_id')}: an evidence item has no citation"
    return None


def to_standard(final: dict) -> dict:
    """Shape the agent verdict like the fixed classifier's output (for aggregate/site)."""
    per = []
    for p in final["per_plume"]:
        per.append({"plume_id": p["plume_id"], "class": p["class"], "confidence": p["confidence"],
                    "source_hint": p["source_hint"],
                    "evidence": [f"{e['text']} [{', '.join(e['cites'])}]" for e in p["evidence"]],
                    "evidence_cited": p["evidence"]})
    return {"class": final["class"], "confidence": final["confidence"],
            "evidence": [e for p in per for e in p["evidence"]][:6],
            "source_hint": final["source_hint"], "per_plume": per, "caveats": final["caveats"]}


def classify_agentic(run_id: str, run_dir: Path, im: Image.Image, plumes: list[dict],
                     facts: dict, historical: bool, effort: str = "medium") -> dict:
    tb = Toolbox(run_dir, plumes, historical, facts["image_time"])
    prompt = (
        "You are classifying haze in a true-color satellite image of the Hawaiian Islands. "
        "Segmented plumes are listed below. Use the tools to gather the evidence YOU judge "
        "necessary (wind at the right places and time, fire detections near the plume's upwind "
        "end, the official volcano status at the image time, plume geometry and distance to the "
        "vents, land coverage of the mask), then classify each plume as one of: "
        + ", ".join(CLASSES) + ". Never force a class; 'uncertain' is valid. Confidence is 0 to 1.\n"
        "CITATION RULE: every tool result carries a 'cite_as' key such as \"E1\". Every "
        "evidence item must list in 'cites' the cite_as key(s) of the tool result(s) it relies "
        "on (a visual observation must still cite the tool output that supports the "
        "interpretation). Evidence without valid citations makes the verdict invalid.\n\n"
        "FACTS (JSON):\n" + json.dumps(facts, ensure_ascii=False)
    )
    c = client()
    trace: list[dict] = []
    totals = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
              "rounds": 0}
    common = {"model": SPARK, "tools": TOOLS, "reasoning": {"effort": effort},
              "text": {"format": {"type": "json_schema", "name": "agent_verdict",
                                  "schema": FINAL_SCHEMA, "strict": True}}}
    r = c.responses.create(input=[{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": prompt},
        {"type": "input_image", "image_url": to_data_url(im, "JPEG")}]}], **common)

    def account(resp):
        cost, toks = spark_cost(resp.usage)
        log_cost("pipeline:agent", resp.model, cost, note=f"run={run_id}; round={totals['rounds']}", **toks)
        totals["cost_usd"] += cost
        totals["rounds"] += 1
        for k in ("input_tokens", "output_tokens", "reasoning_tokens"):
            totals[k] += toks[k]

    account(r)
    while totals["rounds"] < MAX_ROUNDS:
        calls = [o for o in r.output if o.type == "function_call"]
        if not calls:
            break
        outputs = []
        for fc in calls:
            cite = f"E{len(trace) + 1}"
            if len(trace) >= MAX_CALLS:
                out = {"ok": False, "error": "tool-call budget exhausted; classify now"}
            else:
                out = tb.call(fc.name, fc.arguments)
            out = {"cite_as": cite, **out}
            trace.append({"round": totals["rounds"], "cite": cite, "call_id": fc.call_id,
                          "name": fc.name, "arguments": fc.arguments, "output": out})
            outputs.append({"type": "function_call_output", "call_id": fc.call_id,
                            "output": json.dumps(out, ensure_ascii=False, default=str)})
        r = c.responses.create(input=outputs, previous_response_id=r.id, **common)
        account(r)

    totals["cost_usd"] = round(totals["cost_usd"], 6)
    try:
        final = json.loads(r.output_text)
    except Exception as e:  # noqa: BLE001
        return {"valid": False, "rejected": f"no final JSON verdict ({type(e).__name__})",
                "trace": trace, "meta": totals, "final": None}
    reason = verify_citations(final, trace)
    return {"valid": reason is None, "rejected": reason, "trace": trace, "meta": totals,
            "final": final, "result": to_standard(final) if reason is None else None}
