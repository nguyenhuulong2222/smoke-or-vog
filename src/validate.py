"""Validate backfill verdicts against ground monitors (rules in docs/VALIDATION.md).

    .venv/bin/python -m src.validate

Writes out/validation.json, site/data/validation.json and the Results section of
docs/VALIDATION.md. Every backfill scan is included; nothing is filtered by outcome.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from . import geo, groundtruth

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "out" / "runs" / "backfill"
NEAR_KM = 20.0
WINDOW_H = 3
DELTA_MIN = {"SO2": 5.0, "PM2.5": 5.0}
AQI_USG = {"SO2": 76.0, "PM2.5": 35.5}
POLLUTANT = {"vog": "SO2", "smoke": "PM2.5"}


# ------------------------------------------------------------------ pure helpers (tested)

def category(result: dict) -> str:
    if result.get("detection") == "no_plume":
        return "no_plume"
    c = (result.get("overall") or {}).get("class", "uncertain")
    return {"vog_kilauea": "vog", "vog_mauna_loa": "vog", "wildfire_smoke": "smoke"}.get(c, "uncertain")


def baselines(obs: list[dict]) -> dict:
    by = defaultdict(list)
    for o in obs:
        by[(o["site"], o["param"])].append(o["value"])
    out = {}
    for k, v in by.items():
        med = statistics.median(v)
        mad = statistics.median([abs(x - med) for x in v])
        out[k] = {"median": med, "mad": mad, "n": len(v)}
    return out


def threshold(base: dict, param: str) -> float:
    return base["median"] + max(DELTA_MIN[param], 3 * 1.4826 * base["mad"])


def is_elevated(values: list[float], base: dict, param: str) -> bool:
    if not values:
        return False
    m = max(values)
    return m >= threshold(base, param) or m >= AQI_USG[param]


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 3), round(min(1, c + h), 3)]


def stations_near_mask(mask: Image.Image, sites: dict, km: float = NEAR_KM, step: int = 3) -> list[str]:
    small = mask.resize((mask.width // step, mask.height // step), Image.NEAREST)
    px = small.load()
    pts = [geo.px_to_lonlat((x + 0.5) * step, (y + 0.5) * step)
           for y in range(small.height) for x in range(small.width) if px[x, y]]
    out = []
    for sid, s in sites.items():
        if any(abs(lo - s["lon"]) < 0.3 and abs(la - s["lat"]) < 0.3 and
               geo.haversine_km(s["lat"], s["lon"], la, lo) <= km for lo, la in pts):
            out.append(sid)
    return out


def window_values(index: dict, site: str, param: str, t: datetime) -> list[float]:
    vals = []
    for h in range(-WINDOW_H, WINDOW_H + 1):
        k = (site, param, (t + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00Z"))
        if k in index:
            vals.append(index[k])
    return vals


# ------------------------------------------------------------------ main

def load_scans() -> list[dict]:
    scans = []
    for rj in sorted(RUNS.glob("goes_archive_*/run.json")):
        rd = rj.parent
        cls = json.loads((rd / "04_classify.json").read_text())
        res = cls["result"]
        t = cls["context"]["image"]["time"]
        pid = (res.get("overall") or {}).get("plume_id")
        masks = sorted(rd.glob("plume_*_mask.png"))
        scans.append({"run": rd.name, "time": t, "category": category(res),
                      "class": (res.get("overall") or {}).get("class"),
                      "confidence": (res.get("overall") or {}).get("confidence"),
                      "headline_mask": rd / f"plume_{pid}_mask.png" if pid else None,
                      "masks": masks})
    return scans


def evaluate(scans: list[dict], obs: list[dict], sites: dict) -> dict:
    base = baselines(obs)
    index = {(o["site"], o["param"], o["time_utc"]): o["value"] for o in obs}
    rows = []
    for s in scans:
        t = datetime.fromisoformat(s["time"].replace("Z", "+00:00")).replace(tzinfo=None)
        cat = s["category"]
        if cat in ("vog", "smoke") and s["headline_mask"] and s["headline_mask"].exists():
            near = stations_near_mask(Image.open(s["headline_mask"]).convert("L"), sites)
        elif cat == "uncertain" and s["masks"]:
            near = sorted({sid for m in s["masks"]
                           for sid in stations_near_mask(Image.open(m).convert("L"), sites)})
        else:
            near = list(sites)
        el = {}
        for param in ("SO2", "PM2.5"):
            reporting = [sid for sid in near if (sid, param) in base
                         and window_values(index, sid, param, t)]
            el[param] = {"stations": reporting,
                         "elevated": [sid for sid in reporting
                                      if is_elevated(window_values(index, sid, param, t), base[(sid, param)], param)]}
        rows.append({"run": s["run"], "time": s["time"], "category": cat, "class": s["class"],
                     "confidence": s["confidence"], "near": near, "ground": el})

    def rate(subset, param, want_elevated=True):
        cov = [r for r in subset if r["ground"][param]["stations"]]
        k = sum(1 for r in cov if bool(r["ground"][param]["elevated"]) == want_elevated)
        return {"scans": len(subset), "covered": len(cov), "no_coverage": len(subset) - len(cov),
                "agree": k, "rate": round(k / len(cov), 3) if cov else None, "ci95": wilson(k, len(cov))}

    by = defaultdict(list)
    for r in rows:
        by[r["category"]].append(r)
    table = {}
    for cat, param in POLLUTANT.items():
        table[cat] = {"pollutant": param, **rate(by[cat], param)}
        # base rate: same stations, all OTHER scans
        others = [r for r in rows if r["category"] != cat]
        k = n = 0
        for r in by[cat]:
            for o in others:
                t = datetime.fromisoformat(o["time"].replace("Z", "+00:00")).replace(tzinfo=None)
                st = [sid for sid in r["ground"][param]["stations"] if window_values(index, sid, param, t)]
                if st:
                    n += 1
                    k += any(is_elevated(window_values(index, sid, param, t), base[(sid, param)], param) for sid in st)
        table[cat]["base_rate"] = round(k / n, 3) if n else None
    nop = by["no_plume"]
    cov = [r for r in nop if r["ground"]["SO2"]["stations"] or r["ground"]["PM2.5"]["stations"]]
    clean = [r for r in cov if not r["ground"]["SO2"]["elevated"] and not r["ground"]["PM2.5"]["elevated"]]
    table["no_plume"] = {"scans": len(nop), "covered": len(cov), "agree": len(clean),
                         "rate": round(len(clean) / len(cov), 3) if cov else None,
                         "ci95": wilson(len(clean), len(cov))}
    unc = by["uncertain"]
    table["uncertain"] = {
        "scans": len(unc),
        "so2_elevated": sum(1 for r in unc if r["ground"]["SO2"]["elevated"]),
        "pm25_elevated": sum(1 for r in unc if r["ground"]["PM2.5"]["elevated"]),
        "neither": sum(1 for r in unc if not r["ground"]["SO2"]["elevated"] and not r["ground"]["PM2.5"]["elevated"]),
        "covered": sum(1 for r in unc if r["ground"]["SO2"]["stations"] or r["ground"]["PM2.5"]["stations"])}
    return {"scans": len(rows), "table": table, "rows": rows,
            "baselines": {f"{k[0]}|{k[1]}": v for k, v in base.items()},
            "sites": {sid: s["name"] for sid, s in sites.items()},
            "method": "docs/VALIDATION.md (pre-registered)"}


def write_results(res: dict) -> None:
    out = ROOT / "out" / "validation.json"
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    site = {k: res[k] for k in ("scans", "table", "method")}
    site["days"] = {}
    for r in res["rows"]:
        hst_day = (datetime.fromisoformat(r["time"].replace("Z", "+00:00")) - timedelta(hours=10)).strftime("%Y-%m-%d")
        site["days"].setdefault(hst_day, []).append(
            {"time": r["time"], "category": r["category"], "class": r["class"], "run": r["run"],
             "so2_elevated": [res["sites"].get(s, s) for s in r["ground"]["SO2"]["elevated"]],
             "pm25_elevated": [res["sites"].get(s, s) for s in r["ground"]["PM2.5"]["elevated"]]})
    (ROOT / "site" / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "site" / "data" / "validation.json").write_text(json.dumps(site, indent=1, ensure_ascii=False))
    T = res["table"]

    def fmt(x):
        if x.get("rate") is None:
            return "n/a (no monitor coverage)"
        lo, hi = x["ci95"]
        return f"**{x['agree']}/{x['covered']}** ({x['rate']:.0%}, 95% CI {lo:.0%}–{hi:.0%})"
    md = [f"Computed {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC over **{res['scans']} scans**.\n",
          "| Verdict | Scans | With monitor coverage | Agreement | Base rate (same stations, other scans) |",
          "|---|---|---|---|---|"]
    for cat, label in (("vog", "Vog → SO₂ elevated"), ("smoke", "Smoke → PM2.5 elevated")):
        x = T[cat]
        br = f"{x['base_rate']:.0%}" if x.get("base_rate") is not None else "n/a"
        md.append(f"| {label} | {x['scans']} | {x['covered']} | {fmt(x)} | {br} |")
    x = T["no_plume"]
    md.append(f"| No plume → clean air | {x['scans']} | {x['covered']} | {fmt(x)} | — |")
    u = T["uncertain"]
    md += ["", f"**Uncertain** ({u['scans']} scans, {u['covered']} with coverage): SO₂ elevated in "
               f"{u['so2_elevated']}, PM2.5 elevated in {u['pm25_elevated']}, neither in {u['neither']}.",
           "", "Per-scan details: `out/validation.json` (site copy: `site/data/validation.json`)."]
    doc = ROOT / "docs" / "VALIDATION.md"
    text = doc.read_text()
    head = text.split("## Results")[0]
    doc.write_text(head + "## Results\n\n" + "\n".join(md) + "\n")
    print("\n".join(md))


def main() -> None:
    obs = groundtruth.load()
    sites = json.loads((groundtruth.DIR / "sites.json").read_text())
    reporting = {o["site"] for o in obs}
    sites = {k: v for k, v in sites.items() if k in reporting}
    write_results(evaluate(load_scans(), obs, sites))


if __name__ == "__main__":
    main()
