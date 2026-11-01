# Video script: Smoke or Vog? (exactly 3:00)

**Format:** screen capture of https://smoke-or-vog.pages.dev (1920×1080; the phone shot in iPhone
emulation at 390 px) with an AI voice-over (OpenAI TTS). Produced by `scripts/video/make_video.py`,
which reads the scene table below.
**Rule:** show only hackathon-built features. Kahu Ola is named only as the data source.
**Voice-over note:** the narration is AI-generated, one clip per scene, at about 140 words per
minute, with phonetic hints for Hawaiian names (captions keep the correct spelling). If Long
re-records any scene himself, speak slowly; each scene can be re-recorded on its own and dropped
in at its timestamp.

| # | Time | On screen (action) | Voice-over (Long) |
|---|---|---|---|
| 1 | **0:00–0:15** (15 s) | Hook. Full-screen Kīlauea replay image (Oct 17, 2026): the haze trailing south of Hawaiʻi Island. Slow push-in. | "In Hawaiʻi, haze can mean a volcano, or a fire. Satellite products can't tell the difference. Built by Long, from Wailuku, Maui, to do exactly that." |
| 2 | **0:15–0:27** (12 s) | The site with the Kīlauea replay open. The purple banner reads "Replay of a past event. Not a current alert." Step 1 "True-color image". | "Here's a real event: a Kīlauea vog plume on October 17. Replays are clearly labelled, never a current alert. Step one: the true-color satellite image." |
| 3 | **0:27–0:42** (15 s) | Step 3 "Muse Spark boxes": the zoomed box and point on the plume. | "Step three: Muse Spark looks at the image and boxes the haze. At satellite scale, text prompts found nothing. Spark's eyes make the next step work." |
| 4 | **0:42–1:02** (20 s) | Step 4 "SAM masks": red pass-1 and cyan pass-2 outlines. Point at the table "16,446 → 22,607 px · kept pass 2 (1.37×)". | "SAM 3.1 turns that box into a pixel mask. A second pass widens the box by fifteen percent to catch faint tails, and is kept only if the mask stays whole and off land. Here it grew by a third." |
| 5 | **1:02–1:32** (30 s) | Step 5 "Agent trace". Scroll slowly through E1–E7: get_volcano_status, get_wind, distance_to_vents, land_fraction, get_firms, then round 2: distance_to_vents with wind_from_deg, get_wind at the summit. Pause on the green note "Every evidence line cites a tool result." | "This is the agent. Muse Spark chooses its own tools: the official USGS volcano status for that hour, the wind, NASA fire detections with summit glow filtered out, and the plume's distance to the vents. In round two it re-measures using the wind it just fetched. Every claim must cite a tool result, or the verdict is thrown out." |
| 6 | **1:32–1:52** (20 s) | Step 6 "Verdict and evidence": "Likely vog from Kīlauea (82%)", evidence with [E…] citations, the USGS notice link. Then the Maui replay at step 6: "Likely wildfire smoke (90%)". | "Verdict: vog from Kīlauea, eighty-two percent, every reason linked to its source. On the 2023 Maui fires: wildfire smoke, traced to the Kula fire cluster. USGS confirms both volcanoes were quiet." |
| 7 | **1:52–2:07** (15 s) | Mauna Loa replay, step 6: "Haze seen, source not confirmed", with the unconfirmed line "vog_mauna_loa 62%". | "When evidence is weak, it says so. Mauna Loa, 2022: the vents were under cloud. The right answer reaches sixty-two percent, below our bar, so it stays uncertain." |
| 8 | **2:07–2:27** (20 s) | Kīlauea, step 7 "Alerts". Click through the English, Tiếng Việt and ʻŌlelo Hawaiʻi tabs. Zoom in on "Official guidance (quoted)", with the source link and "(verbatim)" / "machine-translated". | "Alerts come in five languages. Health guidance is never chosen or written by AI: each result maps to fixed lines from the Department of Health and EPA, quoted word for word. The AI only translates, and says so." |
| 9 | **2:27–2:40** (13 s) | Scroll to the top: the Live status line ("Live · … · No haze plume detected · mostly cloudy · last checked … min ago"). | "And when there's nothing, it says so. The live scan runs every daylight hour. Right now: no plume, mostly cloudy, with the scan time." |
| 10 | **2:40–3:00** (20 s) | "How it works": the three Meta models. Then the phone view (390 px), scrolling. End card (last 4 s): "Smoke or Vog? · smoke-or-vog.pages.dev · Satellite estimate, not an official warning · AI voice-over (OpenAI TTS)". | "Muse Spark for vision and the agent, SAM 3.1 for masks, Muse Image for backgrounds. Everything you saw was built during this hackathon; Kahu Ola's public API is the only pre-existing input. Smoke or Vog." |

**Total:** 15 + 12 + 15 + 20 + 30 + 20 + 15 + 20 + 13 + 20 = **180 s**.

## Recording checklist

- Clear `localStorage` so the site opens in English. Switch to Tiếng Việt only in scene 8.
- Pre-load each replay once so images are cached and no spinners show.
- Scene 9 shows whatever the live scan says at recording time. If a plume happens to be live,
  adjust the line to describe it ("Right now: …"), keeping the scan time.
- Keep the "Satellite estimate, not an official warning." footer or end card visible in the final frame.
- The end card also credits the narration: "AI voice-over (OpenAI TTS)".
- Don't show the terminal, the API key, or any Kahu Ola interface.
