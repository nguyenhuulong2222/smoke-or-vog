"""Stage 5 alerts: schema, languages, disclaimer, grounding, font rendering (no credits)."""

import json
import unicodedata

import jsonschema
import pytest
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw

from src import alerts

ALERTS_FILE_SCHEMA = {
    "type": "object",
    "required": ["run_id", "verdict", "confidence", "official_source_url", "health_sources",
                 "alerts"],
    "properties": {
        "verdict": {"enum": alerts.VERDICTS},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "official_source_url": {"type": "string", "pattern": "^https://"},
        "alerts": {"type": "array", "minItems": 5, "maxItems": 5, "items": {
            "type": "object",
            "required": ["lang", "headline", "summary", "actions", "confidence", "disclaimer",
                         "disclaimer_en", "official_source_url", "machine_translated",
                         "needs_community_review", "card"],
            "properties": {
                "lang": {"enum": list(alerts.LANGS)},
                "headline": {"type": "string", "minLength": 1},
                "actions": {"type": "array", "minItems": 1, "maxItems": 3, "items": {
                    "type": "object", "required": ["text", "source_id", "index", "excerpt_en", "url"],
                    "properties": {"url": {"type": "string", "pattern": "^https://"}}}},
                "disclaimer_en": {"const": "Satellite estimate, not an official warning."},
                "machine_translated": {"type": "boolean"},
                "needs_community_review": {"type": "boolean"},
            }}},
    },
}


def fake_raw(verdict, n_actions=2, langs=None):
    sid = alerts.HEALTH["verdict_sources"][verdict][0]
    return {
        "selected_excerpts": [{"source_id": sid, "index": i} for i in range(n_actions)],
        "alerts": [{"lang": code, "headline": f"Headline {code} Kaʻū",
                    "summary": "Satellite suggests haze near Pāhala (Kaʻū).",
                    "actions": [f"action {i}" for i in range(n_actions)],
                    "disclaimer": "Satellite estimate, not an official warning.",
                    "confidence_label": "Confidence: 75%",
                    "replay_banner": ""} for code in (langs or alerts.LANGS)],
    }


# ---------------------------------------------------------------- coverage of all verdicts

@pytest.mark.parametrize("verdict", alerts.VERDICTS)
def test_every_verdict_has_sources_link_background_and_valid_schema(verdict):
    assert alerts.HEALTH["verdict_sources"][verdict]
    assert alerts.HEALTH["verdict_links"][verdict].startswith("https://")
    assert "no text" in (alerts.BACKGROUND_PROMPTS[verdict] + alerts.NO_TEXT).lower()
    schema = alerts.alerts_schema(verdict)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(fake_raw(verdict), schema)


def test_vog_uses_ivhhn_and_smoke_uses_airnow():
    assert alerts.HEALTH["verdict_sources"]["vog_kilauea"] == ["ivhhn_hdoh_vog_protection"]
    assert alerts.HEALTH["verdict_sources"]["wildfire_smoke"] == ["airnow_fires_and_health"]
    assert "vog.ivhhn.org" in alerts.HEALTH["sources"]["ivhhn_hdoh_vog_protection"]["url"]
    assert "airnow.gov" in alerts.HEALTH["sources"]["airnow_fires_and_health"]["url"]


def test_prompt_contains_only_the_verdicts_sources():
    p = alerts.build_prompt("wildfire_smoke", 0.88, {"near": ["Kula (Maui)"]}, "x", [])
    assert "airnow.gov/air-quality-and-health" in p and "vog.ivhhn.org" not in p
    assert "Do NOT write any other health or medical advice" in p
    assert "never written by you" in p


# ---------------------------------------------------------------- grounding

