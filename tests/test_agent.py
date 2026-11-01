"""Agentic classifier: citation verification, tool argument checks, mocked tool loop."""

import json
from types import SimpleNamespace

import jsonschema
import pytest
from PIL import Image

from src import agent

PLUMES = [{"plume_id": 1, "geometry": {"centroid": {"lat": 18.7, "lon": -155.6},
                                       "bbox_lonlat": [-156.2, 18.2, -155.0, 19.2], "area_km2": 9000,
                                       "length_km": 170, "upwind_end": {"lat": 19.1, "lon": -155.2},
                                       "upwind_end_distance_km": {"kilauea_summit": 40, "mauna_loa_summit": 70},
                                       "land": {"land_frac": 0.01, "islands_covered": {}, "land_spill": False,
                                                "islands_swallowed": []}}}]


def ok(cite, name="get_wind"):
    return {"cite": cite, "call_id": "call_" + cite, "name": name, "arguments": "{}",
            "output": {"ok": True, "result": {}}}


def final(cites):
    return {"class": "vog_kilauea", "confidence": 0.8, "source_hint": "", "caveats": "",
            "per_plume": [{"plume_id": 1, "class": "vog_kilauea", "confidence": 0.8, "source_hint": "",
                           "evidence": [{"text": "wind from NE", "cites": cites}]}]}


def test_final_schema_is_strict():
    jsonschema.Draft202012Validator.check_schema(agent.FINAL_SCHEMA)


def test_citations_must_point_to_successful_calls():
    trace = [ok("c1"), {"cite": "c2", "call_id": "call_x", "name": "get_firms", "arguments": "{}",
                        "output": {"ok": False, "error": "x"}}]
    assert agent.verify_citations(final(["c1"]), trace) is None
    assert "cites no tool output" in agent.verify_citations(final([]), trace)
    assert "unknown or failed" in agent.verify_citations(final(["c2"]), trace)   # failed call
    assert "unknown or failed" in agent.verify_citations(final(["zz"]), trace)   # invented id
    assert agent.verify_citations({"per_plume": []}, trace) == "no per-plume verdicts"
    mixed = final(["c1"])
    mixed["per_plume"][0]["evidence"].append({"text": "uncited claim", "cites": []})
    assert "has no citation" in agent.verify_citations(mixed, trace)


def test_toolbox_validates_arguments(tmp_path):
    tb = agent.Toolbox(tmp_path, PLUMES, historical=True, image_time="2026-10-17T21:00:00Z")
    assert tb.call("land_fraction", json.dumps({"plume_id": 9}))["ok"] is False      # unknown plume
    assert tb.call("get_wind", json.dumps({"lat": 40, "lon": -100, "time_utc": "2026-10-17"}))["ok"] is False
    assert tb.call("get_firms", json.dumps({"bbox": [1, 2], "date": "2026-10-17"}))["ok"] is False
    assert tb.call("rm_rf", "{}")["ok"] is False
    assert tb.call("land_fraction", "not json")["ok"] is False
    # stored geometry is used when the run has no saved mask
    d = tb.call("distance_to_vents", json.dumps({"plume_id": 1}))
    assert d["ok"] and d["result"]["upwind_end_distance_km"]["kilauea_summit"] == 40


class FakeResponses:
    """Round 1: two tool calls. Round 2: final JSON citing them."""

    def __init__(self, final_cites):
        self.calls, self.final_cites = [], final_cites

    def create(self, **kw):
        self.calls.append(kw)
        usage = SimpleNamespace(input_tokens=100, output_tokens=50,
                                input_tokens_details=SimpleNamespace(cached_tokens=0),
                                output_tokens_details=SimpleNamespace(reasoning_tokens=10))
        if len(self.calls) == 1:
            out = [SimpleNamespace(type="function_call", name="land_fraction", call_id="call_a",
                                   arguments=json.dumps({"plume_id": 1})),
                   SimpleNamespace(type="function_call", name="distance_to_vents", call_id="call_b",
                                   arguments=json.dumps({"plume_id": 1}))]
            return SimpleNamespace(id="r1", output=out, usage=usage, model="muse-spark-1.3", output_text="")
        return SimpleNamespace(id="r2", output=[SimpleNamespace(type="message")], usage=usage,
                               model="muse-spark-1.3", output_text=json.dumps(final(self.final_cites)))


@pytest.mark.parametrize("cites,valid", [(["E1", "E2"], True), ([], False),
                                         (["call_a"], False)])  # raw call_ids are not citable
def test_tool_loop_end_to_end(monkeypatch, tmp_path, cites, valid):
    fr = FakeResponses(cites)
    monkeypatch.setattr(agent, "client", lambda: SimpleNamespace(responses=fr))
    monkeypatch.setattr(agent, "log_cost", lambda *a, **k: None)
    out = agent.classify_agentic("t", tmp_path, Image.new("RGB", (64, 48)), PLUMES,
                                 {"image_time": "2026-10-17T21:00:00Z"}, historical=True)
    assert [t["name"] for t in out["trace"]] == ["land_fraction", "distance_to_vents"]
    assert all(t["output"]["ok"] for t in out["trace"])
    assert out["valid"] is valid and out["meta"]["rounds"] == 2
    # tools offered every round, tool results returned with previous_response_id
    assert all(c["tools"] == agent.TOOLS for c in fr.calls)
    assert fr.calls[1]["previous_response_id"] == "r1"
    assert {i["call_id"] for i in fr.calls[1]["input"]} == {"call_a", "call_b"}
    if valid:
        assert out["result"]["per_plume"][0]["evidence"][0].endswith("[E1, E2]")
        assert [t["output"]["cite_as"] for t in out["trace"]] == ["E1", "E2"]
    else:
        assert out["result"] is None and out["rejected"]
