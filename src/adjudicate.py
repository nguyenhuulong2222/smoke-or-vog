"""Muse Wonder second opinion on borderline Spark agent verdicts.

Trigger (needs_second_opinion): the headline confidence is 0.55-0.75, or two plumes carry
conflicting hazardous classes. Wonder receives the SAME evidence bundle the Spark agent
gathered (FACTS + every tool output with its cite key, text only: Wonder has no vision) but
NOT Spark's verdict, and returns an independent cited verdict.

Combination rule (combine), safety first:
  * Wonder can never raise a verdict: the 0.70 bar is applied to Spark's own confidences.
  * Spark confirmed X and Wonder's class for that plume is also X -> X stands (Spark's confidence).
  * Spark confirmed X and Wonder says anything else -> the headline becomes "uncertain".
  * Spark confirmed nothing -> stays "uncertain" whatever Wonder says.

    .venv/bin/python -m src.adjudicate out/runs/<run_dir>     # re-adjudicate a saved agent run
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .aggregate import HAZARD_RANK, aggregate
from .common import _get, client, log_cost
from .models import CLASSES

WONDER = "muse-wonder-1.0"
WONDER_PER_M = {"input": 4.00, "output": 20.00}
BAND = (0.55, 0.75)
HAZARDOUS = {"wildfire_smoke", "vog_kilauea", "vog_mauna_loa"}

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "per_plume": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "plume_id": {"type": "integer"},
                "class": {"type": "string", "enum": CLASSES},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
                "cites": {"type": "array", "items": {"type": "string"}}},
            "required": ["plume_id", "class", "confidence", "reasoning", "cites"]}},
        "caveats": {"type": "string"}},
    "required": ["per_plume", "caveats"],
}


def headline_confidence(overall: dict) -> float:
    return overall["confidence"] if overall.get("plume_id") is not None \
        else overall.get("max_plume_confidence", 0.0)


def conflicting(per_plume: list[dict], floor: float = BAND[0]) -> bool:
    classes = {p["class"] for p in per_plume if p["class"] in HAZARDOUS and (p.get("confidence") or 0) >= floor}
    return len(classes) >= 2


def needs_second_opinion(per_plume: list[dict], overall: dict) -> str | None:
    """Reason string when Wonder should be consulted, else None."""
    if not per_plume:
        return None
    named = [p for p in per_plume if p["class"] != "uncertain"]
    hc = overall["confidence"] if overall.get("plume_id") is not None \
        else max((p.get("confidence") or 0 for p in named), default=0.0)
    if BAND[0] <= hc <= BAND[1]:
        return f"headline confidence {hc:.2f} is within {BAND[0]:.2f}-{BAND[1]:.2f}"
    if conflicting(per_plume):
        return "plumes carry conflicting hazardous classes"
    return None


def headline_plume(overall: dict) -> int | None:
    if overall.get("plume_id") is not None:
        return overall["plume_id"]
    un = overall.get("unconfirmed") or []
    return un[0]["plume_id"] if un else None


def combine(spark_per: list[dict], wonder_per: list[dict], unreliable: dict | None = None) -> dict:
    """Final overall + agreement record. Wonder can only keep or lower Spark's headline."""
    sp = aggregate(spark_per, unreliable=unreliable)
    pid = headline_plume(sp)
    spark_cls = next((p["class"] for p in spark_per if p["plume_id"] == pid), None)
    w = next((p for p in wonder_per if p["plume_id"] == pid), None)
    agrees = w is not None and w["class"] == spark_cls
    record = {"plume_id": pid, "spark_class": spark_cls,
              "spark_confidence": next((p["confidence"] for p in spark_per if p["plume_id"] == pid), None),
              "wonder_class": w["class"] if w else None, "wonder_confidence": w["confidence"] if w else None,
              "agrees": agrees,
              "per_plume": [{"plume_id": p["plume_id"], "spark_class": p["class"], "spark_confidence": p["confidence"],
                             "wonder_class": (wp := next((x for x in wonder_per if x["plume_id"] == p["plume_id"]), {})).get("class"),
                             "wonder_confidence": wp.get("confidence"),
                             "agrees": wp.get("class") == p["class"]} for p in spark_per]}
    if sp["plume_id"] is None or agrees:
        return {"overall": sp, "agreement": record}
    lowered = dict(sp)
    lowered.update({"class": "uncertain", "confidence": 0.0, "plume_id": None, "confirmed": [],
                    "max_plume_confidence": max((p.get("confidence") or 0 for p in spark_per), default=0.0),
                    "second_opinion_disagreed": True})
    demoted = [{**c, "not_confirmed_because": f"Muse Wonder second opinion: {record['wonder_class'] or 'no verdict'}"}
               for c in sp["confirmed"]]
    lowered["unconfirmed"] = sorted(demoted + sp["unconfirmed"],
                                    key=lambda b: (HAZARD_RANK.get(b.get("class"), 0), b.get("confidence") or 0),
                                    reverse=True)
    return {"overall": lowered, "agreement": record}


def bundle(facts: dict, trace: list[dict]) -> dict:
    """The Spark agent's evidence, minus its verdict."""
    return {"facts": facts,
            "tool_results": [{"cite": t["cite"], "tool": t["name"],
                              "arguments": json.loads(t["arguments"]) if isinstance(t["arguments"], str) else t["arguments"],
                              "output": t["output"]} for t in trace]}


