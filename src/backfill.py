"""Backfill the GOES-West archive: 2 scans/day (11:00 and 14:00 HST) through the agent
pipeline with motion tracking. Separate ledger + budget; resumable.

    SMOKEVOG_COSTS_CSV=out/costs_backfill.csv .venv/bin/python -m src.backfill --workers 3

Each scan runs in its own process (python -m src.backfill --one <ISO time>), so one failure
never stops the batch. A scan is skipped if its run.json already exists.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "out" / "costs_backfill.csv"
RUNS = ROOT / "out" / "runs" / "backfill"
BUDGET_USD = 30.0
SLOTS_UTC = (21, 24)  # 21Z = 11:00 HST; next-day 00Z = 14:00 HST


def available_slots() -> list[str]:
    import requests

    x = requests.get("https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
                     params={"SERVICE": "WMS", "REQUEST": "GetCapabilities", "VERSION": "1.3.0"},
                     timeout=120).text
    m = re.search(r"<Name>GOES-West_ABI_GeoColor</Name>(.*?)</Layer>", x, re.S)
    iv = []
    for p in re.search(r'<Dimension name="time"[^>]*>([^<]*)<', m.group(1)).group(1).split(","):
        a, b, _ = p.split("/")
        iv.append((datetime.fromisoformat(a.replace("Z", "+00:00")),
                   datetime.fromisoformat(b.replace("Z", "+00:00"))))
    first, last = iv[0][0], iv[-1][1]
    out = []
    d = first.date()
    while d <= last.date():
        for hh in SLOTS_UTC:
            t = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(hours=hh)
            # need the 3 h tracking window too
            if t <= last and any(a <= t <= b and (t - a).total_seconds() % 600 == 0 for a, b in iv) \
                    and t - timedelta(hours=3) >= first:
                out.append(t.strftime("%Y-%m-%dT%H:%M:00Z"))
        d += timedelta(days=1)
    return out


def run_id_for(t: str) -> str:
    return f"goes_archive_{t.replace('-', '').replace(':', '')[:13]}Z"


def spent() -> float:
    if not LEDGER.exists():
        return 0.0
    import csv

    with LEDGER.open() as f:
        return sum(float(r["cost_usd"] or 0) for r in csv.DictReader(f))


def one(t: str) -> None:
    from . import pipeline

    pipeline.run("goes_archive", concepts=False, classifier="agent", track=True, at_time=t)


def worker(t: str) -> str:
    rd = RUNS / run_id_for(t)
    if (rd / "run.json").exists():
        return f"skip {t}"
    if spent() >= BUDGET_USD - 0.25:
        return f"budget stop before {t} (${spent():.2f})"
    env = {**os.environ, "SMOKEVOG_COSTS_CSV": str(LEDGER),
           "SMOKEVOG_EXTRA_LEDGERS": str(ROOT / "out" / "costs.csv")}
    log = RUNS / "logs"
    log.mkdir(parents=True, exist_ok=True)
    with open(log / f"{run_id_for(t)}.log", "w") as fh:
        r = subprocess.run([sys.executable, "-m", "src.backfill", "--one", t], cwd=ROOT, env=env,
                           stdout=fh, stderr=subprocess.STDOUT, timeout=1500)
    return f"{'ok' if r.returncode == 0 else 'FAIL'} {t} (${spent():.2f})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if a.one:
        return one(a.one)
    slots = available_slots()
    if a.limit:
        slots = slots[-a.limit:]
    print(f"{len(slots)} slots; backfill ledger ${spent():.2f} of ${BUDGET_USD:.0f}", flush=True)
    (RUNS).mkdir(parents=True, exist_ok=True)
    (RUNS / "slots.json").write_text(json.dumps(slots))
    with ThreadPoolExecutor(a.workers) as ex:
        for msg in ex.map(worker, slots[::-1]):  # newest first
            print(msg, flush=True)
    print(f"done; backfill ledger ${spent():.2f}", flush=True)


if __name__ == "__main__":
    main()
