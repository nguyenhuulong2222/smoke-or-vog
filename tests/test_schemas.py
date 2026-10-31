"""Stage JSON schemas and request shapes, with the Meta API mocked (no credits)."""

import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
from PIL import Image

from src import models, pipeline
from src.aggregate import aggregate

DEMO = Path(__file__).resolve().parent.parent / "demo"


def walk_objects(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for v in schema.values():
            yield from walk_objects(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from walk_objects(v)


@pytest.mark.parametrize("schema", [models.LOCALIZE_SCHEMA, models.CLASSIFY_SCHEMA])
def test_schemas_meet_strict_subset(schema):
    jsonschema.Draft202012Validator.check_schema(schema)
    for obj in walk_objects(schema):
        assert obj.get("additionalProperties") is False
        assert sorted(obj["required"]) == sorted(obj["properties"])


def test_classify_enum_matches_spec():
    assert models.CLASSES == ["vog_kilauea", "vog_mauna_loa", "wildfire_smoke", "dust",
                              "cloud", "uncertain"]


@pytest.mark.parametrize("case", ["kilauea_20261017", "maui_20230808", "mauna_loa_20221201",
                                  "live_20261031"])
def test_saved_demo_outputs_validate(case):
    loc = json.loads((DEMO / case / "02_spark_localize.json").read_text())["result"]
    jsonschema.validate(loc, models.LOCALIZE_SCHEMA)
    cls = dict(json.loads((DEMO / case / "04_classify.json").read_text())["result"])
    # The pipeline renames the model's own overall fields and adds the aggregated verdict.
    cls["class"] = cls.pop("model_overall_class")
    cls["confidence"] = cls.pop("model_overall_confidence")
    overall = cls.pop("overall")
    assert overall == aggregate(cls["per_plume"])
    if "detection" not in cls:  # live 'no_plume' result is synthesised, not model output
        jsonschema.validate(cls, models.CLASSIFY_SCHEMA)


# ---------------------------------------------------------------- mocked Spark

class FakeResponses:
    def __init__(self, payload):
        self.payload, self.kwargs = payload, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        usage = SimpleNamespace(input_tokens=1000, output_tokens=500,
                                input_tokens_details=SimpleNamespace(cached_tokens=0),
                                output_tokens_details=SimpleNamespace(reasoning_tokens=400))
        return SimpleNamespace(output_text=json.dumps(self.payload), usage=usage,
                               model="muse-spark-1.3")


@pytest.fixture
def no_cost_log(monkeypatch):
    rows = []
    monkeypatch.setattr(models, "log_cost", lambda *a, **k: rows.append((a, k)))
    return rows


def fake_client(monkeypatch, payload):
    fr = FakeResponses(payload)
    monkeypatch.setattr(models, "client", lambda: SimpleNamespace(responses=fr))
    return fr


def check_spark_request(kwargs, name, effort):
    assert kwargs["model"] == "muse-spark-1.3"
    assert kwargs["reasoning"] == {"effort": effort}
    fmt = kwargs["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["name"] == name and fmt["strict"] is True
    msg = kwargs["input"][0]
    assert msg["role"] == "user"
    kinds = [c["type"] for c in msg["content"]]
    assert kinds == ["input_text", "input_image"]
    assert msg["content"][1]["image_url"].startswith("data:image/jpeg;base64,")


def test_spark_localize_request_and_output(monkeypatch, no_cost_log):
    payload = {"scene_description": "s", "cloud_cover": "partly", "plumes": [
        {"label": "thin gray streak", "visual_description": "d",
         "bbox": {"x_min": 1, "y_min": 2, "x_max": 3, "y_max": 4},
         "origin_point": {"x": 1, "y": 2}, "inside_point": {"x": 2, "y": 3},
         "visibility": "faint"}]}
    fr = fake_client(monkeypatch, payload)
    out, meta = models.spark_localize("t", Image.new("RGB", (64, 48)), "hints")
    check_spark_request(fr.kwargs, "plume_localization", "medium")
    jsonschema.validate(out, models.LOCALIZE_SCHEMA)
    assert meta["cost_usd"] == pytest.approx((1000 * 1.25 + 500 * 4.25) / 1e6)
    assert len(no_cost_log) == 1


@pytest.mark.parametrize("effort", ["low", "medium"])
def test_spark_classify_request_and_output(monkeypatch, no_cost_log, effort):
    payload = {"class": "vog_kilauea", "confidence": 0.8, "evidence": ["e"], "source_hint": "h",
               "per_plume": [{"plume_id": 1, "class": "vog_kilauea", "confidence": 0.8,
                              "evidence": ["e"], "source_hint": "h"}], "caveats": "c"}
    fr = fake_client(monkeypatch, payload)
    out, meta = models.spark_classify("t", Image.new("RGB", (64, 48)), {"x": 1}, effort=effort)
    check_spark_request(fr.kwargs, "haze_classification", effort)
    jsonschema.validate(out, models.CLASSIFY_SCHEMA)
    assert meta["effort"] == effort


# ---------------------------------------------------------------- mocked SAM

# A real mask record from dev.meta.ai/docs/sam/reading-segmentation (27x60 lossless).
DOC_LINE = ("<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334;c=0.9|><|mask;x=0;y=0;c=0.9;"
            "data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>")


class FakeStream:
    def __init__(self, line):
        lane = {"item_id": "msg_1", "output_index": 0, "content_index": 0}
        self.events = [
            SimpleNamespace(type="response.output_text.delta", delta=line, **lane),
            SimpleNamespace(type="response.output_text.done", text=line, **lane),
            SimpleNamespace(type="response.completed",
                            response=SimpleNamespace(usage=SimpleNamespace(images_processed=1))),
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            for e in self.events:
                yield e
        return gen()


def fake_async_client(monkeypatch, line, seen):
    class Responses:
        async def create(self, **kwargs):
            seen.update(kwargs)
            return FakeStream(line)

    class C:
        responses = Responses()

        async def close(self):
            pass

    monkeypatch.setattr(models, "async_client", lambda: C())


def test_sam_segment_parses_stream_into_full_frame_mask(monkeypatch, no_cost_log):
    seen = {}
    fake_async_client(monkeypatch, DOC_LINE, seen)
    im = Image.new("RGB", (320, 334))
    out = models.sam_segment("t", im, "box", "<0f>1<|box;x1=1;y1=1;x2=9;y2=9;w=320;h=334|>")
    assert seen["model"] == "sam-3.1" and seen["stream"] is True
    assert seen["metadata"] == {"include_confidence": "true"}
    assert out["outcome"] == "completed" and out["images_processed"] == 1
    assert len(out["objects"]) == 1
    o = out["objects"][0]
    assert o["mask"].size == (320, 334)
    bb = o["mask"].getbbox()
    assert bb and 205 <= bb[0] and bb[2] <= 275 and 225 <= bb[1] and bb[3] <= 258
    assert o["confidence"] == pytest.approx(0.9)
    assert no_cost_log[0][0][2] == pytest.approx(0.0025)


def test_sam_zero_matches_is_valid(monkeypatch, no_cost_log):
    class Empty(FakeStream):
        def __init__(self):
            self.events = [SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(usage=SimpleNamespace(images_processed=1)))]

    class C:
        class responses:  # noqa: N801
            @staticmethod
            async def create(**kw):
                return Empty()

        async def close(self):
            pass

    monkeypatch.setattr(models, "async_client", lambda: C())
    out = models.sam_segment("t", Image.new("RGB", (32, 32)), "concept:haze", "haze")
    # Docs: zero matches completes with an empty lane. Accept either a clean empty
    # result or a recorded error, but never a crash, and never invented objects.
    assert out["objects"] == []


# ---------------------------------------------------------------- two-pass selection

def test_choose_pass_rules():
    q1 = {"area_px": 1000, "coherence": 0.95, "bbox_frac": 0.02, "edges_touched": 0}
    good = {"area_px": 1500, "coherence": 0.93, "bbox_frac": 0.03, "edges_touched": 0}
    assert pipeline.choose_pass(q1, good)[0] == "pass2"
    assert pipeline.choose_pass(q1, {**good, "area_px": 900})[0] == "pass1"
    assert pipeline.choose_pass(q1, {**good, "coherence": 0.5})[0] == "pass1"
    assert pipeline.choose_pass(q1, {**good, "area_px": 5000})[0] == "pass1"
    assert pipeline.choose_pass(q1, {**good, "bbox_frac": 0.4})[0] == "pass1"
    assert pipeline.choose_pass(q1, {**good, "edges_touched": 2})[0] == "pass1"
    assert pipeline.choose_pass(q1, {})[0] == "pass1"


def test_refine_box_expands_15_percent_and_clips():
    m = Image.new("L", (1400, 1000), 0)
    m.paste(255, (100, 200, 300, 300))  # 200 x 100 px
    assert pipeline.refine_box(m) == [70, 185, 329, 314]
    edge = Image.new("L", (1400, 1000), 0)
    edge.paste(255, (0, 0, 100, 100))
    assert pipeline.refine_box(edge)[:2] == [0, 0]
