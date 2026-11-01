"""Live publisher guards and published site data (no credits)."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src import live_publish

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


@pytest.mark.parametrize("utc_hour,expected", [(16, True), (22, True), (4, True), (5, False), (15, False)])
def test_daylight_window(utc_hour, expected):
    assert live_publish.is_daylight(datetime(2026, 11, 1, utc_hour, 10, tzinfo=timezone.utc)) is expected


def run_main(monkeypatch, tmp_path, *args):
    monkeypatch.setattr("sys.argv", ["live_publish", "--site-data", str(tmp_path / "site"),
                                     "--persist", str(tmp_path / "persist"), *args])
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    live_publish.main()
    return out.read_text().strip(), json.loads((tmp_path / "site" / "index.json").read_text())


def test_budget_stop_never_runs_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(live_publish, "total_spend", lambda: 15.01)
    monkeypatch.setattr(live_publish.sources, "gibs_latest_time",
                        lambda *a: pytest.fail("must not touch imagery after budget stop"))
    status, idx = run_main(monkeypatch, tmp_path, "--stop-at", "15")
    assert status == "status=budget_stop" and idx["live_status"] == "budget_stop"


def test_night_skips_scan(monkeypatch, tmp_path):
    monkeypatch.setattr(live_publish, "total_spend", lambda: 1.0)
    monkeypatch.setattr(live_publish, "is_daylight", lambda now: False)
    monkeypatch.setattr(live_publish.sources, "gibs_latest_time",
                        lambda *a: pytest.fail("no scan at night"))
    status, idx = run_main(monkeypatch, tmp_path)
    assert status == "status=night"


def test_index_lists_committed_replays(monkeypatch, tmp_path):
    import shutil
    shutil.copytree(SITE / "data" / "replays", tmp_path / "site" / "replays")
    status, idx = run_main(monkeypatch, tmp_path, "--index-only")
    slugs = {r["slug"] for r in idx["replays"]}
    assert {"kilauea_20261017", "maui_20230808", "mauna_loa_20221201"} <= slugs


def test_replay_site_data_is_marked_replay_with_banners():
    for rj in (SITE / "data" / "replays").glob("*/run.json"):
        d = json.loads(rj.read_text())
        assert d["mode"] == "replay"
        if d["steps"]["alerts"]["available"]:
            for a in d["steps"]["alerts"]["items"]:
                assert a["replay_banner_en"].startswith("REPLAY · ")


def test_no_secrets_or_api_calls_in_site():
    for f in SITE.rglob("*"):
        if f.is_file() and f.suffix in {".html", ".js", ".json", ".css", ""}:
            text = f.read_text(errors="ignore")
            assert "LLM_" not in text and "MODEL_API_KEY" not in text, f
            assert "api.meta.ai" not in text, f
    js = (SITE / "app.js").read_text()
    # Only two network calls: published JSON, and the voice proxy Worker (key stays server-side).
    assert re.findall(r'fetch\(([^)]*)\)', js) == ["path, { cache: \"no-cache\" }", "VOICE_API, init"]
    assert 'const VOICE_API = "https://smoke-or-vog-voice.3ranknguyen.workers.dev/ask";' in js
    headers = (SITE / "_headers").read_text()
    assert "connect-src 'self' https://smoke-or-vog-voice.3ranknguyen.workers.dev;" in headers
    assert "microphone=(self)" in headers and "camera=()" in headers
