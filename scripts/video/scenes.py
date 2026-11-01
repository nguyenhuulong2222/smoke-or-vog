"""Scene table for the demo video, read from docs/VIDEO_SCRIPT.md (single source of truth)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs" / "VIDEO_SCRIPT.md"
TOTAL = 180.0

# TTS-only phonetic respellings (captions always keep the correct spelling).
PHONETIC = [
    ("Hawaiʻi", "ha-VAI-ee"),
    ("Kīlauea", "kee-lau-AY-ah"),
    ("Kaʻū", "kah-OO"),
    ("Mauna Loa", "MOW-nah LOH-ah"),
    ("Wailuku", "why-LOO-koo"),
    ("Maui", "MOW-ee"),
    ("Kula", "KOO-lah"),
    ("Kahu Ola", "KAH-hoo OH-lah"),
    ("SAM 3.1", "SAM three point one"),
    ("GOES-West", "GOES West"),
]


def _sec(t: str) -> int:
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def scenes() -> list[dict]:
    rows = [l for l in SCRIPT.read_text().splitlines() if re.match(r"^\| \d+ \|", l)]
    out = []
    for l in rows:
        c = [x.strip() for x in l.split("|")]
        a, b = re.search(r"(\d:\d\d)–(\d:\d\d)", c[2]).groups()
        vo = c[4].strip().strip('"')
        out.append({"n": int(c[1]), "start": float(_sec(a)), "end": float(_sec(b)), "vo": vo})
    assert out[0]["start"] == 0 and out[-1]["end"] == TOTAL, "script must cover 0:00–3:00"
    for x, y in zip(out, out[1:]):
        assert x["end"] == y["start"], f"gap/overlap between scenes {x['n']} and {y['n']}"
    return out


def tts_text(vo: str) -> str:
    t = vo
    for word, sound in PHONETIC:
        t = t.replace(word, sound)
    return t
