from src import sources


def test_kahuola_flagged_points_fall_inside_kilauea_box():
    # Real Kahu Ola volcanic_zone=true detection (2026-10-30) and the extent we observed.
    for lat, lon in [(19.40129, -155.28378), (19.41722, -155.26666), (19.401, -155.29115)]:
        assert sources.volcanic_zone_of(lat, lon) == "kilauea-summit"


def test_mauna_loa_caldera_and_rift_vents():
    assert sources.volcanic_zone_of(19.475, -155.605) == "mauna-loa-summit"
    # 2022 NE rift fissure vents are outside the summit caldera box (stay as fire points).
    assert sources.volcanic_zone_of(19.55, -155.50) is None


def test_split_uses_flag_first_then_boxes():
    pts = [
        {"lat": 19.41, "lon": -155.28},                          # in box, no flag -> volcanic
        {"lat": 20.81, "lon": -156.30},                          # Kula, Maui -> fire
        {"lat": 19.41, "lon": -155.28, "volcanic_zone": False},  # upstream says not volcanic
        {"lat": 21.30, "lon": -157.80, "volcanic_zone": True},   # upstream flag wins
    ]
    fires, volcanic = sources.split_volcanic(pts)
    assert [(f["lat"], f["lon"]) for f in fires] == [(20.81, -156.30), (19.41, -155.28)]
    assert volcanic == {"kilauea-summit": 1, "flagged": 1}


def test_firms_result_clusters_exclude_summit_glow():
    pts = [{"lat": 19.405, "lon": -155.28} for _ in range(50)] + \
          [{"lat": 20.81, "lon": -156.30} for _ in range(5)]
    out = sources._firms_result("test", pts)
    assert out["volcanic_thermal"] == {"kilauea-summit": 50}
    assert out["fire_points_count"] == 5
    assert len(out["clusters"]) == 1
    c = out["clusters"][0]
    assert c["near"].startswith("Kula")
    assert c["nearest_summit_km"] > 100


def test_fetch_firms_live_splits_on_volcanic_zone_flag(monkeypatch):
    fc = {"type": "FeatureCollection", "features": [
        {"geometry": {"coordinates": [-155.28378, 19.40129]},
         "properties": {"frp_mw": 1.3, "volcanic_zone": True}},
        {"geometry": {"coordinates": [-156.30, 20.81]},
         "properties": {"frp_mw": 40.0, "volcanic_zone": False}},
    ], "properties": {}}
    calls = {}

    class R:
        def json(self):
            return fc

    def fake_get(url, params=None, **kw):
        calls["url"], calls["params"] = url, params
        return R()

    monkeypatch.setattr(sources.requests, "get", fake_get)
    out = sources.fetch_firms_live()
    assert calls["params"] == {"include_volcanic": 1}
    assert out["volcanic_thermal"] == {"kilauea-summit": 1}
    assert len(out["clusters"]) == 1 and out["clusters"][0]["near"].startswith("Kula")
