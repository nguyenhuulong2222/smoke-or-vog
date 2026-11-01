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
| 2 | **0:15–0:24** (9 s) | The Kīlauea replay open, with the banner "Replay of a past event. Not a current alert." and step 1. | "Here's a real event: a Kīlauea vog plume on October 17, labelled as a replay, never a current alert." |
| 3 | **0:24–0:38** (14 s) | Step 3 "Muse Spark boxes" (box and point on the plume), then step 4 SAM masks: pass-1 red and pass-2 cyan outlines. | "Muse Spark looks at the image and boxes the haze. SAM 3.1 turns each box into a pixel mask, and a wider second pass catches the faint tail." |
| 4 | **0:38–0:56** (18 s) | Step 4, Time-lapse: SAM 3.1 video outline and drift path over 3 hours of GOES-West frames. Then the motion line: "drift toward 214°, 18 km/h · wind toward 251° · agrees". | "New: SAM 3.1 video tracks the plume through three hours of ten-minute GOES-West frames. It drifts south-west at about eighteen kilometres an hour, and the tracked drift roughly agrees with the wind." |
| 5 | **0:56–1:15** (19 s) | Step 5 "Agent trace": scroll through the tool calls (USGS status, wind, distances, land, FIRMS, track_plume). Pause on "Every evidence line cites a tool result." | "Muse Spark is the agent. It chooses its own tools: the official USGS status, the wind, fire detections, distance to the vents, and the plume's measured motion. Every claim must cite a tool result, or the verdict is thrown out." |
| 6 | **1:15–1:29** (14 s) | Step 6: "Likely vog from Kīlauea (82%)" with cited evidence. Then the Maui replay: "Likely wildfire smoke (90%)". | "Verdict: vog from Kīlauea, eighty-two percent, every reason linked to its source. On the 2023 Maui fires: wildfire smoke, traced to the Kula fire cluster." |
| 7 | **1:29–1:47** (18 s) | Mauna Loa replay, step 6: "Haze seen, source not confirmed", then the "Second opinion (Muse Wonder)" box: Spark vog_mauna_loa 62% / Wonder uncertain 60%, "They disagree, so the verdict stays uncertain." | "Borderline calls get a second opinion. On Mauna Loa in 2022, Spark leans vog at sixty-two percent. Muse Wonder, given the same evidence, says uncertain. They disagree, so it stays uncertain." |
| 8 | **1:47–2:00** (13 s) | Kīlauea step 7 "Alerts": English card, then the Vietnamese quoted official guidance, then the ʻŌlelo Hawaiʻi card. | "Alerts come in five languages. Health guidance is never written by AI: fixed official lines, quoted word for word. The AI only translates, and says so." |
| 9 | **2:00–2:20** (20 s) | The History calendar (81 days, coloured by verdict). Then "How accurate is it?": the table with confidence intervals and base rates, and the finding "no plume never means clean air". | "We ran all one hundred sixty archived scans and checked them against ground monitors. The lesson: satellites see haze aloft, not ground air. So no plume never claims clean air, and links to the monitors." |
| 10 | **2:20–2:36** (16 s) | The Ask panel: language buttons (EN, Tiếng Việt, Tagalog with voice; Ilocano and ʻŌlelo Hawaiʻi typed, labelled), "Start recording", and an answer with "We heard" and the disclaimer. | "Ask by voice in English, Vietnamese or Tagalog, or type in Ilocano or Hawaiian. Muse Voice Transcribe hears the question, and Muse Spark answers only from the latest scan." |
| 11 | **2:36–3:00** (24 s) | "How it works": the Meta models. Then the phone view (390 px), scrolling. End card (last 4 s): "Smoke or Vog? · smoke-or-vog.pages.dev · Satellite estimate, not an official warning · AI voice-over (OpenAI TTS)". | "Muse Spark, SAM 3.1, Muse Wonder, Voice Transcribe and Muse Image, plus a Worker built with Muse Code. Everything you saw was built during this hackathon; Kahu Ola's public API is the only pre-existing input. Smoke or Vog." |

**Total:** 15 + 9 + 14 + 18 + 19 + 14 + 18 + 13 + 20 + 16 + 24 = **180 s**.

## Recording checklist

- Clear `localStorage` so the site opens in English. Switch to Tiếng Việt only in scene 8.
- Scene 4 uses the published replay's numbers (drift toward 214°, wind toward 251°, 37° apart): the voice-over says only that the drift "roughly agrees" with the wind.
- Scene 10 asks one real typed question through the voice proxy before capture, so a real answer is shown.
- Pre-load each replay once so images are cached and no spinners show.
- Keep the "Satellite estimate, not an official warning." footer or end card visible in the final frame.
- The end card also credits the narration: "AI voice-over (OpenAI TTS)".
- Don't show the terminal, the API key, or any Kahu Ola interface.
