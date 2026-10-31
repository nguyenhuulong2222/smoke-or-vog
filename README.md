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

The images we segment are true-color GOES-West GeoColor (or MODIS for older dates) from
NASA GIBS. The public [Kahu Ola](https://kahuola.org) API is used only as an external
detection signal (GOES-18 ADP haze mask + metadata, FIRMS hotspots), never as the image.
Kahu Ola's haze layer is an estimate rather than an official product. For official vog
information, see <https://vog.ivhhn.org/>.

> Status: detection chain working on four cases (live, Kīlauea 2026-10-17, Maui 2023-08-08,
> Mauna Loa 2022-12-01). Curated outputs are in [`demo/`](demo/).
> No alert generation or demo UI yet. See [PLAN.md](PLAN.md).

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

## Detection pipeline

```bash
.venv/bin/python -m src.pipeline --case live              # latest GOES-West GeoColor frame
.venv/bin/python -m src.pipeline --case kilauea_20261017  # vog plume test case
.venv/bin/python -m src.pipeline --case maui_20230808     # Maui wildfire smoke test case
.venv/bin/python -m src.pipeline --case mauna_loa_20221201 # Mauna Loa eruption vog test case
.venv/bin/python -m pytest                                # 29 offline tests, Meta API mocked
```

**Overall verdict rule (safety first):** each plume is classified separately. The overall
verdict is the most hazardous class confirmed at confidence ≥ 0.70, in the order
`wildfire_smoke > vog_* > dust > cloud`. Plumes below 0.70 are listed as *unconfirmed*.
The verdict is `uncertain` only when no plume reaches 0.70 (`src/aggregate.py`).

*Intended behaviour (Mauna Loa test case, 2022-12-01):* the classifier picks the right class
(`vog_mauna_loa`) but only at 0.62. The vent area was under cloud, the visible haze was 320 km
downwind, and Kīlauea was erupting at the same time. So the overall verdict is `uncertain`, and
we don't lower the 0.70 threshold to make a test case pass. When the source can't be seen,
honest uncertainty is the correct output.

**SAM is run in two passes:** pass 1 uses the Muse Spark box and point. Pass 2 re-prompts with
the pass-1 mask's bounding box plus a 15% margin. Pass 2 is kept only if it's larger and still
coherent, with no ocean-wide spill.

**Summit glow is not fire:** FIRMS detections inside the Kīlauea and Mauna Loa summit calderas
(Kahu Ola `volcanic_zone` flag, or the same caldera boxes for historical data) are reported as
`volcanic_thermal` and kept out of the fire clusters.

Each run writes `out/runs/<case>_<UTC>/`:

| File | Stage |
|---|---|
| `00_image.jpg`, `00_context.json` | True-color image on a fixed lon/lat grid, FIRMS fire clusters, 10 m wind |
| `01_adp.json` (+ `01_adp_mask.png`) | Kahu Ola ADP haze signal → candidate regions (live only) |
| `02_spark_localize.json` | Muse Spark vision → plume boxes, origin and inside points (0–1000 grid) |
| `03_sam_*.jpg`, `03_sam.json` | SAM 3.1 with box, box+point, and concept prompts, with a score for each; `03_sam_two_pass.jpg` shows pass 1 vs pass 2 |
| `04_classify.json` | Muse Spark per-plume classes (`vog_kilauea \| vog_mauna_loa \| wildfire_smoke \| dust \| cloud \| uncertain`) plus the aggregated `overall` |
| `overlay.png`, `run.json` | Annotated overlay and run summary (incl. cost) |

A budget guard stops any run that would push total logged spend past $20.

## Data sources and credits

- Imagery: NASA GIBS / Worldview (`GOES-West_ABI_GeoColor`, `MODIS_Terra_CorrectedReflectance_TrueColor`),
  courtesy of NASA EOSDIS. The GOES-18 Hawaiʻi GeoColor sector from NOAA/NESDIS/STAR is saved for reference.
- Fire detections: NASA FIRMS (live via the Kahu Ola public API, historical via GIBS thermal-anomaly layers).
- Haze signal: NOAA GOES-18 ADP, via the Kahu Ola public API (an estimate, not an official product).
- Wind: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0), forecast and historical archive APIs.

## Layout

```
src/            pipeline.py (chain), models.py (Meta API stages), sources.py (data),
                aggregate.py (verdict rule), geo.py, common.py
tests/          pytest suite (no credits spent)
scripts/        Step-3 smoke tests, effort_ab.py (classifier reasoning-effort A/B)
demo/           curated runs with compressed images
out/            generated outputs and costs.csv
data/raw/       downloaded frames (git-ignored)
```

## License

MIT. See [LICENSE](LICENSE).