def test_grounding_rejects_bad_references():
    with pytest.raises(ValueError):  # index out of range
        raw = fake_raw("vog_kilauea")
        raw["selected_excerpts"][0]["index"] = 999
        alerts.validate_spark_alerts("vog_kilauea", raw)
    with pytest.raises(ValueError):  # source not allowed for this verdict
        raw = fake_raw("vog_kilauea")
        raw["selected_excerpts"][0]["source_id"] = "airnow_fires_and_health"
        alerts.validate_spark_alerts("vog_kilauea", raw)
    with pytest.raises(ValueError):  # missing a language
        alerts.validate_spark_alerts("vog_kilauea", fake_raw("vog_kilauea", langs=["en", "vi"]))
    with pytest.raises(ValueError):  # action count must match excerpts
        raw = fake_raw("vog_kilauea")
        raw["alerts"][0]["actions"].append("invented advice")
        alerts.validate_spark_alerts("vog_kilauea", raw)


def test_assembled_alerts_file_schema_flags_and_disclaimer():
    raw = fake_raw("wildfire_smoke")
    g = alerts.validate_spark_alerts("wildfire_smoke", raw)
    doc = alerts.assemble("run", "wildfire_smoke", 0.88, {"near": []}, "2023-08-08", raw, g, {},
                          mode="replay")
    jsonschema.validate(doc, ALERTS_FILE_SCHEMA)
    by = {a["lang"]: a for a in doc["alerts"]}
    assert set(by) == {"en", "vi", "ilo", "tl", "haw"}
    assert by["en"]["machine_translated"] is False and by["en"]["needs_community_review"] is False
    assert by["vi"]["machine_translated"] is True and by["vi"]["needs_community_review"] is False
    for c in ("ilo", "tl", "haw"):
        assert by[c]["machine_translated"] and by[c]["needs_community_review"]
    for a in doc["alerts"]:
        assert a["disclaimer_en"] == "Satellite estimate, not an official warning."
        assert a["confidence"] == 0.88
        for act in a["actions"]:
            src = alerts.HEALTH["sources"][act["source_id"]]
            assert act["excerpt_en"] == src["excerpts"][act["index"]]


# ---------------------------------------------------------------- fonts

TEST_STRINGS = ["Kaʻū", "Hawaiʻi", "khói", "sương mù núi lửa", "ʻŌlelo Hawaiʻi", "Lānaʻi",
                "Cảnh báo khói cháy rừng"]


@pytest.mark.parametrize("path", [alerts.FONT_REG, alerts.FONT_BOLD])
def test_font_has_every_glyph(path):
    cmap = TTFont(str(path)).getBestCmap()
    for s in TEST_STRINGS:
        missing = [c for c in unicodedata.normalize("NFC", s) if ord(c) not in cmap]
        assert not missing, (s, missing)


def _render(text, f):
    im = Image.new("L", (900, 120), 0)
    ImageDraw.Draw(im).text((10, 10), text, font=f, fill=255)
    return im


def test_diacritics_actually_render():
    f = alerts.font(48, True)
    for marked, plain in [("Kaʻū", "Kau"), ("Hawaiʻi", "Hawaii"), ("khói", "khoi"),
                          ("sương mù núi lửa", "suong mu nui lua")]:
        a, b = _render(marked, f), _render(plain, f)
        assert a.getbbox() is not None
        assert ImageChops.difference(a, b).getbbox() is not None, marked
    # the ʻokina on its own draws visible ink
    assert _render("ʻ", f).getbbox() is not None


def test_card_renders_all_languages(tmp_path):
    raw = fake_raw("vog_kilauea")
    g = alerts.validate_spark_alerts("vog_kilauea", raw)
    doc = alerts.assemble("run", "vog_kilauea", 0.7, {"near": []}, "2026-10-31T21:40:00Z", raw, g,
                          {}, mode="live")
    bg = Image.new("RGB", (1536, 1024), (60, 90, 120))
    for a in doc["alerts"]:
        card = alerts.render_card(bg, a, "vog_kilauea")
        assert card.size == (alerts.CARD_W, alerts.CARD_H)
        card.save(tmp_path / a["card"])
    assert len(list(tmp_path.glob("alert_*.png"))) == 5


