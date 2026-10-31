# PLAN: Smoke or Vog?

Deadline: **Tue Nov 4, 2026, 4:00 pm HST**. Today: Sat Oct 31.

## Done (Step 1–3)

- Repo, venv, deps, `.env.local` key handling.
- I read the official docs (Quickstart, Auth, Models, Pricing/limits, Image understanding,
  Structured output, Media segmentation, SAM section, Image generation). Request shapes
  in `scripts/` follow those docs.
- Smoke tests passed for all four calls: `muse-spark-1.3`, `sam-3.1`, `muse-spark-1.3`
  vision with json_schema, and `muse-image-1.0`. Total spend $0.0386.

## Findings that shape the design

1. **Kahu Ola frames are mask overlays, not imagery.** `frame_url` returns a 384×293 RGBA
   PNG that is transparent wherever there's no haze. When `haze_pixels=0` (every frame on
   Oct 31 from 09:50Z to 21:50Z), the frame is blank. Running SAM on a mask is close to
   pointless because the mask is already a segmentation.
   → We need true-color context: pull GOES-18 GeoColor/true-color for the Hawaiʻi sector
   directly from NOAA public sources and use the Kahu Ola JSON (state, haze_pixels,
   coverage polygon, scan time) as the detection signal and metadata.
2. **SAM with "haze plume" found nothing on a real MODIS plume image.** With "island" on
   the same image, SAM returned 5 accurate masks, so the client, parser, mask decoding, and
   overlay all work. Diffuse haze isn't a "concrete object" in SAM's terms.
   → Try concrete phrases ("smoke plume", "gray haze", "volcanic plume"). Or let Muse Spark
   localize the haze first (perception grounding, 0–1000 boxes) and pass the box to SAM as an
   object prompt via `build_object_prompt`.
3. **Muse Spark vision is grounded and honest.** On the blank frame it said "no haze" with
   0.99 confidence and invented nothing. On the MODIS image it found the translucent veil and
   the thermal hotspot. It attributed the haze to Kīlauea, but the image shows the **2022
   Mauna Loa** eruption. My prompt only offered Kīlauea or fire.
   → Add `mauna_loa_vog` to the enum and feed the active-volcano status (USGS HVO) into the
   prompt.
4. **Muse Image renders ʻokina/kahakō correctly** ("Kaʻū") with `reasoning_strength: low`
   and search turned off. That's $0.01 per card.

## Next steps (not started; waiting for go-ahead)

- [ ] Data in: Kahu Ola smoke-sat JSON, NOAA GOES-18 true-color tile for the Hawaiʻi
      sector, and (if time) trade-wind direction + HVO volcano status.
- [ ] Interpret: one Muse Spark call returns the JSON verdict (source, districts affected,
      confidence, caveats, guidance level). Optional SAM pass for a highlighted overlay.
- [ ] Alert: Muse Image card per affected district, EN first, then ʻŌlelo Hawaiʻi
      if quality holds. Always include "estimate, not official" and the IVHHN link.
- [ ] Demo surface: static page with the latest verdict + card + overlay.
- [ ] Budget guard: keep logging every call to `costs.csv` and set a hard per-run cap.
- [ ] Submission: README polish, demo video, repo public.

## Constraints

- New code only. No Kahu Ola source; its public API is an external data source.
- Never print, log, or commit `MODEL_API_KEY`.
- Haze output is advisory, and every card points to official sources.
