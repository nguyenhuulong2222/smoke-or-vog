"""Generate one voice-over clip per scene with OpenAI TTS.

    .venv/bin/python scripts/video/tts.py

Reads OPENAI_API_KEY from .env.local (never printed). Writes out/video/audio/scene_NN.wav and
appends the estimated cost of each call to out/video/tts_costs.csv (kept separate from the
Meta ledger so it never affects the live-scan budget stop).
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenes import ROOT, scenes, tts_text  # noqa: E402

OUT = ROOT / "out" / "video" / "audio"
COSTS = ROOT / "out" / "video" / "tts_costs.csv"
MODEL = "gpt-4o-mini-tts-2025-12-15"
VOICES = ["ash"]  # pace test on the densest line: ash ~144 wpm; cedar and marin ran 168-186
# Published price for gpt-4o-mini-tts: ~$0.015 per minute of generated audio
# ($12 / 1M audio tokens) plus $0.60 / 1M text tokens (negligible here).
USD_PER_AUDIO_MIN = 0.015
INSTRUCTIONS = (
    "Voice: a calm, clear, warm documentary narrator. Pace: unhurried, about 140 words per "
    "minute, with natural pauses at commas and full stops. Tone: confident and factual, never "
    "salesy. Words written with hyphens and a capitalized syllable are Hawaiian place names "
    "spelled phonetically (for example kee-lau-AY-ah, ha-VAI-ee, kah-OO, why-LOO-koo, MOW-ee, "
    "MOW-nah LOH-ah): say each one smoothly as a single word, stressing the capitalized "
    "syllable, never spell out letters."
)


def wav_seconds(path: Path) -> float:
    """Duration via ffprobe (streamed WAV headers leave the data length unset)."""
    import subprocess

    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(out.stdout.strip())


# Per-scene pacing nudges (the model drifts faster on long, dense lines).
PACE = {4: "Speak slowly and deliberately, about 130 words per minute, pausing at each comma.",
        5: "Speak slowly and deliberately, about 130 words per minute, pausing at each comma.",
        9: "Speak slowly, about 135 words per minute.",
        2: "Keep a steady pace of about 145 words per minute."}


PAUSES: set[int] = set()  # ellipsis pauses did not slow cedar; not needed with ash


def speak(key: str, text: str, voice: str, path: Path, scene: int = 0) -> None:
    instr = INSTRUCTIONS + (" " + PACE[scene] if scene in PACE else "")
    r = requests.post("https://api.openai.com/v1/audio/speech", timeout=120,
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": MODEL, "voice": voice, "input": text,
                            "instructions": instr, "response_format": "wav"})
    if r.status_code != 200:
        raise RuntimeError(f"TTS HTTP {r.status_code}: {r.text[:200]}")
    path.write_bytes(r.content)


def log(scene: int, seconds: float, chars: int, voice: str) -> float:
    cost = seconds / 60 * USD_PER_AUDIO_MIN
    new = not COSTS.exists()
    with COSTS.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp_utc", "model", "voice", "scene", "chars", "audio_s", "est_cost_usd"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), MODEL, voice, scene,
                    chars, f"{seconds:.2f}", f"{cost:.5f}"])
    return cost


def main(only: list[int] | None = None) -> None:
    key = dotenv_values(ROOT / ".env.local").get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY missing from .env.local")
    OUT.mkdir(parents=True, exist_ok=True)
    voice, total, report = None, 0.0, []
    for s in scenes():
        if only and s["n"] not in only:
            continue
        text = tts_text(s["vo"])
        if s["n"] in PAUSES:  # breathing room between sentences/clauses (TTS input only)
            text = text.replace(". ", "... ").replace(": ", ":... ").replace("; ", "... ")
        path = OUT / f"scene_{s['n']:02d}.wav"
        for v in ([voice] if voice else VOICES):
            try:
                speak(key, text, v, path, s["n"])
                voice = v
                break
            except RuntimeError as e:
                if v == VOICES[-1]:
                    raise
                print(f"voice {v} rejected ({e}); trying next")
        secs = wav_seconds(path)
        total += log(s["n"], secs, len(text), voice)
        slot = s["end"] - s["start"]
        words = len(s["vo"].split())
        report.append({"scene": s["n"], "audio_s": round(secs, 2), "slot_s": slot,
                       "wpm": round(words / secs * 60), "voice": voice})
        print(f"scene {s['n']:2d}: {secs:5.2f}s of {slot:4.1f}s slot, {words} words "
              f"({words / secs * 60:.0f} wpm), voice={voice}")
    prev = json.loads((OUT / "tts_report.json").read_text()) if (OUT / "tts_report.json").exists() else []
    merged = {r["scene"]: r for r in prev} | {r["scene"]: r for r in report}
    (OUT / "tts_report.json").write_text(json.dumps([merged[k] for k in sorted(merged)], indent=1))
    print(f"TTS estimated cost this run: ${total:.4f}")


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or None)
