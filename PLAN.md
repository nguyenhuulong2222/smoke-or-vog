# PLAN: Smoke or Vog?

Deadline: **Tue Nov 4, 2026, 4:00 pm HST**. Budget: **< $20 total** (spent so far: see `out/costs.csv`).

## Done

- **Step 1–3:** repo, venv, and smoke tests for all four Meta calls.
- **Repo:** private GitHub repo `nguyenhuulong2222/smoke-or-vog`; `.env.local` verified absent.
- **Imagery (decision B):**
  - **Live: NOAA STAR CDN.** `https://cdn.star.nesdis.noaa.gov/GOES18/ABI/SECTOR/hi/GEOCOLOR/`,
    filename `YYYYDDDHHMM_GOES18-ABI-hi-GEOCOLOR-{300,600,1200,2400}.jpg` (DDD = day of year),
    plus `latest.jpg`. New frame every 10 min, about 15 min latency. Covers all main islands,
    but they fill only the middle of a wide ocean view. The JPEG carries no georeferencing,
    so we save it for reference only.
  - **Pipeline image: NASA GIBS WMS `GOES-West_ABI_GeoColor`** (GOES-18). It comes in EPSG:4326
    on exactly the Kahu Ola ADP box (lon −161…−154, lat 18…23) at 1400×1000 (about 0.5 km/px),
    so lat/lon maps linearly to pixels for summits, FIRMS, wind and ADP. 10-min cadence,
    about 45–60 min latency, about 80 days of history.
    GIBS capabilities lag and disagree between requests, so the latest time is found by probing
    tiles (transparent = not yet available).
  - **Historical:**
    - Kīlauea 2026-10-17 21:00Z: GOES-West GeoColor from GIBS. Works.
    - Maui 2023-08-08: older than GIBS keeps GOES, so we use `MODIS_Terra_CorrectedReflectance_TrueColor`
      (daily, about 10:30 local overpass). Works. Aqua has a swath gap over the islands that day.
      VIIRS NOAA-20 is a backup.
    - NOAA NODD (raw ABI on S3) is not needed yet.
  - **Kahu Ola ADP:** live only. Historical frame keys return 404.
- **Detection chain (decision C):** `src/pipeline.py`, 5 stages, output per run in `out/runs/`.
- **Round 2:** per-plume aggregation rule, FIRMS volcanic-zone exclusion, two-pass SAM,
  Mauna Loa case, offline pytest suite (29 tests), and the effort A/B.

## Results: round 2 (2026-10-31, after fixes 2 and 3a–e)

| Case | Per-plume verdicts | Overall (≥0.70 rule) | Expected |
|---|---|---|---|
| Kīlauea 2026-10-17 21:00Z (GOES-W) | #1 vog_kilauea 0.75 | **vog_kilauea 0.75** | vog_kilauea ✅ |
| Maui 2023-08-08 (MODIS Terra) | #2 wildfire_smoke 0.88; #1 vog_kilauea 0.65 (unconfirmed); #3 uncertain 0.45 | **wildfire_smoke 0.88** | wildfire_smoke ✅ (round 1 said "uncertain") |
| Mauna Loa 2022-12-01 (MODIS Aqua) | #1 vog_mauna_loa 0.62 (unconfirmed) | **uncertain** | vog_mauna_loa ⚠️ right class, below 0.70 |
| Live 2026-10-31 21:40Z (GOES-W) | no plume (mostly cloudy) | **uncertain / no_plume** | n/a |

**Two-pass SAM (3b):** pass 2 was kept for every plume (1.11–1.50× larger, coherence ≥ 0.99).
Kīlauea tail before/after: the plume extent grew from lon −155.89…−155.03 / lat 18.30…19.04
(5,336 km², 123 km) to −156.27…−154.96 / 18.23…19.25 (9,122 km², 179 km). That captures the
western tail and reaches the south coast. See `demo/kilauea_20261017/tail_before_after.jpg`.

**Effort A/B (3e)**, classifier only, 6 samples per level over 3 cases (`demo/effort_ab.json`):

| effort | key plume correct | overall correct | mean key conf | mean cost | mean output tokens |
|---|---|---|---|---|---|
| low | 5/6 | 4/6 | 0.665 | $0.0100 | 1,625 |
| medium | 6/6 | 4/6 | 0.760 | $0.0191 | 3,502 |

→ **We keep `medium`.** `low` is cheaper but scores worse. It missed Mauna Loa once (uncertain
0.45), and on Maui it confirmed plume #1 as vog_kilauea at 0.72, which is doubtful because
Kīlauea was paused in August 2023. The saving is about $0.009 per run.

**SAM prompt style:** boxes from Spark, refined in two passes. The concept prompts "smoke",
"volcanic plume" and "haze" still return 0 masks in all 4 cases.

## Known issues / next fixes

1. **Pass-2 land spill:** on Mauna Loa, pass 2 pulled in Molokaʻi and nearby cloud, yet passed
   every check (coherent, under 3× growth). Add a land/cloud check, for example rejecting pass 2
   if it adds more than X% bright or land pixels.
2. **"Active vent" overclaim:** the classifier now reads summit glow as an active vent. On Maui
   2023-08-08 that pushed plume #1 toward vog_kilauea (0.65), but Kīlauea was paused and only
   residual heat remained. Phrase it as "thermal signal at summit", and add HVO eruption status
   (erupting / paused) as context.
3. **Mauna Loa confidence 0.62:** the source area was under cloud, and the plume was 320 km
   downwind over the Oʻahu channel. Options: a clearer date (try 2022-11-29 Terra, or VIIRS
   2022-12-02), or an SO₂ layer from GIBS as extra evidence. Both Kīlauea and Mauna Loa were
   erupting, so a cautious answer is defensible.
4. **The upwind end uses 10 m wind**, which isn't plume-level transport. Consider 850 hPa wind
   from Open-Meteo.
5. **NE-rift fissure detections** (Mauna Loa 2022) stay in the fire clusters, as designed, and are
   labeled with `nearest_summit_km`. The classifier handled this correctly ("indicating lava").

## Next steps (waiting for go-ahead)

- [ ] Fixes 1–2, re-run the 4 cases.
- [ ] Alerts: Muse Image card per affected district, EN first, then ʻŌlelo Hawaiʻi if quality
      holds. Every card includes "estimate, not official" and the IVHHN link.
- [ ] Demo surface: static page with the latest verdict, overlay, stage outputs and card.
- [ ] Submission: README polish, demo video, make the repo public.

## Reference repo (decision E)

`/Volumes/Crucial1TB/reference/ai-experiments` (commit e3c0b4b), read-only.
- It has **no LICENSE file**, which means all rights reserved, so we **reused no code**.
- `experiments/meta-hackathon-muse` covers Muse Spark Open and Glimmer on Fireworks. It has
  nothing on SAM 3.1 or image input.
- One useful tip: in its effort sweep, Muse did best at `reasoning_effort=low` on simple tasks.
  Higher effort cost more tokens and lowered accuracy, and `max` truncated answers. We tested `low` against
  `medium` for the classifier; `medium` won (see the effort table above).

## Constraints

- New code only. Kahu Ola is used only through its public API, as an external data source.
- Never print, log, or commit `MODEL_API_KEY`.
- Output is advisory, and every card points to official sources.
