# Smoke or Vog?

A Hawaiʻi haze explainer built for the Meta Global AI Developer Hackathon.

When the sky over the islands turns hazy, people want to know two things: is it
volcanic vog from Kīlauea or smoke from a wildfire, and what should I do about it?
**Smoke or Vog?** takes GOES-18 satellite haze detections, uses Meta's models to
segment and interpret the haze, and produces a plain-language alert card for the
affected district.

Built on [Meta Model API](https://dev.meta.ai/docs):

| Role | Model | Endpoint |
|---|---|---|
| Segment haze regions | `sam-3.1` | `POST /v1/responses` (streamed) |
| Interpret the scene (vog vs smoke), JSON output | `muse-spark-1.3` | `POST /v1/responses` with `text.format` json_schema |
| Render the alert card | `muse-image-1.0` | `POST /v1/images/generations` |

The satellite haze frames come from the public [Kahu Ola](https://kahuola.org) API
(`/api/hazards/smoke-sat?region=hawaii`), used as an external data source only.
Kahu Ola's haze layer is an estimate rather than an official product. For official vog
information, see <https://vog.ivhhn.org/>.

> Status: smoke tests only (Step 3). The pipeline is not built yet. See [PLAN.md](PLAN.md).

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
export PIP_CACHE_DIR=/Volumes/Crucial1TB/.cache/pip   # optional: keep pip cache on the project drive
.venv/bin/pip install openai python-dotenv requests pillow meta-sam-parser
```

Create `.env.local` in the repo root (it is git-ignored):

```
MODEL_API_KEY=LLM_...
```

The scripts load the key from `.env.local` and never print or log it.

## Smoke tests

Run from `scripts/`:

```bash
cd scripts
../.venv/bin/python hello_spark.py          # Muse Spark text answer (falls back to 1.2)
../.venv/bin/python sam_test.py             # SAM 3.1 "haze plume" on latest Kahu Ola frame -> out/sam_overlay.png
../.venv/bin/python spark_vision_test.py    # Muse Spark vog-vs-smoke JSON -> out/spark_vision.json
../.venv/bin/python image_test.py           # Muse Image alert card -> out/alert_card_vog_kau_en.png
```

`sam_test.py` and `spark_vision_test.py` accept `--image PATH_OR_URL` to run on another
image. `sam_test.py` also accepts `--prompt` and `--out`.

Every call appends a row to `out/costs.csv`. Spark cost is computed from response `usage`
tokens. SAM ($0.0025/image) and Muse Image ($0.01/image) are billed per image, using the
prices on dev.meta.ai/docs/pricing-rate-limits.

## Layout

```
scripts/        smoke tests + _common.py (client, cost log, frame fetch)
out/            generated outputs and costs.csv
data/raw/       downloaded frames (git-ignored)
```

## License

MIT. See [LICENSE](LICENSE).
