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

## Results (2026-10-31)

| Case | Spark localize | SAM (box / box+point) | SAM concepts | Verdict |
|---|---|---|---|---|
| Kīlauea 2026-10-17 | 1 plume S of Hawaiʻi Island | 1 mask each, 95–99% inside Spark box | 0 / 0 / 0 | **vog_kilauea 0.80** |
| Maui 2023-08-08 | 3 plumes | 3 masks each | 0 / 0 / 0 | **uncertain 0.55** overall: #2 wildfire_smoke 0.88 (Kula fire, 22 km upwind); #1 Kona-side veil uncertain 0.45; #3 faint Oʻahu streak smoke 0.62 |
| Live 2026-10-31 21:40Z | 0 plumes (mostly cloudy) | skipped | 0 / 0 / 0 | no_plume (uncertain 0.0) |

**Which SAM prompt style works best:** box prompts from Muse Spark. In all three cases, the concept
prompts "smoke", "volcanic plume" and "haze" returned nothing on 1 km satellite imagery, and so did
"haze plume" in Step 3. Box+point usually gave slightly higher SAM confidence than box alone and is
used for classification.

## Known issues / next fixes

1. **Spark boxes can be too tight.** On the Kīlauea case the box cut off the plume's western tail,
   so the mask is smaller than the visible haze. Try padding the box, asking for the full extent,
   or splitting a plume into head and tail objects.
2. **Volcanic heat in historical FIRMS.** GIBS thermal anomalies include the summit glow, so the
   summits show up as "fire clusters". Tag clusters within about 5 km of a summit as
   `volcanic_thermal` (Kahu Ola live already suppresses these zones).
3. **No ground truth for Maui plume #1.** Kīlauea was paused on 2023-08-08, so `uncertain` looks
   right. Check against HVO status and the Kohala fire timeline before we use it in the demo.
4. **The overall verdict follows the biggest plume.** When there are several plumes, consider
   a `mixed` headline, or report each plume first.
5. **Unexercised path:** ADP→candidate reprojection (Mercator mask → our grid). Today's ADP was
   empty, so it's untested on a real detection.
6. **Mauna Loa** has no test case yet. Add one, such as the 2022-11/12 eruption with MODIS daily.

## Next steps (waiting for go-ahead)

- [ ] Fixes 1–2 above, then rerun all three cases.
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
  Higher effort cost more tokens and lowered accuracy, and `max` truncated answers. We use
  `reasoning.effort="medium"` for localization and classification. Testing `low` is a cheap
  experiment.

## Constraints

- New code only. Kahu Ola is used only through its public API, as an external data source.
- Never print, log, or commit `MODEL_API_KEY`.
- Output is advisory, and every card points to official sources.
