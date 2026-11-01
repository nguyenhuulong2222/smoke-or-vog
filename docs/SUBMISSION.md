# Smoke or Vog? (submission draft)

**One line:** A satellite haze explainer for Hawaiʻi. It finds a haze plume, works out whether
it's volcanic vog or wildfire smoke, shows every step of its reasoning, and quotes official
health guidance in five island languages, without inventing advice.

**Live demo:** https://smoke-or-vog.pages.dev (mobile-first, English / Tiếng Việt)
**Code:** github.com/nguyenhuulong2222/smoke-or-vog (made public at submission)

---

## The problem

When the sky over Hawaiʻi turns hazy, people ask two questions: *is this vog from Kīlauea or
smoke from a wildfire?* and *what should I do?* The answers differ. Vog is sulfur dioxide and
sulfate particles from a volcano. Wildfire smoke means a fire somewhere upwind, possibly near
homes, as Maui learned on Aug 8, 2023.

The satellite products people can find online don't answer the first question. NOAA's GOES-18
Aerosol Detection Product (ADP) flags hazy pixels, but it can't tell wildfire smoke from
volcanic haze. NOAA's Hazard Mapping System (HMS) smoke polygons are drawn for fire smoke and
aren't designed to identify vog. Residents end up comparing several government websites while
the haze drifts over them. Many of those residents speak Ilocano, Tagalog, Vietnamese or
ʻŌlelo Hawaiʻi at home.

## What we built

A pipeline that runs every daylight hour on the newest GOES-18 GeoColor image, and a public site
that shows each step:

1. **True-color image.** GOES-West GeoColor from NASA GIBS, on a fixed latitude/longitude grid
   over the main islands, so every later measurement is in real kilometres.
2. **Aerosol signal.** NOAA ADP via the Kahu Ola public API, used as a hint only.
3. **Find the plume (Muse Spark vision).** Muse Spark draws a box around each haze plume and
   marks a point inside it.
4. **Cut it out (SAM 3.1, two passes).** SAM turns the box and point into a pixel mask. A second
   pass widens the box by 15% to catch faint tails, and is kept only if the mask stays coherent
   and doesn't spill onto land (Natural Earth coastlines). In the published Kīlauea replay, pass 2
   grew the mask 1.37×. On an earlier Kīlauea run, it recovered a faint tail that pass 1 missed,
   taking the plume from 123 km to 179 km long.
5. **Investigate (Muse Spark agent with native tool calling).** Muse Spark decides which of our
   tools to call, and in what order:
   - `get_wind`
   - `get_firms` (NASA fire detections, with volcano summit glow filtered out)
   - `get_volcano_status` (the official USGS HVO notice valid at that hour)
   - `distance_to_vents` (from the SAM mask)
   - `land_fraction`
   - `track_plume` (measured motion from SAM 3.1 video tracking)

   Typically it calls 7–11 tools over 3 rounds. It often re-computes a plume's upwind end after
   it has fetched the wind. **Every evidence line must cite a tool result** (`E1`, `E2`, …), and
   a verdict that cites nothing is rejected. A fixed-context classifier remains the fallback.
6. **Decide safely.** Each plume gets its own verdict: `vog_kilauea`, `vog_mauna_loa`,
   `wildfire_smoke`, `dust`, `cloud` or `uncertain`. The headline is the *most hazardous* class
   confirmed at ≥ 70% confidence. Everything weaker is shown as "not confirmed". A mask that
   swallows an island can't confirm anything.
7. **Alert in five languages (Muse Spark + Muse Image).** English, Vietnamese, Ilocano, Tagalog
   and ʻŌlelo Hawaiʻi.
   - **Health guidance is never chosen or written by AI.** Each verdict maps to fixed official
     lines quoted verbatim from Hawaiʻi DOH / IVHHN (vog) or EPA AirNow (smoke). Muse Spark only
     translates them. Translations are labelled machine-translated, and Ilocano, Tagalog and
     Hawaiian are flagged for community review.
   - Muse Image paints a text-free background, and our code draws all text in a font that
     renders the ʻokina, kahakō and Vietnamese diacritics correctly.

### Results on real events

| Event | Imagery | Verdict |
|---|---|---|
| Kīlauea vog plume, Oct 17, 2026 | GOES-West GeoColor | **Vog from Kīlauea, 82%**. The agent fetched the USGS notice: the eruption episode had ended 2 h earlier. |
| Maui wildfires, Aug 8, 2023 | MODIS Terra | **Wildfire smoke, 90%**, traced to the Kula fire cluster about 21 km from the plume's upwind end. USGS showed both volcanoes not erupting. |
| Mauna Loa eruption, Dec 1, 2022 | MODIS Aqua | **Uncertain (honest).** The vents were under cloud and the visible haze was 320 km downwind. The right class (`vog_mauna_loa`, 62%) is shown but not confirmed. |
| Live, every daylight hour | GOES-West GeoColor | Mostly "no haze plume detected, mostly cloudy", stated plainly with the scan time. |

