"""Geometry for the fixed Hawaiʻi analysis grid.

All imagery is requested from NASA GIBS in EPSG:4326 (plate carrée) over the
same box Kahu Ola's ADP layer uses, so pixel <-> lon/lat is linear.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# lon -161..-154, lat 18..23 (Kahu Ola smoke-sat image_coordinates)
WEST, EAST, SOUTH, NORTH = -161.0, -154.0, 18.0, 23.0
WIDTH, HEIGHT = 1400, 1000  # 0.005 deg/px  (~0.52 km x 0.56 km at 20N)

SOURCES = {
    # Summit vents (USGS HVO reference points, approximate)
    "kilauea_summit": (19.406, -155.283),
    "mauna_loa_summit": (19.475, -155.608),
}


def lonlat_to_px(lon: float, lat: float, w: int = WIDTH, h: int = HEIGHT) -> tuple[float, float]:
    return (lon - WEST) / (EAST - WEST) * w, (NORTH - lat) / (NORTH - SOUTH) * h


def px_to_lonlat(x: float, y: float, w: int = WIDTH, h: int = HEIGHT) -> tuple[float, float]:
    return WEST + x / w * (EAST - WEST), NORTH - y / h * (NORTH - SOUTH)


def norm1000_to_px(x: float, y: float, w: int = WIDTH, h: int = HEIGHT) -> tuple[float, float]:
    return x * w / 1000, y * h / 1000


def px_to_norm1000(x: float, y: float, w: int = WIDTH, h: int = HEIGHT) -> tuple[int, int]:
    return round(x * 1000 / w), round(y * 1000 / h)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def pixel_area_km2(lat: float, w: int = WIDTH, h: int = HEIGHT) -> float:
    dlon = (EAST - WEST) / w
    dlat = (NORTH - SOUTH) / h
    return (dlat * 111.32) * (dlon * 111.32 * math.cos(math.radians(lat)))


# Web-Mercator helpers (Kahu Ola ADP frames are drawn on a Mercator canvas)
def _merc_y(lat: float) -> float:
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def merc_px_to_lonlat(x: float, y: float, w: int, h: int) -> tuple[float, float]:
    lon = WEST + x / w * (EAST - WEST)
    yn, ys = _merc_y(NORTH), _merc_y(SOUTH)
    my = yn - y / h * (yn - ys)
    lat = math.degrees(2 * math.atan(math.exp(my)) - math.pi / 2)
    return lon, lat


@dataclass
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    def clip(self, w: int = WIDTH, h: int = HEIGHT) -> "Box":
        return Box(max(0, min(self.x1, w - 1)), max(0, min(self.y1, h - 1)),
                   max(0, min(self.x2, w - 1)), max(0, min(self.y2, h - 1)))

    def as_list(self) -> list[int]:
        return [round(self.x1), round(self.y1), round(self.x2), round(self.y2)]
