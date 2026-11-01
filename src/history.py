"""Export backfill scans as lightweight site data + a day index for the History calendar.

    .venv/bin/python -m src.history [--out site/data/history]

Each archive scan -> <out>/<run_id>/ (sitedata, lite mode, marked "replay": it is a past
scan, never a current alert). <out>/index.json lists days with their headline verdict:
the most hazardous class confirmed (>= 0.70) across that day's scans, else "uncertain" if
any scan saw an unconfirmed plume, else "no_plume".
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import sitedata
from .aggregate import HAZARD_RANK
from .validate import RUNS, category

ROOT = Path(__file__).resolve().parent.parent


def day_headline(scans: list[dict]) -> str:
    """Most hazardous confirmed class among the day's scans; else uncertain/no_plume."""
    confirmed = [s["class"] for s in scans if s["category"] in ("vog", "smoke")]
    if confirmed:
        return max(confirmed, key=lambda c: HAZARD_RANK.get(c, 0))
    if any(s["category"] == "uncertain" for s in scans):
        return "uncertain"
    return "no_plume"


def export(out: Path, rebuild: bool = False) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    days: dict[str, list] = {}
    for rj in sorted(RUNS.glob("goes_archive_*/run.json")):
        rd = rj.parent
        cls = json.loads((rd / "04_classify.json").read_text())
        res = cls["result"]
        t = cls["context"]["image"]["time"]
        hst = datetime.fromisoformat(t.replace("Z", "+00:00")) - timedelta(hours=10)
        dst = out / rd.name
        if rebuild or not (dst / "run.json").exists():
            sitedata.build(rd, dst, mode="replay", lite=True)
        ov = res.get("overall") or {}
        days.setdefault(hst.strftime("%Y-%m-%d"), []).append({
            "time": t, "hst": hst.strftime("%H:%M"), "path": f"history/{rd.name}",
            "category": category(res), "class": "no_plume" if res.get("detection") == "no_plume" else ov.get("class"),
            "confidence": ov.get("confidence")})
    index = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "days": [{"date": d, "headline": day_headline(v), "scans": sorted(v, key=lambda s: s["time"])}
                      for d, v in sorted(days.items())]}
    (out / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False))
    return index


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "site" / "data" / "history"))
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    idx = export(Path(a.out), a.rebuild)
    from collections import Counter
    print(len(idx["days"]), "days", Counter(d["headline"] for d in idx["days"]))
