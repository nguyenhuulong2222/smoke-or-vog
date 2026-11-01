"""Ground monitors: Hawaiʻi SO2 and PM2.5 from the public AirNow hourly files (no key).

    .venv/bin/python -m src.groundtruth --start 2026-08-11 --end 2026-11-01

Downloads files.airnowtech.org/airnow/YYYY/YYYYMMDD/HourlyData_YYYYMMDDHH.dat (UTC) for the
18-03 UTC hours around the two daily scans, keeps Hawaiʻi (AQS state 15) SO2 / PM2.5 rows,
and writes data/raw/airnow/hi_hourly.csv plus data/raw/airnow/sites.json (coordinates).
"""

from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from .common import RAW

BASE = "https://files.airnowtech.org/airnow"
DIR = RAW / "airnow"
HOURS_UTC = list(range(18, 24)) + list(range(0, 4))   # around 21Z and 00Z scans (±3 h)
PARAMS = {"SO2", "PM2.5"}
UA = {"User-Agent": "smoke-or-vog/0.1 (Meta hackathon; contact long@kahuola.org)"}


def parse_hourly(text: str) -> list[dict]:
    """Rows of an AirNow HourlyData file -> Hawaiʻi SO2/PM2.5 observations (UTC)."""
    out = []
    for line in text.splitlines():
        f = line.split("|")
        if len(f) < 8 or not f[2].startswith("15") or f[5] not in PARAMS:
            continue
        try:
            t = datetime.strptime(f"{f[0]} {f[1]}", "%m/%d/%y %H:%M")
            v = float(f[7])
        except ValueError:
            continue
        if v < -50:  # AirNow missing-value sentinels
            continue
        out.append({"time_utc": t.strftime("%Y-%m-%dT%H:00Z"), "site": f[2], "name": f[3].strip(),
                    "param": f[5], "value": v})
    return out


def _fetch(day: date, hour: int) -> list[dict]:
    d = day + timedelta(days=1) if hour < 18 else day
    stamp = d.strftime("%Y%m%d")
    cache = DIR / "files" / f"{stamp}{hour:02d}.psv"
    if cache.exists():
        return parse_hourly(cache.read_text())
    r = requests.get(f"{BASE}/{d:%Y}/{stamp}/HourlyData_{stamp}{hour:02d}.dat", headers=UA, timeout=60)
    if r.status_code != 200:
        return []
    keep = "\n".join(l for l in r.text.splitlines() if "|15" in l)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(keep)
    return parse_hourly(keep)


def sites() -> dict:
    r = requests.get(f"{BASE}/today/monitoring_site_locations.dat", headers=UA, timeout=60)
    out = {}
    for line in r.text.splitlines():
        f = line.split("|")
        if len(f) > 10 and f[0].startswith("15"):
            try:
                out[f[0]] = {"name": f[3].strip(), "lat": float(f[8]), "lon": float(f[9])}
            except ValueError:
                continue
    return out


def download(start: date, end: date, workers: int = 8) -> Path:
    DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    d = start
    while d <= end:
        jobs += [(d, h) for h in HOURS_UTC]
        d += timedelta(days=1)
    rows: list[dict] = []
    with ThreadPoolExecutor(workers) as ex:
        for part in ex.map(lambda j: _fetch(*j), jobs):
            rows += part
    rows = list({(r["time_utc"], r["site"], r["param"]): r for r in rows}.values())
    rows.sort(key=lambda r: (r["time_utc"], r["site"], r["param"]))
    out = DIR / "hi_hourly.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["time_utc", "site", "name", "param", "value"])
        w.writeheader()
        w.writerows(rows)
    (DIR / "sites.json").write_text(json.dumps(sites(), indent=1, ensure_ascii=False))
    print(f"{len(jobs)} files, {len(rows)} observations -> {out}")
    return out


def load(path: Path | None = None) -> list[dict]:
    with (path or DIR / "hi_hourly.csv").open() as f:
        return [{**r, "value": float(r["value"])} for r in csv.DictReader(f)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-08-11")
    ap.add_argument("--end", default=date.today().isoformat())
    a = ap.parse_args()
    download(date.fromisoformat(a.start), date.fromisoformat(a.end))
