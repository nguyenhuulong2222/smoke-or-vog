"""Rasterise Natural Earth 10m land (public domain) onto the analysis grid.

    .venv/bin/python scripts/build_land_mask.py

Reads data/raw/naturalearth/ne_10m_land.shp (download:
https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip) and writes
assets/land_hawaii_1400x1000.png (L, 255 = land).
"""

import sys
from pathlib import Path

import shapefile  # pyshp
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import geo  # noqa: E402

SHP = ROOT / "data/raw/naturalearth/ne_10m_land.shp"
OUT = ROOT / "assets/land_hawaii_1400x1000.png"


def main() -> None:
    sf = shapefile.Reader(str(SHP))
    mask = Image.new("L", (geo.WIDTH, geo.HEIGHT), 0)
    d = ImageDraw.Draw(mask)
    n = 0
    for shp in sf.shapes():
        x0, y0, x1, y1 = shp.bbox
        if x1 < geo.WEST or x0 > geo.EAST or y1 < geo.SOUTH or y0 > geo.NORTH:
            continue
        parts = list(shp.parts) + [len(shp.points)]
        for a, b in zip(parts[:-1], parts[1:]):
            ring = [geo.lonlat_to_px(lon, lat) for lon, lat in shp.points[a:b]]
            if len(ring) >= 3:
                d.polygon(ring, fill=255)
                n += 1
    OUT.parent.mkdir(exist_ok=True)
    mask.save(OUT, optimize=True)
    print(f"rings drawn: {n}; land px: {mask.histogram()[255]}; saved {OUT}")


if __name__ == "__main__":
    main()
