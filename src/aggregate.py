"""Overall verdict from per-plume classifications (safety rule).

The overall class is the MOST HAZARDOUS class among plumes classified with
confidence >= CONFIRM_THRESHOLD. Hazard order:
    wildfire_smoke > vog_kilauea = vog_mauna_loa > dust > cloud
Ties within a rank go to the higher confidence. Plumes below the threshold
(or classified "uncertain") are listed as unconfirmed. The overall verdict is
"uncertain" only when no plume reaches the threshold.

Data-quality gate: a plume whose segmentation is unreliable (e.g. the mask
swallowed an island or is mostly land, see land.py) cannot be confirmed, whatever
its confidence; it is listed as unconfirmed with the reason.
"""

from __future__ import annotations

CONFIRM_THRESHOLD = 0.70
HAZARD_RANK = {
    "wildfire_smoke": 4,
    "vog_kilauea": 3,
    "vog_mauna_loa": 3,
    "dust": 2,
    "cloud": 1,
    "uncertain": 0,
}


def aggregate(per_plume: list[dict], threshold: float = CONFIRM_THRESHOLD,
              unreliable: dict[int, str] | None = None) -> dict:
    """unreliable: {plume_id: reason} for plumes whose masks failed quality checks."""
    unreliable = unreliable or {}

    def brief(p: dict) -> dict:
        b = {"plume_id": p.get("plume_id"), "class": p.get("class"),
             "confidence": p.get("confidence"), "source_hint": p.get("source_hint")}
        if p.get("plume_id") in unreliable:
            b["not_confirmed_because"] = unreliable[p["plume_id"]]
        return b

    confirmed = [p for p in per_plume
                 if p.get("class") != "uncertain" and (p.get("confidence") or 0) >= threshold
                 and p.get("plume_id") not in unreliable]
    unconfirmed = [p for p in per_plume if p not in confirmed]
    confirmed.sort(key=lambda p: (HAZARD_RANK.get(p["class"], 0), p["confidence"]), reverse=True)
    unconfirmed.sort(key=lambda p: (HAZARD_RANK.get(p.get("class"), 0), p.get("confidence") or 0),
                     reverse=True)
    rule = (f"most hazardous class with confidence >= {threshold:.2f} "
            "(wildfire_smoke > vog_* > dust > cloud)")
    if not confirmed:
        return {"class": "uncertain", "confidence": 0.0,
                "max_plume_confidence": max((p.get("confidence") or 0 for p in per_plume),
                                            default=0.0),
                "plume_id": None, "rule": rule, "confirmed": [],
                "unconfirmed": [brief(p) for p in unconfirmed]}
    top = confirmed[0]
    return {"class": top["class"], "confidence": top["confidence"], "plume_id": top["plume_id"],
            "rule": rule, "confirmed": [brief(p) for p in confirmed],
            "unconfirmed": [brief(p) for p in unconfirmed]}