def verify_cites(result: dict, trace: list[dict]) -> str | None:
    keys = {t["cite"] for t in trace if t["output"].get("ok", True) is not False}
    for p in result["per_plume"]:
        if not p["cites"] or not set(p["cites"]) <= keys:
            return f"plume {p['plume_id']}: cites {p['cites']} not all valid tool results"
    return None


def wonder_cost(usage) -> tuple[float, dict]:
    inp, out = _get(usage, "input_tokens"), _get(usage, "output_tokens")
    reasoning = _get(_get(usage, "output_tokens_details", None), "reasoning_tokens")
    return (inp * WONDER_PER_M["input"] + out * WONDER_PER_M["output"]) / 1e6, \
        {"input_tokens": inp, "cached_tokens": 0, "output_tokens": out, "reasoning_tokens": reasoning}


EFFORT = "low"


def second_opinion(run_id: str, facts: dict, trace: list[dict], plume_ids: list[int]) -> dict:
    prompt = (
        "You are an independent second reviewer of haze in a satellite image of the Hawaiian "
        "Islands. Another analyst gathered the evidence below with tools; you do NOT see their "
        "conclusion. Judge each plume (" + ", ".join(map(str, plume_ids)) + ") from the evidence "
        "alone and classify it as one of: " + ", ".join(CLASSES) + ". 'uncertain' is valid and "
        "preferred over a guess. Confidence is 0 to 1. Cite the tool results you rely on by "
        "their 'cite' keys (E1, E2, ...); a verdict with no valid citation is discarded. You "
        "cannot see the image, so the plume labels and scene description in FACTS are the only "
        "visual information. 'reasoning': at most three sentences. 'caveats': one sentence on "
        "the main limit of this evidence.\n\nEVIDENCE (JSON):\n" + json.dumps(bundle(facts, trace), ensure_ascii=False, default=str))
    r = client().responses.create(
        model=WONDER, input=prompt, reasoning={"effort": EFFORT},
        text={"format": {"type": "json_schema", "name": "second_opinion", "schema": SCHEMA, "strict": True}})
    cost, toks = wonder_cost(r.usage)
    log_cost("pipeline:wonder", r.model, cost, note=f"run={run_id}", **toks)
    try:
        res = json.loads(r.output_text)
    except Exception as e:  # noqa: BLE001
        return {"valid": False, "rejected": f"no JSON ({type(e).__name__})", "cost_usd": round(cost, 6)}
    reason = verify_cites(res, trace)
    return {"valid": reason is None, "rejected": reason, "result": res, "model": WONDER,
            "cost_usd": round(cost, 6), **toks}


def adjudicate(run_id: str, facts: dict, trace: list[dict], spark_per: list[dict],
               spark_overall: dict, unreliable: dict | None = None) -> dict | None:
    """None when no second opinion is needed; else the record to store with the run."""
    why = needs_second_opinion(spark_per, spark_overall)
    if not why:
        return None
    so = second_opinion(run_id, facts, trace, [p["plume_id"] for p in spark_per])
    rec = {"trigger": why, **{k: so.get(k) for k in ("valid", "rejected", "model", "cost_usd")},
           "wonder": so.get("result")}
    if so["valid"]:
        rec.update(combine(spark_per, so["result"]["per_plume"], unreliable))
    else:  # an invalid second opinion cannot confirm anything: treat as disagreement
        rec.update(combine(spark_per, [], unreliable))
    return rec


def rerun(run_dir: Path) -> dict | None:
    """Adjudicate a saved agent run in place (04_agent_trace.json + 04_classify.json)."""
    from . import land
    rd = Path(run_dir)
    tr = json.loads((rd / "04_agent_trace.json").read_text())
    cj = json.loads((rd / "04_classify.json").read_text())
    res, ctx = cj["result"], cj["context"]
    facts = tr.get("facts") or {"image_time": ctx["image"]["time"], "plumes": ctx["plumes"],
                                "spark_scene": ctx.get("spark_scene")}
    unrel = {p["plume_id"]: r for p in ctx["plumes"]
             if (r := land.unreliable_reason(p["geometry"].get("land", {})))}
    spark_ov = aggregate(res["per_plume"], unreliable=unrel)
    rec = adjudicate(rd.name, facts, tr["trace"], res["per_plume"], spark_ov, unrel)
    if rec is None:
        print("no second opinion needed:", spark_ov["class"], headline_confidence(spark_ov))
        return None
    (rd / "04_wonder.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    res["spark_overall"] = spark_ov
    res["overall"] = rec.get("overall", spark_ov)
    res["second_opinion"] = {k: rec.get(k) for k in ("trigger", "valid", "rejected", "agreement", "model", "cost_usd")}
    (rd / "04_classify.json").write_text(json.dumps(cj, indent=1, ensure_ascii=False))
    rj = rd / "run.json"
    if rj.exists():
        log = json.loads(rj.read_text())
        log.setdefault("classification", {})["overall"] = res["overall"]
        log["classification"]["second_opinion"] = res["second_opinion"]
        rj.write_text(json.dumps(log, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(res["second_opinion"], indent=1, ensure_ascii=False))
    return rec


if __name__ == "__main__":
    rerun(Path(sys.argv[1]))
