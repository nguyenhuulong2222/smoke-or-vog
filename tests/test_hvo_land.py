from PIL import Image

from src import land, sources


def test_classify_eruption_from_real_hvo_wording():
    c = sources.classify_eruption
    assert c("Kīlauea volcano is not erupting. No significant changes have been observed.") == "no"
    assert c("The summit eruption of Kīlauea Volcano, within Halemaʻumaʻu crater, continued "
             "over the past 24 hours.") == "yes"
    assert c("The Northeast Rift Zone eruption of Mauna Loa continues, with two active "
             "fissures feeding lava flows downslope.") == "yes"
    assert c("Episode 55 of the ongoing Halemaʻumaʻu eruption ended abruptly at 9:03 a.m. "
             "HST on October 17, 2026.") == "episodic_pause"
    assert c("The Halema'uma'u eruption of Kīlauea remains paused following episode 55.") \
        == "episodic_pause"
    assert c("Mauna Loa earthquake counts decreased in September.") == "unknown"


WEEKLY_2023 = """<b>KILAUEA</b> (VNUM #332010)<br/>19°25'16" N 155°17'13" W, Summit Elevation
4091 ft (1247 m)<br/>Current Volcano Alert Level: ADVISORY<br/>Current Aviation Color Code:
YELLOW<br/><br/><span name="summary"><p><strong>Activity Summary:</strong> K&#299;lauea volcano
is not&nbsp;erupting. No significant changes have been observed at the summit or in either rift
zone over the past week.<br /><br /><strong>Summit Observations: </strong>Over the past week...
<b>MAUNA LOA</b> (VNUM #332020)<br/>Current Volcano Alert Level: NORMAL<br/>Current Aviation
Color Code: GREEN<br/><strong>Activity Summary:</strong> Mauna Loa is not erupting."""


def test_parse_hvo_notice_picks_the_right_volcano_block():
    k = sources.parse_hvo_notice(WEEKLY_2023, r"K[IĪ]LAUEA")
    assert (k["alert_level"], k["aviation_color"], k["erupting"]) == ("ADVISORY", "YELLOW", "no")
    assert k["activity_summary"].startswith("Kīlauea volcano is not erupting.")
    m = sources.parse_hvo_notice(WEEKLY_2023, r"MAUNA LOA")
    assert (m["alert_level"], m["aviation_color"], m["erupting"]) == ("NORMAL", "GREEN", "no")


def test_normal_green_without_summary_counts_as_not_erupting():
    m = sources.parse_hvo_notice("MAUNA LOA (VNUM #332020) Current Volcano Alert Level: NORMAL "
                                 "Current Aviation Color Code: GREEN", r"MAUNA LOA")
    assert m["erupting"] == "no"


def test_islands_named_and_sized():
    sizes = {n: m.histogram()[255] for n, m in land.island_masks().items()}
    assert set(sizes) == set(land.ISLANDS)
    assert max(sizes, key=sizes.get) == "Hawaiʻi"
    assert 30000 < sizes["Hawaiʻi"] < 42000   # ~10,400 km2 at ~0.29 km2/px


def test_ocean_plume_has_no_land_and_swallowing_islands_is_flagged():
    sea = Image.new("L", (1400, 1000), 0)
    sea.paste(255, (1000, 850, 1200, 950))     # open ocean south of Hawaiʻi Island
    s = land.land_stats(sea)
    assert s["land_frac"] == 0 and not s["land_spill"]
    blob = Image.new("L", (1400, 1000), 0)
    blob.paste(255, (700, 350, 1000, 500))     # covers Maui Nui islands
    s2 = land.land_stats(blob)
    assert s2["land_spill"] and "Molokaʻi" in s2["islands_swallowed"]
    assert land.pass2_adds_land(s, s2) is not None
    assert land.pass2_adds_land(s, s) is None


def test_unreliable_reason():
    assert land.unreliable_reason({"islands_swallowed": ["Hawaiʻi"], "land_frac": 0.94})
    assert land.unreliable_reason({"islands_swallowed": [], "land_frac": 0.6})
    assert land.unreliable_reason({"islands_swallowed": [], "land_frac": 0.1}) is None
