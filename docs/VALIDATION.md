# Validation against ground monitors

*The method below was fixed and committed **before** any validation result was computed. Results
are appended in the "Results" section by `python -m src.validate`. The thresholds were not tuned
afterwards.*

## Question

When Smoke or Vog? says *vog*, does SO₂ rise at ground monitors under or downwind of the plume?
When it says *wildfire smoke*, does PM2.5 rise? When it says *no plume*, is the air clean? And
what does *uncertain* look like on the ground?

## Data

- **Verdicts:** every archive scan from the backfill (`src/backfill.py`). These are GOES-West
  GeoColor scans at 11:00 and 14:00 HST, for each day in the GIBS archive window (about 81 days),
  run through the full pipeline in agent mode with motion tracking. Every scan is included: there
  is no filtering by verdict, quality or outcome.
- **Ground truth:** hourly SO₂ and PM2.5 from the public AirNow hourly files
  (`files.airnowtech.org`, UTC). Stations are the Hawaiʻi DOH and National Park Service monitors.
  - SO₂: Hawaiʻi Volcanoes NP, Hilo, Kona, Pāhala, Ocean View, Waikoloa, Mountain View, Kapolei,
    Honolulu.
  - PM2.5: Hilo, Kona, Pāhala, Ocean View, Waikoloa, Mountain View, Honolulu, Sand Island, Kīhei,
    Kahului.
  - AirNow data are preliminary, not the final certified record.

## Rules (pre-registered)

1. **Unit:** one scan. The scan's verdict is the published **overall** verdict (the ≥ 0.70
   safety rule): `vog` (`vog_kilauea` or `vog_mauna_loa`), `smoke` (`wildfire_smoke`), `no_plume`,
   or `uncertain` (everything else).
2. **Relevant stations:**
   - `vog` / `smoke`: stations within **20 km** of the headline plume's SAM mask.
   - `uncertain`: stations within 20 km of any plume mask; if there is no mask, all stations.
   - `no_plume`: all stations.
   - A scan with no relevant station reporting the pollutant is counted as **"no monitor
     coverage"** and kept out of the rates (but reported).
3. **Window:** hourly values from **T − 3 h to T + 3 h**, where T is the scan time.
4. **Baseline:** for each station and pollutant, the median and MAD of all downloaded hours (the
   18–03 UTC hours of every day in the window).
5. **Elevated:** the maximum in the window is at least `median + max(5, 3 × 1.4826 × MAD)` (ppb
   for SO₂, µg/m³ for PM2.5). Values at or above the EPA AQI "Unhealthy for Sensitive Groups"
   breakpoint (SO₂ ≥ 76 ppb, PM2.5 ≥ 35.5 µg/m³) always count as elevated.
6. **Agreement:**
   - `vog`: SO₂ elevated at ≥ 1 relevant station.
   - `smoke`: PM2.5 elevated at ≥ 1 relevant station.
   - `no_plume`: neither SO₂ nor PM2.5 elevated at any station.
   - `uncertain` is not scored; its ground readings are reported to show what the model was
     unsure about.
7. **Context (base rate):** for the same relevant stations, the share of all **other** scans
   where SO₂ (or PM2.5) was elevated. A verdict is only informative if its agreement rate beats
   this base rate.
8. **Uncertainty:** 95% Wilson intervals on every rate. The samples are small and are reported as
   counts, not just percentages.

## Known limits (stated in advance)

- **Coverage:** most Kīlauea plumes drift south-west over the ocean, where there are no monitors,
  so many vog verdicts will have **no monitor coverage**. That is a limit of the monitoring
  network, not evidence either way.
- **Column vs ground:** satellites see the whole air column; monitors see the air at ground level.
  A plume aloft can pass over a monitor without raising its readings.
- **Daylight only:** two scans per day, both in daylight.
- **Missing scans:** five archive slots were missing in GIBS and are not run.

## Results

*(appended by `python -m src.validate`)*
