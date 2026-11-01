# New-work disclosure

**Project:** Smoke or Vog? · Meta Global AI Developer Hackathon
**Hackathon period:** Oct 31 – Nov 4, 2026 (HST)
**Repository created:** Oct 31, 2026, 12:16 HST (first commit `33a7b18`)

## Built during the hackathon

Everything in this repository is new work, created during the hackathon period:

| Area | Files |
|---|---|
| Detection pipeline (imagery, ADP, Muse Spark localisation, SAM 3.1 two-pass segmentation, classification) | `src/pipeline.py`, `src/models.py`, `src/sources.py`, `src/geo.py`, `src/land.py`, `src/common.py` |
| Agentic classifier (Muse Spark native tool calling, citation-verified evidence) | `src/agent.py` |
| Safety aggregation (per-plume verdicts, ≥ 0.70 rule, unreliable-mask gate) | `src/aggregate.py` |
| Multilingual alerts and cards (quoted official guidance, text-free Muse Image backgrounds, PIL rendering) | `src/alerts.py`, `assets/health_sources.json`, `assets/translation_overrides.json` |
| Live publishing and static-site data | `src/live_publish.py`, `src/sitedata.py`, `.github/workflows/live.yml`, `.github/dependabot.yml` |
| Demo website | `site/` |
| Tests | `tests/` |
| Smoke tests and tools | `scripts/` |
| Documentation and demo assets | `README.md`, `PLAN.md`, `docs/`, `demo/` |
| Derived data | `assets/land_hawaii_1400x1000.png` (rasterised from Natural Earth by `scripts/build_land_mask.py`) |

Git history shows every commit from the first one, made on Oct 31, 2026. No code was copied from
any earlier project, including Kahu Ola.

## Pre-existing external inputs

| Input | What it is | How it is used |
|---|---|---|
| **Kahu Ola public API**: `https://kahuola.org/api/hazards/smoke-sat` and `https://kahuola.org/api/firms/hotspots` | A Hawaiʻi hazard service built **before the event by the same author**. Kahu Ola source code is **not** in this repository and was not copied. | Called **read-only over HTTPS as an external data source**, like any public API: the GOES-18 ADP haze signal and metadata, and NASA FIRMS hotspots with a volcanic-zone flag. |

## Third-party data, libraries and assets (not authored by us)

- **Meta Model API:** `muse-spark-1.3`, `sam-3.1`, `muse-image-1.0`; `meta-sam-parser` (pip).
- **Data:**
  - NASA GIBS (GOES-West GeoColor, MODIS, FIRMS thermal-anomaly layers)
  - NOAA/NESDIS/STAR GOES-18 imagery
  - USGS Hawaiian Volcano Observatory notices (HANS API)
  - Open-Meteo (CC BY 4.0)
  - Natural Earth (public domain)
- **Health guidance text** (quoted verbatim, never generated): the Hawaii Interagency Vog
  Information Dashboard (IVHHN / Hawaiʻi DOH) and U.S. EPA AirNow.
- **Font:** Noto Sans (SIL OFL), bundled in `assets/fonts/`. The site uses Newsreader from Google
  Fonts.
- **Python packages:** `requirements.txt`.
- **Reference consulted:** `sinanuozdemir/ai-experiments` (it has no license, so no code was
  reused).
