# Video script: Smoke or Vog? (exactly 3:00)

**Format:** screen recording of https://smoke-or-vog.pages.dev plus a voice-over. 1920×1080; use
Chrome device mode (iPhone, 390 px) for the mobile shots.
**Rule:** show only hackathon-built features. Kahu Ola appears only as the named data source.
**Timing:** about 150 words per minute. Each scene's voice-over fits its time slot.

| # | Time | On screen (action) | Voice-over |
|---|---|---|---|
| 1 | **0:00–0:15** (15 s) | Full-screen GOES-West GeoColor loop over Hawaiʻi. Cut to the site header "What the satellite sees over Hawaiʻi right now". | "When the sky over Hawaiʻi turns hazy, everyone asks the same thing: is this vog from Kīlauea, or smoke from a wildfire? Government satellite products can't tell you. So we built something that can." |
| 2 | **0:15–0:30** (15 s) | Desktop. Point at the Live status line ("Live · … · No haze plume detected · mostly cloudy · last checked … min ago"). Hover "Open live run". | "Smoke or Vog runs every daylight hour on the newest GOES-18 image. Right now it's honest: no plume, too cloudy. When there's nothing to show, it says so, with the scan time." |
| 3 | **0:30–0:45** (15 s) | Click the Kīlauea replay. The purple banner reads "Replay of a past event. Not a current alert." Step 1 shows the true-color image. | "Here's a real event: a Kīlauea vog plume on October 17. Replays are clearly labelled, so nobody mistakes them for a current alert. Step one: the true-color image, on a fixed map grid." |
| 4 | **0:45–1:00** (15 s) | Step 3 "Muse Spark boxes": the zoomed box and point on the plume. | "Step three: Muse Spark looks at the image and draws a box around the haze, plus a point inside it. Text prompts like 'smoke' found nothing at satellite scale. Spark's eyes make the next step work." |
| 5 | **1:00–1:20** (20 s) | Step 4 "SAM masks": red pass-1 and cyan pass-2 outlines. Point at the table "16,446 → 22,607 px · kept pass 2 (1.37×)". | "SAM 3.1 turns that box into a pixel-accurate mask. Then a second pass widens the box by fifteen percent to catch the faint tail. It's kept only if the mask stays in one piece and doesn't spill onto land. Here pass two grew the mask by more than a third." |
| 6 | **1:20–1:50** (30 s) | Step 5 "Agent trace". Scroll slowly through E1–E7: get_volcano_status, get_wind, distance_to_vents, land_fraction, get_firms, then round 2: distance_to_vents with wind_from_deg, get_wind at the summit. Pause on the green note "Every evidence line cites a tool result." | "This is the agent. Muse Spark decides which tools to call: the official USGS volcano status for that hour, the wind, NASA fire detections with summit glow filtered out, and the plume's distance to the vents. In round two it re-measures the plume using the wind it just fetched. Every piece of evidence must cite a tool result. A verdict that cites nothing is thrown out." |
| 7 | **1:50–2:10** (20 s) | Step 6 "Verdict and evidence": "Likely vog from Kīlauea (82%)", evidence bullets with [E…] citations, the USGS notice link. Then switch to the Maui replay at step 6: "Likely wildfire smoke (90%)". | "Verdict: vog from Kīlauea, eighty-two percent, with every reason linked to its source. Same pipeline on the 2023 Maui fires: wildfire smoke, traced to the Kula fire cluster about twenty kilometres upwind. USGS says both volcanoes were quiet." |
| 8 | **2:10–2:25** (15 s) | Open the Mauna Loa replay, step 6: "Haze seen, source not confirmed", with the unconfirmed line "vog_mauna_loa 62%". | "And when the evidence is weak, it says so. Mauna Loa, 2022: the vents were under cloud. The right answer gets sixty-two percent, below our seventy-percent bar, so the headline stays 'uncertain'." |
| 9 | **2:25–2:45** (20 s) | Back to Kīlauea, step 7 "Alerts". Click through the English, Tiếng Việt and ʻŌlelo Hawaiʻi tabs. Zoom in on "Official guidance (quoted)", with the source link and "(verbatim)" / "machine-translated". | "Alerts come in five languages: English, Vietnamese, Ilocano, Tagalog and Hawaiian. Health guidance is never chosen or written by AI. Each result maps to fixed official lines from the Department of Health and EPA, quoted word for word. The AI only translates, and it's labelled." |
| 10 | **2:45–3:00** (15 s) | Phone view (390 px), scrolling the page. Then "How it works": the three Meta models and the cost table ($0.006 per empty scan). End card: "Smoke or Vog? · smoke-or-vog.pages.dev · Satellite estimate, not an official warning." | "Muse Spark for vision and the agent, SAM 3.1 for masks, Muse Image for backgrounds. Under a cent for an empty scan. Built in Hawaiʻi during this hackathon. Smoke or Vog." |

**Total:** 15 + 15 + 15 + 15 + 20 + 30 + 20 + 15 + 20 + 15 = **180 s**.

## Recording checklist

- Clear `localStorage` so the site opens in English, then switch to Tiếng Việt only in scene 9.
- Pre-load each replay once so images are cached and no spinners show.
- Scene 2 uses whatever the live run shows at recording time. If a plume is live, keep it: the
  viewer will open on live, which is even better.
- Keep the "Satellite estimate, not an official warning." footer visible in the closing frame.
- Don't show the terminal, the API key, or any Kahu Ola interface. Mention Kahu Ola only as a
  data source, and only if asked.