On all four cases, the agent's verdicts matched or beat the fixed classifier's on the same plumes.

## How we used Meta's models

| Model | Where | What it does |
|---|---|---|
| **Muse Spark** (`muse-spark-1.3`) | Stage 3 | Vision grounding: plume boxes and points on a 0–1000 grid, structured JSON output |
| **Muse Spark** | Stage 5 | **Agent with native tool calling** (Responses API, `previous_response_id`): chooses tools, cites every result, classifies |
| **Muse Spark** | Stage 7 | Five-language situation summaries and translations of fixed official guidance |
| **SAM 3.1** (`sam-3.1`) | Stage 4 | Box and point prompts → pixel masks, streamed and parsed with `meta-sam-parser`, two-pass refinement |
| **SAM 3.1 video** (`sam-3.1`, `input_video`) | Stage 4b | **Plume motion tracking**: a 3-hour, 10-minute GOES-West clip seeded with the plume box → per-frame masks → measured drift direction and speed and the trailing source end. The agent reads it with the `track_plume` tool and compares it with the wind. Kīlauea Oct 17: tracked 19/19 frames, drift toward 214° (fit R² 0.98), within 37° of the wind. $0.01 per clip |
| **Muse Image** (`muse-image-1.0`) | Stage 7 | Text-free card backgrounds |

**What we learned:** text prompts like "smoke", "haze" and "volcanic plume" returned no SAM
masks on 1 km satellite imagery in any case. Muse Spark's boxes made SAM work. Combining
Spark's reasoning with SAM's pixels is the core of the project.

**Cost:** about **$0.006** per scan with no plume, **$0.05–0.08** per plume scan (vision, SAM
and the agent), and about **$0.03** more when alerts are issued. The whole hackathon, including
development, cost under $2.

## Built during the hackathon (building period Oct 27 – Nov 4, 2026)

Everything in the repository is new work created during the hackathon's building period
(Oct 27 – Nov 4, 2026): the pipeline, the agentic classifier, safety rules, alerts, the live
publisher, the website, tests (100 offline, with the Meta API mocked) and docs. The repository
was created within that period, on Oct 31, 2026 (first commit 12:16 HST). See
`docs/NEW_WORK.md`.

**Pre-existing external input:** the **Kahu Ola public API** (`/api/hazards/smoke-sat`,
`/api/firms/hotspots`). It was built before the event by the same author and is used here
read-only, as a data source. No Kahu Ola code is in this project.

## Honesty and safety, by design

- **"Satellite estimate, not an official warning"** appears on every card and page, with links
  to vog.ivhhn.org and fire.airnow.gov.
- **Replays are labelled** "REPLAY · date · not a current alert" in every language, and a test
  makes sure a replay can't render without that banner.
- **No forced answers:** `uncertain` is a valid verdict, and the 70% bar is never lowered to
  make a case pass.
- **No secrets reach the browser:** the site reads published JSON only. The API key lives in
  GitHub Actions secrets, and actions are pinned to commit SHAs.
- **Budget stop:** live scanning stops itself if total spend reaches $15.

## Limitations

- **Daylight only:** true-color analysis needs daylight, so there are no night scans.
- **Approximate places:** a town counts as "near the plume" if it's within 15 km of a satellite
  mask. That isn't a measurement of ground-level air quality.
- **10 m wind:** upwind ends use 10 m wind, not plume-height transport.
- **Translations need review:** they are machine-made, and Ilocano, Tagalog and ʻŌlelo
  Hawaiʻi need community speakers before any public use.
- **Borderline verdicts can flip:** confidence near 70% can change between runs. The safety
  rule shows `uncertain` rather than guessing.

## Impact

For people in Kaʻū, Puna, Kona and Maui, the question "vog or smoke?" decides whether to close
the windows and wait, or check fire maps and maybe leave. Smoke or Vog? answers it within an
hour of the satellite pass. It shows its evidence, says "uncertain" when that's the truth, and
quotes the health agencies word for word in the languages people speak at home. The same
pattern of open satellite data, a citing agent and quoted official guidance can carry over to
any place where two hazards look alike from orbit.

This is personal for us: the author lives in Wailuku, Maui. After the hackathon, the plan is to
offer Smoke or Vog? as an opt-in layer in Kahu Ola (kahuola.org), an existing free civic
hazard map for Hawaiʻi, so residents can use it in a tool they already know. That integration
hasn't been built yet. It would follow community review of the translations and a period of
side-by-side checks against official vog and smoke advisories.
