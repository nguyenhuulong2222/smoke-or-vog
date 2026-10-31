"""Land / island coverage of plume masks (Natural Earth 10m land, public domain).

assets/land_hawaii_1400x1000.png is built by scripts/build_land_mask.py on the
analysis grid. Islands are the land components, named by nearest centroid.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops

from . import geo

LAND_PNG = Path(__file__).resolve().parent.parent / "assets" / "land_hawaii_1400x1000.png"

ISLANDS = {  # approximate centroids (lat, lon)
    "Hawaiʻi": (19.59, -155.44), "Maui": (20.80, -156.33), "Kahoʻolawe": (20.55, -156.61),
    "Lānaʻi": (20.83, -156.93), "Molokaʻi": (21.13, -157.02), "Oʻahu": (21.47, -157.97),
    "Kauaʻi": (22.06, -159.53), "Niʻihau": (21.90, -160.15),
}
ISLAND_SPILL_FRAC = 0.25   # a mask covering >25% of an island's area has swallowed it
LAND_SPILL_FRAC = 0.20     # or >20% of the mask is land
PASS2_EXTRA_LAND = 0.05    # pass 2 may not add >5 points of land fraction


def _area(m: Image.Image) -> int:
    return m.histogram()[255]


@lru_cache(maxsize=1)
def land_mask() -> Image.Image:
    return Image.open(LAND_PNG).convert("L").point(lambda v: 255 if v >= 128 else 0)


@lru_cache(maxsize=1)
def island_masks() -> dict[str, Image.Image]:
    from .sources import components  # local import avoids a cycle

    land = land_mask()
    out = {}
    for box, _ in components(land, min_px=100):
        cx, cy = (box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2
        lon, lat = geo.px_to_lonlat(cx, cy)
        name = min(ISLANDS, key=lambda n: geo.haversine_km(lat, lon, *ISLANDS[n]))
        m = Image.new("L", land.size, 0)
        crop = (box.x1, box.y1, box.x2 + 1, box.y2 + 1)
        m.paste(land.crop(crop), crop[:2])
        out[name] = ImageChops.lighter(out[name], m) if name in out else m
    return out


def land_stats(mask: Image.Image) -> dict:
    area = _area(mask)
    if not area:
        return {"land_frac": 0.0, "islands_covered": {}, "land_spill": False}
    land_px = _area(ImageChops.multiply(mask, land_mask()))
    covered = {}
    for name, im in island_masks().items():
        inter = _area(ImageChops.multiply(mask, im))
        if inter:
            covered[name] = round(inter / max(1, _area(im)), 3)
    land_frac = round(land_px / area, 3)
    spilled = [n for n, f in covered.items() if f > ISLAND_SPILL_FRAC]
    return {"land_frac": land_frac, "islands_covered": covered,
            "land_spill": land_frac > LAND_SPILL_FRAC or bool(spilled),
            "islands_swallowed": spilled}


def pass2_adds_land(s1: dict, s2: dict) -> str | None:
    """Reason string if pass 2 spills onto land that pass 1 did not cover, else None."""
    if s2["land_frac"] > s1["land_frac"] + PASS2_EXTRA_LAND:
        return f"pass 2 adds land ({s1['land_frac']:.0%} -> {s2['land_frac']:.0%})"
    new = set(s2.get("islands_swallowed", [])) - set(s1.get("islands_swallowed", []))
    if new:
        return "pass 2 swallows " + ", ".join(sorted(new))
    return None


UNRELIABLE_LAND_FRAC = 0.50


def unreliable_reason(stats: dict) -> str | None:
    """Why a plume mask is too land-dominated to confirm a verdict, else None."""
    if stats.get("islands_swallowed"):
        return "mask swallows " + ", ".join(stats["islands_swallowed"]) + " (segmentation unreliable)"
    if stats.get("land_frac", 0) > UNRELIABLE_LAND_FRAC:
        return f"mask is {stats['land_frac']:.0%} land (segmentation unreliable)"
    return None
