from src.aggregate import aggregate


def p(i, cls, conf):
    return {"plume_id": i, "class": cls, "confidence": conf, "source_hint": ""}


def test_maui_case_wildfire_wins_over_uncertain_dominant_plume():
    # Regression: the 2023-08-08 run showed overall "uncertain" although #2 was smoke 0.88.
    out = aggregate([p(1, "uncertain", 0.45), p(2, "wildfire_smoke", 0.88),
                     p(3, "wildfire_smoke", 0.62)])
    assert out["class"] == "wildfire_smoke"
    assert out["confidence"] == 0.88
    assert out["plume_id"] == 2
    assert [u["plume_id"] for u in out["unconfirmed"]] == [3, 1]


def test_hazard_order_beats_confidence():
    out = aggregate([p(1, "vog_kilauea", 0.95), p(2, "wildfire_smoke", 0.71)])
    assert out["class"] == "wildfire_smoke"
    out = aggregate([p(1, "cloud", 0.99), p(2, "dust", 0.75), p(3, "vog_mauna_loa", 0.70)])
    assert out["class"] == "vog_mauna_loa"


def test_vog_ranks_tie_broken_by_confidence():
    out = aggregate([p(1, "vog_kilauea", 0.75), p(2, "vog_mauna_loa", 0.90)])
    assert out["class"] == "vog_mauna_loa"
    assert [c["plume_id"] for c in out["confirmed"]] == [2, 1]


def test_threshold_is_inclusive_and_below_is_unconfirmed():
    assert aggregate([p(1, "vog_kilauea", 0.70)])["class"] == "vog_kilauea"
    out = aggregate([p(1, "wildfire_smoke", 0.69), p(2, "vog_kilauea", 0.5)])
    assert out["class"] == "uncertain"
    assert out["confidence"] == 0.0
    assert out["max_plume_confidence"] == 0.69
    assert len(out["unconfirmed"]) == 2


def test_uncertain_class_is_never_confirmed_even_if_confident():
    out = aggregate([p(1, "uncertain", 0.95)])
    assert out["class"] == "uncertain"
    assert out["confirmed"] == []


def test_empty_is_uncertain():
    out = aggregate([])
    assert out["class"] == "uncertain" and out["plume_id"] is None


def test_unreliable_mask_cannot_confirm():
    # Regression: Mauna Loa run where SAM's "plume" was 68% of Hawaiʻi Island.
    out = aggregate([p(1, "vog_mauna_loa", 0.70), p(2, "uncertain", 0.30)],
                    unreliable={1: "mask swallows Hawaiʻi (segmentation unreliable)"})
    assert out["class"] == "uncertain"
    assert out["unconfirmed"][0]["not_confirmed_because"].startswith("mask swallows")
    # a reliable plume elsewhere still confirms
    out = aggregate([p(1, "vog_mauna_loa", 0.9), p(2, "wildfire_smoke", 0.8)],
                    unreliable={1: "x"})
    assert out["class"] == "wildfire_smoke"
