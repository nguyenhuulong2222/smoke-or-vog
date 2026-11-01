"""Hourly live scan + publish (run by .github/workflows/live.yml, server-side only).

    python -m src.live_publish --site-data site/data --persist live-data

1. Budget guard: if the hackathon total (all ledgers) >= --stop-at, publish nothing
   new and report status=budget_stop (the workflow then disables its schedule).
2. Daylight only (true-color analysis): outside 06:00-18:30 HST -> status=night.
3. Skip if the newest GOES-West GeoColor frame was already published -> unchanged.
4. Otherwise run the pipeline (no SAM concept prompts) and, only for a confirmed hazard,
   the 5-language alerts. Publish site/data/live/ and copy it to the persist dir.
The status and the last good run are always written to site/data/index.json.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import sitedata, sources
from .common import total_spend

HAZARDS = {"wildfire_smoke", "vog_kilauea", "vog_mauna_loa", "dust"}
DAY_START_HST, DAY_END_HST = (6, 0), (18, 30)


def is_daylight(now_utc: datetime) -> bool:
    hst = now_utc - timedelta(hours=10)
    return DAY_START_HST <= (hst.hour, hst.minute) <= DAY_END_HST


def set_output(status: str) -> None:
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a") as f:
            f.write(f"status={status}\n")


def write_index(site_data: Path, status: str, detail: str, spend: float) -> dict:
    replays = []
    for rj in sorted((site_data / "replays").glob("*/run.json")):
        d = json.loads(rj.read_text())
        replays.append({"slug": d["slug"], "path": f"replays/{d['slug']}", "title": d["title"],
                        "verdict": d["verdict"], "image_time": d["image_time"]})
    live_json = site_data / "live" / "run.json"
    live = None
    if live_json.exists():
        d = json.loads(live_json.read_text())
        live = {"path": "live", "title": d["title"], "verdict": d["verdict"],
                "detection": d.get("detection"), "image_time": d["image_time"]}
    idx = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "live_status": status, "live_status_detail": detail, "live": live,
           "replays": replays, "hackathon_spend_usd": round(spend, 2)}
    (site_data / "index.json").write_text(json.dumps(idx, indent=1, ensure_ascii=False))
    return idx


def restore_last(site_data: Path, persist: Path) -> None:
    src = persist / "live"
    dst = site_data / "live"
    if src.exists() and not dst.exists():
        shutil.copytree(src, dst)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-data", default="site/data")
    ap.add_argument("--persist", default="live-data")
    ap.add_argument("--stop-at", type=float, default=float(os.environ.get("SMOKEVOG_STOP_AT_USD", 15)))
    ap.add_argument("--force", action="store_true", help="ignore daylight/unchanged checks")
    ap.add_argument("--index-only", action="store_true",
                    help="only (re)write site/data/index.json from existing data; no API calls")
    a = ap.parse_args()
    site_data, persist = Path(a.site_data), Path(a.persist)
    site_data.mkdir(parents=True, exist_ok=True)
    persist.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    spend = total_spend()

    def finish(status: str, detail: str) -> None:
        restore_last(site_data, persist)
        write_index(site_data, status, detail, total_spend())
        set_output(status)
        print(f"live_publish: {status}: {detail} (spend ${total_spend():.4f})")

    if a.index_only:
        return finish("not_started" if not (site_data / "live").exists() else "ok", "index rebuilt")
    if spend >= a.stop_at:
        return finish("budget_stop", f"hackathon spend ${spend:.2f} >= ${a.stop_at:.2f}")
    if not a.force and not is_daylight(now):
        return finish("night", "outside daylight hours (true-color analysis needs daylight)")
    try:
        latest = sources.gibs_latest_time("GOES-West_ABI_GeoColor")
        last = persist / "live" / "run.json"
        if not a.force and last.exists() and json.loads(last.read_text())["image_time"] == latest:
            return finish("unchanged", f"no new GOES-West frame since {latest}")

        from . import alerts, pipeline

        run_dir = pipeline.run("live", concepts=False, classifier="agent",
                               track=os.environ.get("SMOKEVOG_TRACK") == "1")
        verdict = json.loads((run_dir / "04_classify.json").read_text())["result"]
        if verdict.get("overall", {}).get("class") in HAZARDS:
            alerts.run_alerts(run_dir)
        tmp = site_data / "live"
        sitedata.build(run_dir, tmp, mode="live")
        if (persist / "live").exists():
            shutil.rmtree(persist / "live")
        shutil.copytree(tmp, persist / "live")
        return finish("ok", f"scanned {latest}")
    except SystemExit as e:  # budget guard inside the pipeline
        return finish("budget_stop", str(e))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return finish("error", f"{type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    main()
