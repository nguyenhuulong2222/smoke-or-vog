"""Plume motion tracking: math, frame handling, unavailable paths, agent tool (no credits)."""

import json
import math

import pytest
from PIL import Image

from src import agent, track


def test_bearing_cardinal_directions():
    assert round(track.bearing_deg(19, -155, 20, -155)) == 0
    assert round(track.bearing_deg(19, -155, 19, -154)) == 90
    assert round(track.bearing_deg(19, -155, 18, -155)) == 180
    assert round(track.bearing_deg(19, -155, 19, -156)) == 270


def test_fit_motion_recovers_known_drift():
    # 3 h of centroids drifting 12 km/h toward 210° (SSW), with small noise
    pts = []
    for i in range(19):
        th = -3 + i / 6
        d = 12 * th
        dn, de = d * math.cos(math.radians(210)), d * math.sin(math.radians(210))
        lat = 18.6 + dn / 111.32 + (0.002 if i % 3 == 0 else -0.001)
        lon = -155.7 + de / (111.32 * math.cos(math.radians(18.6)))
        pts.append((th, lat, lon))
    m = track.fit_motion(pts)
    assert abs(m["speed_kmh"] - 12) < 1.0
    assert track.angle_diff(m["toward_deg"], 210) < 3
    assert m["r2"] > 0.95 and m["n"] == 19


def test_fit_motion_needs_enough_points():
    assert track.fit_motion([(0, 18, -155), (1, 18.1, -155)]) is None


@pytest.mark.parametrize("track_toward,wind_from,label", [(214, 30, "agrees"), (214, 71, "agrees"), (214, 100, "partly"),
                                                         (30, 30, "disagrees")])
def test_wind_agreement(track_toward, wind_from, label):
    assert track.wind_agreement(track_toward, wind_from)["label"] == label


def test_blank_frame_detection():
    assert track.is_blank(Image.new("RGB", (140, 100), (0, 0, 0)))
    assert not track.is_blank(Image.new("RGB", (140, 100), (20, 60, 90)))


def test_encode_one_video_frame_per_image(tmp_path):
    frames = []
    for i in range(7):
        f = tmp_path / f"f{i}.png"
        Image.new("RGB", (140, 100), (10 * i, 40, 90)).save(f)
        frames.append(f)
    assert track.encode_mp4(frames, tmp_path / "clip.mp4") == 7


def test_modis_and_no_plume_are_unavailable(tmp_path):
    out = track.track_run(tmp_path, "2023-08-08", "MODIS_Terra_CorrectedReflectance_TrueColor",
                          [{"plume_id": 1, "box": [1, 1, 9, 9]}], "t")
    assert out == {"available": False, "reason": track.UNAVAILABLE}
    assert json.loads((tmp_path / "05_track.json").read_text())["available"] is False
    out = track.track_run(tmp_path, "2026-10-17T21:00:00Z", "GOES-West_ABI_GeoColor", [], "t")
    assert out["available"] is False and "no plume" in out["reason"]


def test_source_end_is_against_the_drift():
    m = Image.new("L", (100, 100), 0)
    m.paste(255, (20, 40, 80, 60))           # horizontal band
    x, y = track.source_end(m, 90)           # drifting east -> source end on the west side
    assert x <= 22


PLUME = [{"plume_id": 1, "geometry": {"land": {}}}]


def test_agent_track_plume_tool(tmp_path):
    tb = agent.Toolbox(tmp_path, PLUME, historical=True, image_time="2026-10-17T21:00:00Z")
    r = tb.call("track_plume", json.dumps({"plume_id": 1}))
    assert r["ok"] and r["result"]["available"] is False                    # not run
    (tmp_path / "05_track.json").write_text(json.dumps({
        "available": True, "frames": ["2026-10-17T18:00Z", "2026-10-17T21:00Z"], "note": "n",
        "plumes": [{"plume_id": 1, "frames_tracked": 19, "frames_total": 19,
                    "motion": {"toward_deg": 214, "speed_kmh": 18.1, "r2": 0.98},
                    "source_end": {"lat": 19.06, "lon": -155.44}}]}))
    r = tb.call("track_plume", json.dumps({"plume_id": 1}))["result"]
    assert r["available"] and r["drift_toward_deg"] == 214 and r["frames_tracked"] == "19/19"
    assert tb.call("track_plume", json.dumps({"plume_id": 7}))["ok"] is False   # unknown plume
    assert any(t["name"] == "track_plume" for t in agent.TOOLS)


def test_site_track_block_modis_message(tmp_path):
    from src import sitedata
    out = tmp_path / "site"
    out.mkdir()
    blk = sitedata._track_block(tmp_path, out, {"image": {"layer": "MODIS_Terra_CorrectedReflectance_TrueColor"}},
                                tmp_path / "none.json")
    assert blk == {"available": False, "reason": track.UNAVAILABLE}