def test_run_alerts_end_to_end_mocked(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"run_id": "kilauea_20261017_test",
                                              "case": "kilauea_20261017"}))
    plume = {"plume_id": 1, "geometry": {"bbox_lonlat": [-156.27, 18.22, -154.95, 19.25],
                                         "centroid": {"lat": 18.7, "lon": -155.6},
                                         "upwind_end": {"lat": 19.17, "lon": -154.83}}}
    (run / "04_classify.json").write_text(json.dumps({
        "context": {"image": {"time": "2026-10-17T21:00:00Z"}, "plumes": [plume]},
        "result": {"overall": {"class": "vog_kilauea", "confidence": 0.7, "plume_id": 1,
                               "unconfirmed": []}, "per_plume": []}}))
    monkeypatch.setattr(alerts, "_spark_json",
                        lambda *a, **k: (fake_raw("vog_kilauea"), {"cost_usd": 0}))
    monkeypatch.setattr(alerts, "background", lambda v, r: Image.new("RGB", (1536, 1024), "gray"))
    out = alerts.run_alerts(run)
    doc = json.loads((out / "alerts.json").read_text())
    jsonschema.validate(doc, ALERTS_FILE_SCHEMA)
    assert "Pāhala (Kaʻū)" in doc["places"]["near"]
    assert doc["mode"] == "replay"
    assert doc["replay_banner_en"] == "REPLAY · Oct 17, 2026 · not a current alert"
    for a in doc["alerts"]:
        assert a["mode"] == "replay" and a["replay_banner"] and a["replay_banner_en"]
        card = Image.open(out / a["card"]).convert("RGB")
        assert card.getpixel((5, 5)) == alerts.REPLAY_COLOR
    assert sorted(p.name for p in out.glob("alert_*.png")) == [
        "alert_en.png", "alert_haw.png", "alert_ilo.png", "alert_tl.png", "alert_vi.png"]


def test_places_near_mask_does_not_overreach_like_bbox():
    from src import geo
    # Diagonal band from Kula (Maui) toward the SW; its bbox would include Honolulu-ish areas
    m = Image.new("L", (1400, 1000), 0)
    d = ImageDraw.Draw(m)
    a = geo.lonlat_to_px(-156.33, 20.78)
    b = geo.lonlat_to_px(-158.2, 20.2)
    d.line([a, b], fill=255, width=30)
    near = alerts.places_near_mask(m)
    assert "Kula (Maui)" in near
    assert "Honolulu (Oʻahu)" not in near


# ---------------------------------------------------------------- replay safety

BG = Image.new("RGB", (1536, 1024), (60, 90, 120))


def replay_doc(local_banner=""):
    raw = fake_raw("wildfire_smoke")
    for a in raw["alerts"]:
        a["replay_banner"] = local_banner
    g = alerts.validate_spark_alerts("wildfire_smoke", raw)
    return alerts.assemble("maui_20230808_x", "wildfire_smoke", 0.9, {"near": []}, "2023-08-08",
                           raw, g, {}, mode="replay")


def has_banner(card):
    # every pixel of the left margin of the top band is the replay colour
    return all(card.getpixel((x, y)) == alerts.REPLAY_COLOR for x in (2, 20, 40) for y in (2, 30, 60))


def test_replay_banner_text_and_flags():
    doc = replay_doc()
    assert doc["mode"] == "replay"
    assert doc["replay_banner_en"] == "REPLAY · Aug 8, 2023 · not a current alert"
    for a in doc["alerts"]:
        # model gave no localized banner -> English fallback is used, never empty
        assert a["replay_banner"] == doc["replay_banner_en"]


@pytest.mark.parametrize("local", ["", "PHÁT LẠI · 8 thg 8, 2023 · không phải cảnh báo hiện tại"])
def test_replay_card_always_has_banner(local):
    for a in replay_doc(local)["alerts"]:
        assert has_banner(alerts.render_card(BG, a, "wildfire_smoke")), a["lang"]


def test_replay_cannot_render_without_banner_or_mode():
    a = dict(replay_doc()["alerts"][0])
    a["replay_banner_en"] = ""
    with pytest.raises(ValueError):
        alerts.render_card(BG, a, "wildfire_smoke")
    a = dict(replay_doc()["alerts"][0])
    del a["mode"]
    with pytest.raises(ValueError):
        alerts.render_card(BG, a, "wildfire_smoke")
    with pytest.raises(ValueError):
        alerts.assemble("r", "dust", 0.8, {}, "2023-08-08", fake_raw("dust"),
                        alerts.validate_spark_alerts("dust", fake_raw("dust")), {}, mode="other")


