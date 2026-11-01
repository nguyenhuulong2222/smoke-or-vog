"""Muse Wonder second-opinion rules (offline)."""

from src import adjudicate as A
from src.aggregate import aggregate


def P(pid, cls, conf):
    return {"plume_id": pid, "class": cls, "confidence": conf, "source_hint": ""}


def test_trigger_band_and_conflict():
    per = [P(1, "vog_kilauea", 0.72)]
    assert A.needs_second_opinion(per, aggregate(per))
    per = [P(1, "vog_kilauea", 0.85)]
    assert A.needs_second_opinion(per, aggregate(per)) is None
    per = [P(1, "vog_kilauea", 0.60)]          # unconfirmed but borderline
    assert A.needs_second_opinion(per, aggregate(per))
    per = [P(1, "vog_kilauea", 0.40)]
    assert A.needs_second_opinion(per, aggregate(per)) is None
    per = [P(1, "vog_kilauea", 0.9), P(2, "wildfire_smoke", 0.6)]   # conflicting plumes
    assert "conflicting" in A.needs_second_opinion(per, aggregate(per))
    assert A.conflicting(per)
    assert A.needs_second_opinion([], aggregate([])) is None
    per = [P(1, "uncertain", 0.6)]             # "uncertain" at 0.6 is not borderline
    assert A.needs_second_opinion(per, aggregate(per)) is None


def test_agreement_keeps_spark_verdict_and_confidence():
    out = A.combine([P(1, "vog_kilauea", 0.72)], [P(1, "vog_kilauea", 0.95)])
    assert out["overall"]["class"] == "vog_kilauea"
    assert out["overall"]["confidence"] == 0.72          # Wonder never raises it
    assert out["agreement"]["agrees"]


def test_disagreement_forces_uncertain():
    out = A.combine([P(1, "vog_kilauea", 0.72)], [P(1, "cloud", 0.8)])
    ov = out["overall"]
    assert ov["class"] == "uncertain" and ov["plume_id"] is None and ov["second_opinion_disagreed"]
    assert "Muse Wonder" in ov["unconfirmed"][0]["not_confirmed_because"]
    assert not out["agreement"]["agrees"]


def test_wonder_cannot_override_bar():
    # Spark below 0.70: Wonder agreeing at 0.99 still leaves it uncertain
    out = A.combine([P(1, "vog_mauna_loa", 0.62)], [P(1, "vog_mauna_loa", 0.99)])
    assert out["overall"]["class"] == "uncertain"
    assert out["agreement"]["agrees"]


def test_missing_wonder_verdict_is_disagreement():
    out = A.combine([P(1, "wildfire_smoke", 0.74)], [])
    assert out["overall"]["class"] == "uncertain"


def test_bundle_hides_spark_verdict_and_cites_checked():
    trace = [{"cite": "E1", "name": "get_wind", "arguments": '{"lat": 19}', "output": {"cite_as": "E1", "ok": True}},
             {"cite": "E2", "name": "firms", "arguments": "{}", "output": {"cite_as": "E2", "ok": False}}]
    b = A.bundle({"plumes": []}, trace)
    assert "per_plume" not in str(b) and b["tool_results"][0]["arguments"] == {"lat": 19}
    good = {"per_plume": [{"plume_id": 1, "cites": ["E1"]}]}
    bad = {"per_plume": [{"plume_id": 1, "cites": ["E2"]}]}   # failed tool call
    assert A.verify_cites(good, trace) is None and A.verify_cites(bad, trace)


def test_site_block(tmp_path):
    import json
    from src import sitedata
    assert sitedata._second_opinion(tmp_path, {}) is None
    rec = {"trigger": "headline confidence 0.62 is within 0.55-0.75", "valid": True, "model": A.WONDER,
           "wonder": {"per_plume": [{"plume_id": 1, "reasoning": "far from both vents"}], "caveats": "c"},
           **A.combine([P(1, "vog_kilauea", 0.72)], [P(1, "cloud", 0.6)])}
    (tmp_path / "04_wonder.json").write_text(json.dumps(rec))
    b = sitedata._second_opinion(tmp_path, {"spark_overall": {"class": "vog_kilauea"}})
    assert b["trigger_code"] == "band" and b["trigger_conf"] == 0.62
    assert b["lowered"] and not b["agrees"] and b["spark_overall"] == "vog_kilauea"
    assert b["per_plume"][0]["wonder_reasoning"] == "far from both vents"
