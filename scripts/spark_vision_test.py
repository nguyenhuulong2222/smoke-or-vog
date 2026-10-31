"""Smoke test (c): Muse Spark describes the haze in a frame and its likely
source (Kīlauea vog vs wildfire smoke), returned as schema-constrained JSON.

Default input is the latest Kahu Ola GOES-18 frame (same as sam_test.py);
pass --image PATH_OR_URL to use another picture.
"""

import argparse
import json

import openai

from _common import OUT, client, fetch_frame, log_cost, spark_cost, to_data_url

MODELS = ["muse-spark-1.3", "muse-spark-1.2"]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "image_type": {"type": "string", "description": "what kind of image this is"},
        "haze_present": {"type": "boolean"},
        "haze_description": {"type": "string"},
        "likely_source": {"type": "string", "enum": ["kilauea_vog", "wildfire_smoke", "mixed", "unknown", "none"]},
        "confidence": {"type": "number", "description": "0 to 1"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "caveats": {"type": "string"},
    },
    "required": ["image_type", "haze_present", "haze_description", "likely_source",
                 "confidence", "evidence", "caveats"],
}

PROMPT = (
    "This image is a satellite-derived haze frame over the Hawaiian Islands "
    "(lon -161 to -154, lat 18 to 23). It may be a sparse overlay where only "
    "detected haze pixels are drawn on a black background. Describe any haze "
    "or plume you see and judge its likely source: volcanic vog from Kīlauea "
    "(Island of Hawaiʻi, usually drifting southwest past Ka Lae on trade winds) "
    "versus wildfire smoke. If the image contains no haze, say so plainly; do "
    "not invent features."
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="path or URL; default = latest Kahu Ola frame")
    ap.add_argument("--out", default="spark_vision.json")
    args = ap.parse_args()

    im, label = fetch_frame(args.image)
    print(f"input: {label}  size={im.size}")
    c = client()
    for model in MODELS:
        try:
            r = c.responses.create(
                model=model,
                input=[{
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": PROMPT},
                        {"type": "input_image", "image_url": to_data_url(im)},
                    ],
                }],
                text={"format": {"type": "json_schema", "name": "haze_assessment",
                                 "schema": SCHEMA, "strict": True}},
            )
        except openai.APIStatusError as e:
            print(f"{model}: HTTP {e.status_code}, trying fallback")
            log_cost("spark_vision_test", model, 0.0, status=f"http_{e.status_code}")
            continue
        cost, toks = spark_cost(r.usage)
        log_cost("spark_vision_test", r.model, cost, note=f"image={label[:80]}", **toks)
        result = json.loads(r.output_text)
        out_path = OUT / args.out
        out_path.write_text(json.dumps({"model": r.model, "input": label, "result": result},
                                       indent=2, ensure_ascii=False))
        print(f"model: {r.model}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"usage: {toks}  cost: ${cost:.6f}")
        print(f"saved: {out_path}")
        return
    raise SystemExit("all models failed")


if __name__ == "__main__":
    main()
