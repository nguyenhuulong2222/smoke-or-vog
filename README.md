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

## Built during the hackathon (Oct 31–Nov 4, 2026)

Everything in this repository is new work, created during the hackathon (first commit
Oct 31, 2026, 12:16 HST). That includes the pipeline, the agentic classifier, alerts, the live
publisher, the website, tests, scripts and docs. Full list: [`docs/NEW_WORK.md`](docs/NEW_WORK.md).

**Pre-existing external inputs:** the **Kahu Ola public API** (`/api/hazards/smoke-sat`,
`/api/firms/hotspots`). It was built before the event by the same author and is used here
**read-only, as a data source**, over HTTPS like any public API. No Kahu Ola source code is in
this repository.

## The AI does not give medical advice

The system never generates health advice. Health guidance on every alert is **quoted** from
official sources stored in [`assets/health_sources.json`](assets/health_sources.json):
Hawaiʻi DOH / IVHHN for vog, EPA AirNow for smoke. Muse Spark may only **select** which
official lines to show:
- English lines are always the verbatim official text. The code discards any model wording.
- Other languages are labelled "translation of official guidance, machine-translated".
- A verifier (`alerts.verify_guidance`) rejects any guidance line that doesn't trace to the
  source file, and it is covered by tests.

The model writes only a short situation summary (what the satellite shows, where and when) and
the "satellite estimate, not an official warning" disclaimer.

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
.venv/bin/python -m src.alerts out/runs/<run_id>          # stage 5: 5-language alerts + cards
.venv/bin/python -m src.pipeline --case kilauea_20261017 --classifier both  # agent vs fixed classifier
.venv/bin/python -m pytest                                # 84 offline tests, Meta API mocked
```

**Overall verdict rule (safety first):** each plume is classified separately. The overall
verdict is the most hazardous class confirmed at confidence ≥ 0.70, in the order
`wildfire_smoke > vog_* > dust > cloud`. Plumes below 0.70 are listed as *unconfirmed*.
The verdict is `uncertain` only when no plume reaches 0.70 (`src/aggregate.py`).
A **data-quality gate** also applies. A plume whose mask swallows an island, or is more than
50% land (Natural Earth 10m land), can't be confirmed at any confidence. It's listed as
unconfirmed with the reason.

*Intended behaviour (Mauna Loa test case, 2022-12-01): `uncertain`.* The vent area was under
cloud, the visible haze was about 320 km downwind near Oʻahu, and Kīlauea was erupting at the
same time. Across runs the classifier gave `vog_mauna_loa` 0.62, then `uncertain` 0.38. One run
reached 0.70, but only because SAM's "plume" was 68% of Hawaiʻi Island. The data-quality gate now
blocks that case. We don't lower the 0.70 threshold to make a test case pass. When the source
can't be seen, honest uncertainty is the correct output.

**SAM is run in two passes:** pass 1 uses the Muse Spark box and point. Pass 2 re-prompts with
the pass-1 mask's bounding box plus a 15% margin. Pass 2 is kept only if it's larger and still
coherent, with no ocean-wide spill.

**Agentic classification (`--classifier agent|both`):** Muse Spark calls our tools through
native tool calling. It decides which tools to call and in what order, then classifies. The tools:
- `get_wind(lat, lon, time)`
- `get_firms(bbox, date)` (summit glow filtered into `volcanic_thermal`)
- `get_volcano_status(time)` (USGS HVO)
- `distance_to_vents(plume_id, wind_from_deg)` (from the SAM mask)
- `land_fraction(plume_id)`

Every evidence item must cite a tool result (`E1`, `E2`, …), and a verdict that cites nothing,
or cites a failed or unknown call, is rejected. The fixed classifier stays as the fallback. The
full trace is saved to `04_agent_trace.json` and shown on the site as step 5 "Agent trace". On
the four cases, the agent's overall verdicts matched the fixed classifier's. It gave higher
confidence on Kīlauea (0.82 vs 0.70) and named the right class on Mauna Loa (`vog_mauna_loa`
0.62, still unconfirmed), for about $0.01 more per plume run. Live scans use agent mode.

**Summit glow is not fire:** FIRMS detections inside the Kīlauea and Mauna Loa summit calderas
(Kahu Ola `volcanic_zone` flag, or the same caldera boxes for historical data) are reported as
`volcanic_thermal` and kept out of the fire clusters. Glow alone is not treated as proof of
emissions.

**Volcano status is official:** each run fetches the USGS HVO notice valid at the image time
(HANS public search API). That gives the alert level, aviation color, an
`erupting = yes | no | episodic_pause | unknown` flag, the activity summary, and the notice
permalink, all stored in `00_context.json` and `04_classify.json`. Example: on 2023-08-08 HVO
reported "Kīlauea volcano is not erupting", so Maui's haze is no longer attributed to Kīlauea.

## Stage 5: alerts

`python -m src.alerts out/runs/<run_id>` writes `alerts/alerts.json`, `alerts/background.png`
and `alerts/alert_{en,vi,ilo,tl,haw}.png`:

- **Muse Spark** writes one short alert per language: English, Vietnamese, Ilocano, Tagalog
  and ʻŌlelo Hawaiʻi. Verdicts covered: `wildfire_smoke`, `vog_kilauea`, `vog_mauna_loa`, `dust`,
  `uncertain`, `no_plume`.
- **Health guidance comes only from official text** in
  [`assets/health_sources.json`](assets/health_sources.json): Hawaiʻi DOH / IVHHN for vog, EPA
  AirNow for smoke and particles. The model picks excerpts by index. The code rejects any
  reference outside the verdict's sources, and attaches the verbatim English excerpt and source
  URL to every action.
- **Every alert carries** the confidence, "Satellite estimate, not an official warning." (in the
  alert's language and in English), and the official link.
- **Translation labels:** non-English alerts are marked `machine_translated`. Ilocano, Tagalog
  and ʻŌlelo Hawaiʻi are also marked `needs_community_review`, and the cards show both badges.
- **Cards:** Muse Image paints only a text-free background (the prompt says "no text"). All text
  is drawn by PIL in bundled Noto Sans (SIL OFL), which renders Vietnamese diacritics and the
  ʻokina/kahakō: "Kaʻū", "Hawaiʻi", "khói", "sương mù núi lửa"
  ([`demo/font_check.png`](demo/font_check.png)).
- **Affected places** are towns within 15 km of the plume mask (`plume_<id>_mask.png`).

## Stage 6: public demo

- **Site** (`site/`): a static page with no build step, mobile-first (works at 390px), in
  English and Vietnamese. It reads only `site/data/**` JSON and images, and has no API key or
  API calls. A CSP limits it to its own origin plus Google Fonts. It has three parts:
  - **Live now:** the latest scan, or an honest "no plume / too cloudy" with the scan time.
  - **Replays:** Kīlauea 2026-10-17, Maui 2023-08-08, and Mauna Loa 2022-12-01 as the
    honest-uncertainty example.
  - **A six-step view for each run:** true-color image → ADP → Muse Spark boxes → SAM pass 1 vs
    pass 2 → verdict and evidence (wind, distance to vents, FIRMS, USGS status with link) →
    alerts in 5 languages with cards.
- **Replay data:** `python -m src.sitedata out/runs/<run> site/data/replays/<slug> --mode replay`
  (committed).
- **Live data:** `.github/workflows/live.yml` runs `python -m src.live_publish` hourly during
  Hawaiʻi daylight. `MODEL_API_KEY` is an Actions secret, used only server-side. The job:
  - skips night hours and unchanged frames (no spend);
  - drops the SAM concept prompts;
  - writes alerts only for confirmed hazards;
  - stores its cost ledger and last live run on the `live-data` branch;
  - deploys `site/` to Cloudflare Pages project `smoke-or-vog`.
  When total logged spend reaches **$15**, it publishes `budget_stop` and disables its own schedule.
- **Gate:** the job runs only if the repo variable `LIVE_ENABLED` is `true`. Required secrets:
  `MODEL_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
- **Local preview:** `python -m src.live_publish --index-only && cd site && python3 -m http.server`.

## Known limitations

- Affected places are approximate: a fixed town list, 15 km from a satellite-derived mask.
  This doesn't measure ground-level air quality.
- Translations are machine-made. Ilocano, Tagalog and ʻŌlelo Hawaiʻi need review by community
  speakers before any public use.
- SAM concept prompts ("smoke", "haze", "volcanic plume") return nothing on 1 km satellite
  imagery, so segmentation relies on Muse Spark's boxes.
- The upwind end uses 10 m wind, not plume-level transport.
- Verdicts near 0.70 can flip between runs (model sampling). The safety rule handles this by
  reporting `uncertain` rather than guessing.

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
- Volcano status: USGS Hawaiian Volcano Observatory notices via the HANS public API.
- Land polygons: [Natural Earth](https://www.naturalearthdata.com/) 10m land (public domain),
  rasterised to `assets/land_hawaii_1400x1000.png` by `scripts/build_land_mask.py`.
- Health guidance excerpts: Hawaii Interagency Vog Information Dashboard (IVHHN / Hawaiʻi DOH),
  <https://vog.ivhhn.org/>; U.S. EPA AirNow, <https://www.airnow.gov/>.
- Font: Noto Sans, © The Noto Project Authors, SIL Open Font License (`assets/fonts/OFL.txt`).

## Layout

```
src/            pipeline.py (chain), models.py (Meta API stages), sources.py (data),
                aggregate.py (verdict rule), land.py, alerts.py (stage 5), geo.py, common.py
assets/         health_sources.json, land mask, fonts
tests/          pytest suite (no credits spent)
site/           static demo site (data/replays committed; data/live built by the workflow)
.github/        live.yml: hourly server-side scan + Pages deploy (gated by LIVE_ENABLED)
scripts/        Step-3 smoke tests, effort_ab.py (classifier reasoning-effort A/B)
demo/           curated runs with compressed images
out/            generated outputs and costs.csv
data/raw/       downloaded frames (git-ignored)
```

## License

MIT. See [LICENSE](LICENSE).
