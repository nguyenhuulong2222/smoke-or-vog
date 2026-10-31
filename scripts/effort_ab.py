"""A/B the classifier's reasoning effort on saved run contexts (stage 4 only).

    .venv/bin/python scripts/effort_ab.py RUN_DIR [RUN_DIR ...]

For each run, re-classifies the saved 04_classify.json context with each effort
level N times, and scores the result against the expected answer. The original
run's own result counts as one 'medium' sample.
"""

import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import models  # noqa: E402
from src.aggregate import aggregate  # noqa: E402
from src.common import OUT  # noqa: E402

EXPECTED = {  # case -> (key plume selector, expected class); overall must match too
    "kilauea_20261017": "vog_kilauea",
    "maui_20230808": "wildfire_smoke",
    "mauna_loa_20221201": "vog_mauna_loa",
}
EXTRA = {"low": 2, "medium": 1}


def score(case: str, result: dict) -> dict:
    exp = EXPECTED[case]
    per = result["per_plume"]
    key_hit = any(p["class"] == exp for p in per)
    key_conf = max((p["confidence"] for p in per if p["class"] == exp), default=0.0)
    overall = aggregate(per)
    return {"key_plume_correct": key_hit, "key_conf": key_conf,
            "overall": overall["class"], "overall_correct": overall["class"] == exp,
            "per_plume": [(p["plume_id"], p["class"], p["confidence"]) for p in per]}


def main(run_dirs: list[str]) -> None:
    report = []
    for rd in map(Path, run_dirs):
        case = rd.name.rsplit("_", 1)[0]
        saved = json.loads((rd / "04_classify.json").read_text())
        im = Image.open(rd / "00_image.jpg").convert("RGB")
        orig = saved["result"]
        samples = [{"effort": "medium", "source": "pipeline run", "cost_usd": saved["meta"]["cost_usd"],
                    "output_tokens": saved["meta"].get("output_tokens"),
                    **score(case, orig)}]
        for effort, n in EXTRA.items():
            for k in range(n):
                res, meta = models.spark_classify(f"effort_ab:{rd.name}", im, saved["context"],
                                                  effort=effort)
                samples.append({"effort": effort, "source": f"ab#{k + 1}",
                                "cost_usd": meta["cost_usd"], "output_tokens": meta["output_tokens"],
                                **score(case, res)})
                print(f"{case:20s} {effort:6s} {samples[-1]['per_plume']} -> "
                      f"{samples[-1]['overall']}  ${meta['cost_usd']:.4f}")
        report.append({"run": rd.name, "case": case, "expected": EXPECTED[case], "samples": samples})

    summary = {}
    for effort in ("low", "medium"):
        ss = [s for r in report for s in r["samples"] if s["effort"] == effort]
        summary[effort] = {
            "n": len(ss),
            "key_plume_correct": sum(s["key_plume_correct"] for s in ss),
            "overall_correct": sum(s["overall_correct"] for s in ss),
            "mean_key_conf": round(sum(s["key_conf"] for s in ss) / len(ss), 3),
            "mean_cost_usd": round(sum(s["cost_usd"] for s in ss) / len(ss), 5),
            "mean_output_tokens": round(sum(s["output_tokens"] or 0 for s in ss) / len(ss)),
        }
    out = OUT / "effort_ab.json"
    out.write_text(json.dumps({"summary": summary, "runs": report}, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    print(f"saved {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
