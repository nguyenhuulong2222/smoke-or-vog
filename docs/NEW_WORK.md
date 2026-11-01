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
| Plume motion tracking (SAM 3.1 video over GOES-West frames) | `src/track.py` |
| Muse Wonder second-opinion adjudicator (borderline calls; can only keep or lower a verdict) | `src/adjudicate.py` |
| Archive backfill, ground-monitor validation (pre-registered in `docs/VALIDATION.md`), History calendar data | `src/backfill.py`, `src/groundtruth.py`, `src/validate.py`, `src/history.py` |
| Safety aggregation (per-plume verdicts, ≥ 0.70 rule, unreliable-mask gate) | `src/aggregate.py` |
| Multilingual alerts and cards (fixed, quoted official guidance per verdict; text-free Muse Image backgrounds; PIL rendering) | `src/alerts.py`, `assets/health_sources.json`, `assets/translation_overrides.json` |
| Live publishing and static-site data | `src/live_publish.py`, `src/sitedata.py`, `.github/workflows/live.yml`, `.github/dependabot.yml` |
| Voice / typed questions proxy (Cloudflare Worker), **built with Muse Code** (`muse exec`, headless, from `worker/voice/SPEC.md`). Muse Code wrote `wrangler.jsonc`, `src/lib.js`, `src/index.js` and `test/lib.test.js` (68 tests). Our review then made these changes: moved the per-IP rate limit and daily cap **before** the paid transcription call, made missing bindings or a bad cap fail closed, stripped `<`/`>` from questions, raised the answer token budget (reasoning used up 600 tokens), renamed a misleading status field, and added `test/handler.test.js` (8 mocked-fetch tests) | `worker/voice/` |
| Ask panel (mic recording → 16 kHz WAV in the browser, typed fallback) | `site/app.js` |
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

- **Meta Model API:** `muse-spark-1.3`, `sam-3.1`, `muse-image-1.0`, `muse-wonder-1.0`,
  `muse-voice-transcribe-1.0`; `meta-sam-parser` (pip). **Muse Code** CLI (`muse` 1.4.14), installed
  from the official `dev.meta.ai/install.sh` after inspecting it, and used to build `worker/voice/`.
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