def test_live_card_has_no_banner():
    raw = fake_raw("dust")
    g = alerts.validate_spark_alerts("dust", raw)
    doc = alerts.assemble("live_x", "dust", 0.8, {}, "2026-10-31T21:40:00Z", raw, g, {}, mode="live")
    for a in doc["alerts"]:
        assert a["replay_banner"] == "" and not has_banner(alerts.render_card(BG, a, "dust"))


def test_historical_and_unknown_cases_are_replay():
    assert alerts.run_mode({"run_id": "maui_20230808_x", "case": "maui_20230808"}) == "replay"
    assert alerts.run_mode({"run_id": "live_x", "case": "live"}) == "live"
    assert alerts.run_mode({"run_id": "mystery_case_x"}) == "replay"


def test_reviewed_vi_override_for_airnow_line():
    raw = fake_raw("wildfire_smoke", n_actions=1)
    raw["selected_excerpts"] = [{"source_id": "airnow_fires_and_health", "index": 4}]
    g = alerts.validate_spark_alerts("wildfire_smoke", raw)
    doc = alerts.assemble("r", "wildfire_smoke", 0.9, {}, "2023-08-08", raw, g, {}, mode="replay")
    vi = next(a for a in doc["alerts"] if a["lang"] == "vi")["actions"][0]
    assert "các cảnh báo về khói cháy rừng" in vi["text"] and vi["reviewed_override"] is True
    en = next(a for a in doc["alerts"] if a["lang"] == "en")["actions"][0]
    assert "reviewed_override" not in en


# ---------------------------------------------------------------- medical-advice rule

def good_doc(verdict="wildfire_smoke"):
    raw = fake_raw(verdict)
    g = alerts.validate_spark_alerts(verdict, raw)
    return alerts.assemble("r", verdict, 0.9, {}, "2023-08-08", raw, g, {}, mode="replay")


def test_english_guidance_is_verbatim_official_text_even_if_model_paraphrases():
    doc = good_doc()   # fake model wrote "action 0", "action 1" for English
    en = next(a for a in doc["alerts"] if a["lang"] == "en")
    for act in en["actions"]:
        src = alerts.HEALTH["sources"][act["source_id"]]["excerpts"][act["index"]]
        assert act["text"] == src and act["verbatim"] is True
    alerts.verify_guidance(doc)  # passes


def test_translations_are_labelled():
    doc = good_doc()
    for a in doc["alerts"]:
        if a["lang"] != "en":
            assert all(x["label"].startswith("Translation of official guidance") for x in a["actions"])


@pytest.mark.parametrize("tamper", ["en_text", "source", "index", "excerpt", "label", "url"])
def test_untraceable_guidance_is_rejected(tamper):
    doc = good_doc()
    en = next(a for a in doc["alerts"] if a["lang"] == "en")
    vi = next(a for a in doc["alerts"] if a["lang"] == "vi")
    if tamper == "en_text":
        en["actions"][0]["text"] = "Drink ginger tea to clear smoke from your lungs."
    elif tamper == "source":
        en["actions"][0]["source_id"] = "made_up_blog"
    elif tamper == "index":
        en["actions"][0]["index"] = 999
    elif tamper == "excerpt":
        vi["actions"][0]["excerpt_en"] = "Wear any mask outdoors."
    elif tamper == "label":
        vi["actions"][0]["label"] = "Health advice"
    elif tamper == "url":
        en["actions"][0]["url"] = "https://example.com/"
    with pytest.raises(ValueError):
        alerts.verify_guidance(doc)


def test_every_official_excerpt_in_source_file_is_reachable():
    for verdict in alerts.VERDICTS:
        for sid in alerts.HEALTH["verdict_sources"][verdict]:
            assert alerts.HEALTH["sources"][sid]["excerpts"]
