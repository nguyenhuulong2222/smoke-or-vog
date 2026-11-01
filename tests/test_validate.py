"""Validation rules (docs/VALIDATION.md) and ground-truth parsing, offline."""

from datetime import datetime

from PIL import Image

from src import geo, groundtruth, validate


def test_category_mapping():
    assert validate.category({"detection": "no_plume"}) == "no_plume"
    assert validate.category({"overall": {"class": "vog_kilauea"}}) == "vog"
    assert validate.category({"overall": {"class": "vog_mauna_loa"}}) == "vog"
    assert validate.category({"overall": {"class": "wildfire_smoke"}}) == "smoke"
    assert validate.category({"overall": {"class": "uncertain"}}) == "uncertain"
    assert validate.category({"overall": {"class": "dust"}}) == "uncertain"


def test_elevation_rule_relative_and_absolute():
    base = {"median": 2.0, "mad": 1.0, "n": 100}
    # threshold = 2 + max(5, 3*1.4826*1) = 2 + 5 = 7 (delta floor dominates: 4.45 < 5)
    assert validate.threshold(base, "SO2") == 7.0
    assert validate.is_elevated([1, 3, 7], base, "SO2")
    assert not validate.is_elevated([1, 3, 6.9], base, "SO2")
    noisy = {"median": 10.0, "mad": 5.0, "n": 100}       # 3*1.4826*5 = 22.2 -> threshold 32.2
    assert not validate.is_elevated([30], noisy, "PM2.5")
    assert validate.is_elevated([36], noisy, "PM2.5")     # AQI USG breakpoint always counts
    assert not validate.is_elevated([], base, "SO2")


def test_wilson_interval():
    lo, hi = validate.wilson(8, 10)
    assert 0.44 < lo < 0.5 and 0.94 < hi < 0.97
    assert validate.wilson(0, 0) is None


def test_stations_near_mask():
    sites = {"pahala": {"name": "Pahala", "lat": 19.2065, "lon": -155.4689},
             "hilo": {"name": "Hilo", "lat": 19.7176, "lon": -155.1105}}
    m = Image.new("L", (geo.WIDTH, geo.HEIGHT), 0)
    x, y = geo.lonlat_to_px(-155.50, 19.15)  # ~7 km from Pāhala, ~80 km from Hilo
    m.paste(255, (int(x) - 10, int(y) - 10, int(x) + 10, int(y) + 10))
    assert validate.stations_near_mask(m, sites) == ["pahala"]


def test_parse_airnow_hourly():
    text = ("10/17/26|21:00|150012016|Pahala|-10|SO2|PPB|2|Hawaii State Dept. of Health\n"
            "10/17/26|21:00|150012016|Pahala|-10|WD|DEGREES|105.9|Hawaii State Dept. of Health\n"
            "10/17/26|21:00|060010007|Livermore|-8|PM2.5|UG/M3|9|CARB\n"
            "10/17/26|21:00|150090006|Kihei, Maui|-10|PM2.5|UG/M3|-999|Hawaii State Dept. of Health\n")
    rows = groundtruth.parse_hourly(text)
    assert rows == [{"time_utc": "2026-10-17T21:00Z", "site": "150012016", "name": "Pahala",
                     "param": "SO2", "value": 2.0}]


def test_window_values():
    idx = {("s", "SO2", "2026-10-17T19:00Z"): 1.0, ("s", "SO2", "2026-10-18T00:00Z"): 9.0,
           ("s", "SO2", "2026-10-18T01:00Z"): 99.0}
    v = validate.window_values(idx, "s", "SO2", datetime(2026, 10, 17, 21))
    assert sorted(v) == [1.0, 9.0]   # 18Z..00Z inclusive; 01Z is outside ±3 h


def test_day_headline_priority():
    from src import history
    s = lambda cat, cls: {"category": cat, "class": cls}
    assert history.day_headline([s("no_plume", "no_plume"), s("uncertain", "uncertain")]) == "uncertain"
    assert history.day_headline([s("vog", "vog_kilauea"), s("smoke", "wildfire_smoke")]) == "wildfire_smoke"
    assert history.day_headline([s("no_plume", "no_plume")]) == "no_plume"
