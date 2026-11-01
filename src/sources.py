"""External data sources (no Meta credits spent here).

- Imagery: NASA GIBS WMS, EPSG:4326, fixed Hawaiʻi box (geo.py).
  Live + recent: GOES-West_ABI_GeoColor (10-min cadence, ~80-day retention).
  Older dates:   MODIS_Terra / VIIRS_NOAA20 CorrectedReflectance_TrueColor (daily).
  Reference only: NOAA STAR GOES-18 'hi' sector GeoColor JPEG (not georeferenced).
- ADP haze signal: Kahu Ola /api/hazards/smoke-sat (live only).
- Fire points: Kahu Ola /api/firms/hotspots (live, rolling 24 h) or the GIBS
  FIRMS thermal-anomaly layers rasterised on the same grid (historical).
- Wind: Open-Meteo forecast (live) / archive (historical).
"""

from __future__ import annotations

import io
import re
import time as time_mod
from datetime import datetime, timedelta, timezone

import requests
from PIL import Image

from . import geo
from .common import RAW

UA = {"User-Agent": "smoke-or-vog/0.1 (Meta hackathon; contact long@kahuola.org)"}
GIBS_WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
STAR_HI = "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/SECTOR/hi/GEOCOLOR/"
KAHUOLA = "https://kahuola.org"


def _gibs_map(layer: str, time: str, fmt: str = "image/jpeg", attempts: int = 4) -> Image.Image:
    """GetMap with retries: GIBS intermittently answers with a ServiceException."""
    err = ""
    for i in range(attempts):
        r = requests.get(GIBS_WMS, params={
            "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0",
            "LAYERS": layer, "CRS": "EPSG:4326",
            "BBOX": f"{geo.SOUTH},{geo.WEST},{geo.NORTH},{geo.EAST}",
            "WIDTH": geo.WIDTH, "HEIGHT": geo.HEIGHT, "FORMAT": fmt, "TIME": time,
        }, headers=UA, timeout=90)
        if r.ok and r.headers.get("content-type", "").startswith("image/"):
            return Image.open(io.BytesIO(r.content))
        m = re.search(r"<ServiceException[^>]*>([^<]*)", r.text or "")
        err = (m.group(1).strip() if m else r.text[:200]) or f"HTTP {r.status_code}"
        time_mod.sleep(1.5 * (2 ** i))
    raise RuntimeError(f"GIBS GetMap failed for {layer} @ {time}: {err}")


def gibs_latest_time(layer: str, lookback_steps: int = 18) -> str:
    """Newest timestamp with real data for a 10-min GIBS layer.

    GIBS capabilities lag and vary between requests, so probe small PNG tiles
    backward from now; unavailable times come back fully transparent.
    Falls back to the capabilities document.
    """
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    now -= timedelta(minutes=now.minute % 10)
    for k in range(lookback_steps):
        t = (now - timedelta(minutes=10 * k)).strftime("%Y-%m-%dT%H:%M:00Z")
        r = requests.get(GIBS_WMS, params={
            "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": layer,
            "CRS": "EPSG:4326", "BBOX": f"{geo.SOUTH},{geo.WEST},{geo.NORTH},{geo.EAST}",
            "WIDTH": 140, "HEIGHT": 100, "FORMAT": "image/png", "TIME": t},
            headers=UA, timeout=60)
        if r.headers.get("content-type", "").startswith("image/"):
            alpha = Image.open(io.BytesIO(r.content)).convert("RGBA").getchannel("A")
            if alpha.getextrema()[1] > 0:
                return t
    r = requests.get(GIBS_WMS, params={"SERVICE": "WMS", "REQUEST": "GetCapabilities",
                                       "VERSION": "1.3.0"}, headers=UA, timeout=120)
    r.raise_for_status()
    m = re.search(r"<Name>" + re.escape(layer) + r"</Name>(.*?)</Layer>", r.text, re.S)
    dim = re.search(r'<Dimension name="time"[^>]*>([^<]*)<', m.group(1)).group(1)
    return dim.split(",")[-1].split("/")[1]


def fetch_imagery(layer: str, time: str) -> tuple[Image.Image, dict]:
    im = _gibs_map(layer, time).convert("RGB")
    tag = time.replace("-", "").replace(":", "").replace("Z", "Z")[:14]
    path = RAW / "imagery" / f"{layer}_{tag}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=92)
    return im, {"source": "NASA GIBS WMS", "layer": layer, "time": time,
                "bbox_lonlat": [geo.WEST, geo.SOUTH, geo.EAST, geo.NORTH],
                "crs": "EPSG:4326", "size": list(im.size), "raw_path": str(path)}


def fetch_star_latest() -> dict:
    """Save the newest NOAA STAR GOES-18 Hawaiʻi GeoColor 2400px frame (reference)."""
    listing = requests.get(STAR_HI, headers=UA, timeout=30).text
    names = sorted(set(re.findall(r"\d{11}_GOES18-ABI-hi-GEOCOLOR-2400x2400\.jpg", listing)))
    if not names:
        return {"error": "no STAR frames listed"}
    name = names[-1]
    stamp = datetime.strptime(name[:11], "%Y%j%H%M").replace(tzinfo=timezone.utc)
    path = RAW / "goes18_geocolor" / f"goes18_hi_geocolor_{stamp:%Y%m%dT%H%MZ}_2400.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(requests.get(STAR_HI + name, headers=UA, timeout=90).content)
    return {"source": "NOAA STAR CDN", "file": name, "time": stamp.isoformat(),
            "raw_path": str(path), "georeferenced": False}


# ---------------------------------------------------------------- ADP (Kahu Ola)

def fetch_adp_live() -> dict:
    """Kahu Ola smoke-sat JSON + mask -> candidate regions (pixel boxes on our grid)."""
    meta = requests.get(f"{KAHUOLA}/api/hazards/smoke-sat", params={"region": "hawaii"},
                        headers=UA, timeout=30).json()
    out = {k: meta.get(k) for k in ("state", "scan_start_utc", "haze_pixels",
                                    "volcanic_suppressed_pixels", "frame_age_seconds",
                                    "authority", "note", "meaning_of_absence", "frame_url")}
    out["candidates"] = []
    out["mask"] = None
    if not meta.get("frame_url"):
        return out
    im = Image.open(io.BytesIO(requests.get(meta["frame_url"], headers=UA, timeout=30).content))
    im = im.convert("RGBA")
    path = RAW / "adp" / ("kahuola_adp_" + meta["frame_url"].rsplit("%2F", 1)[-1])
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    out["raw_path"] = str(path)
    if not meta.get("haze_pixels"):
        return out
    out["mask"] = adp_mask_to_grid(im)
    out["candidates"] = adp_candidates(out["mask"])
    return out


def adp_mask_to_grid(im: Image.Image) -> Image.Image:
    """Reproject a Kahu Ola ADP frame (Web-Mercator canvas over the analysis box,
    haze = non-transparent pixels) onto the plate-carrée analysis grid (L, 0/255)."""
    alpha = im.convert("RGBA").getchannel("A")
    mw, mh = im.size
    grid = Image.new("L", (geo.WIDTH, geo.HEIGHT), 0)
    gp, ap = grid.load(), alpha.load()
    for my in range(mh):
        for mx in range(mw):
            if ap[mx, my]:
                lon0, lat0 = geo.merc_px_to_lonlat(mx, my, mw, mh)
                lon1, lat1 = geo.merc_px_to_lonlat(mx + 1, my + 1, mw, mh)
                x0, y0 = geo.lonlat_to_px(lon0, lat0)
                x1, y1 = geo.lonlat_to_px(lon1, lat1)
                for yy in range(int(y0), max(int(y0) + 1, int(round(y1)))):
                    for xx in range(int(x0), max(int(x0) + 1, int(round(x1)))):
                        if 0 <= xx < geo.WIDTH and 0 <= yy < geo.HEIGHT:
                            gp[xx, yy] = 255
    return grid


ADP_MIN_AREA_KM2 = 25.0  # ignore specks: one ADP canvas pixel is ~13 grid px (~4 km2)


def adp_candidates(grid: Image.Image, min_px: int | None = None) -> list[list[int]]:
    """Candidate regions = bounding boxes of connected ADP haze components
    of at least ADP_MIN_AREA_KM2 (~0.29 km2 per grid pixel at 20 N)."""
    if min_px is None:
        min_px = round(ADP_MIN_AREA_KM2 / geo.pixel_area_km2(20.0))
    return [box.as_list() for box, _ in components(grid, min_px)]


def components(mask: Image.Image, min_px: int = 30) -> list[tuple[geo.Box, int]]:
    """(bounding box, pixel count) of 4-connected components of a binary L image,
    largest first."""
    w, h = mask.size
    px = mask.load()
    seen = bytearray(w * h)
    found = []
    for y in range(h):
        for x in range(w):
            if px[x, y] and not seen[y * w + x]:
                stack, n = [(x, y)], 0
                x1 = x2 = x
                y1 = y2 = y
                seen[y * w + x] = 1
                while stack:
                    cx, cy = stack.pop()
                    n += 1
                    x1, x2, y1, y2 = min(x1, cx), max(x2, cx), min(y1, cy), max(y2, cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h and px[nx, ny] and not seen[ny * w + nx]:
                            seen[ny * w + nx] = 1
                            stack.append((nx, ny))
                if n >= min_px:
                    found.append((geo.Box(x1, y1, x2, y2), n))
    found.sort(key=lambda t: -t[1])
    return found


# ---------------------------------------------------------------- FIRMS

# Summit caldera boxes (lat_min, lat_max, lon_min, lon_max). They mirror the
# Kahu Ola volcanic zones: its flagged Kīlauea detections fall in
# 19.401-19.417 N, -155.291 to -155.267 W (Halemaʻumaʻu); Mauna Loa = Mokuʻāweoweo.
VOLCANIC_ZONES = {
    "kilauea-summit": (19.385, 19.435, -155.310, -155.250),
    "mauna-loa-summit": (19.445, 19.500, -155.630, -155.570),
}


def volcanic_zone_of(lat: float, lon: float) -> str | None:
    for name, (la0, la1, lo0, lo1) in VOLCANIC_ZONES.items():
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return name
    return None


def split_volcanic(pts: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Separate summit-glow detections from fire candidates.

    Uses the point's own `volcanic_zone` flag when present (Kahu Ola), otherwise
    the caldera boxes. Returns (fire points, {zone: count})."""
    fires, volcanic = [], {}
    for p in pts:
        zone = volcanic_zone_of(p["lat"], p["lon"])
        flagged = p.get("volcanic_zone")
        if flagged or (flagged is None and zone):
            key = zone or "flagged"
            volcanic[key] = volcanic.get(key, 0) + 1
        else:
            fires.append(p)
    return fires, volcanic


def _firms_result(source: str, pts: list[dict], **extra) -> dict:
    fires, volcanic = split_volcanic(pts)
    return {"source": source, "points_count": len(pts), "fire_points_count": len(fires),
            "clusters": _cluster_points(fires),
            "volcanic_thermal": volcanic,
            "volcanic_note": "summit-caldera thermal detections (active vent glow), excluded "
                             "from fire clusters", **extra}


def fetch_firms_live() -> dict:
    fc = requests.get(f"{KAHUOLA}/api/firms/hotspots", params={"include_volcanic": 1},
                      headers=UA, timeout=30).json()
    pts = []
    for f in fc.get("features", []):
        lon, lat = f["geometry"]["coordinates"][:2]
        p = f.get("properties", {})
        pts.append({"lat": lat, "lon": lon, "frp": p.get("frp_mw") or p.get("frp"),
                    "acq": p.get("acq_datetime_utc") or p.get("acq_date"),
                    "confidence": p.get("detection_confidence") or p.get("confidence"),
                    "volcanic_zone": bool(p.get("volcanic_zone"))})
    return _firms_result("Kahu Ola /api/firms/hotspots?include_volcanic=1 "
                         "(VIIRS NOAA-20/21 NRT, rolling 24 h)", pts)


def fetch_firms_gibs(date: str) -> dict:
    """Rasterised FIRMS thermal anomalies from GIBS for a past date."""
    pts = []
    layers = ["VIIRS_NOAA20_Thermal_Anomalies_375m_All", "VIIRS_SNPP_Thermal_Anomalies_375m_All",
              "MODIS_Terra_Thermal_Anomalies_All"]
    for layer in layers:
        try:
            im = _gibs_map(layer, date, fmt="image/png").convert("RGBA")
        except Exception:  # noqa: BLE001  layer missing for this date
            continue
        a = im.getchannel("A").load()
        for y in range(im.height):
            for x in range(im.width):
                if a[x, y] > 0:
                    lon, lat = geo.px_to_lonlat(x + 0.5, y + 0.5)
                    pts.append({"lat": round(lat, 4), "lon": round(lon, 4), "layer": layer})
    return _firms_result(
        f"NASA GIBS FIRMS thermal anomaly layers ({date}), rasterised", pts, layers=layers,
        note="counts are rendered marker pixels on a 0.005-deg grid, not individual detections")


def _cluster_points(pts: list[dict], radius_km: float = 8.0) -> list[dict]:
    clusters: list[dict] = []
    for p in pts:
        for c in clusters:
            if geo.haversine_km(p["lat"], p["lon"], c["lat"], c["lon"]) <= radius_km:
                c["n"] += 1
                c["lat"] += (p["lat"] - c["lat"]) / c["n"]
                c["lon"] += (p["lon"] - c["lon"]) / c["n"]
                break
        else:
            clusters.append({"lat": p["lat"], "lon": p["lon"], "n": 1})
    clusters.sort(key=lambda c: -c["n"])
    for c in clusters:
        c["lat"], c["lon"] = round(c["lat"], 4), round(c["lon"], 4)
        c["near"] = _nearest_place(c["lat"], c["lon"])
        c["nearest_summit_km"] = round(min(geo.haversine_km(c["lat"], c["lon"], *v)
                                           for v in geo.SOURCES.values()), 1)
    return clusters


PLACES = {
    "Kīlauea summit": (19.406, -155.283), "Mauna Loa summit": (19.475, -155.608),
    "Lahaina, Maui": (20.878, -156.677), "Kula, Maui": (20.790, -156.326),
    "Kīhei, Maui": (20.764, -156.445), "Hilo": (19.707, -155.085),
    "Kailua-Kona": (19.640, -155.997), "Pāhala (Kaʻū)": (19.203, -155.479),
    "Honolulu": (21.307, -157.858), "Līhuʻe": (21.981, -159.371),
}


def _nearest_place(lat, lon) -> str:
    name, (plat, plon) = min(PLACES.items(),
                             key=lambda kv: geo.haversine_km(lat, lon, *kv[1]))
    return f"{name} ({geo.haversine_km(lat, lon, plat, plon):.0f} km)"


# ---------------------------------------------------------------- Wind

def fetch_wind(points: dict[str, tuple[float, float]], when: datetime | None) -> dict:
    """10 m wind at named points. when=None -> current conditions."""
    names = list(points)
    lats = ",".join(str(points[n][0]) for n in names)
    lons = ",".join(str(points[n][1]) for n in names)
    if when is None:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lats, "longitude": lons, "timezone": "GMT",
            "current": "wind_speed_10m,wind_direction_10m"}, headers=UA, timeout=30).json()
        r = r if isinstance(r, list) else [r]
        return {"source": "Open-Meteo forecast (current)", "sites": {
            n: {"time": d["current"]["time"], "speed_kmh": d["current"]["wind_speed_10m"],
                "from_deg": d["current"]["wind_direction_10m"]} for n, d in zip(names, r)}}
    day = when.strftime("%Y-%m-%d")
    next_day = (when + timedelta(days=1)).strftime("%Y-%m-%d")  # rounding can cross midnight
    hour = when.replace(minute=0, second=0, microsecond=0) + timedelta(
        hours=1 if when.minute >= 30 else 0)
    key = hour.strftime("%Y-%m-%dT%H:00")
    params = {"latitude": lats, "longitude": lons, "timezone": "GMT", "start_date": day,
              "end_date": next_day, "hourly": "wind_speed_10m,wind_direction_10m"}

    def read(url):
        r = requests.get(url, params=params, headers=UA, timeout=30).json()
        r = r if isinstance(r, list) else [r]
        sites = {}
        for n, d in zip(names, r):
            h = d.get("hourly") or {}
            if key not in h.get("time", []):
                return None
            i = h["time"].index(key)
            sp, dr = h["wind_speed_10m"][i], h["wind_direction_10m"][i]
            if sp is None or dr is None:
                return None
            sites[n] = {"time": key, "speed_kmh": sp, "from_deg": dr}
        return sites

    sites = read("https://archive-api.open-meteo.com/v1/archive")
    if sites is not None:
        return {"source": "Open-Meteo archive (ERA5-based reanalysis)", "sites": sites}
    # ERA5 lags ~5 days: recent past hours come from the forecast endpoint's history
    sites = read("https://api.open-meteo.com/v1/forecast")
    if sites is None:
        raise RuntimeError(f"no Open-Meteo wind for {key}")
    return {"source": "Open-Meteo forecast history (recent days; ERA5 not yet available)", "sites": sites}


# ---------------------------------------------------------------- Volcano status (USGS HVO)

HANS_SEARCH = "https://volcanoes.usgs.gov/hans-public/api/search/search"
HVO_VOLCANOES = {"kilauea": ("hi3", r"K[IĪ]LAUEA"), "mauna_loa": ("hi6", r"MAUNA LOA")}


def parse_hvo_notice(notice_html: str, name_re: str) -> dict:
    """Pull alert level, aviation color, and activity summary for one volcano
    out of an HVO notice (daily/weekly/monthly update or VAN/VONA)."""
    import html as html_mod

    text = html_mod.unescape(re.sub(r"<[^>]+>", " ", notice_html))
    text = re.sub(r"\s+", " ", text)
    m = re.search(name_re + r"\s*\(VNUM", text, re.I)
    block = text[m.start():] if m else text
    nxt = re.search(r"\b[A-Z][A-ZĀĒĪŌŪʻ' ]{3,}\s*\(VNUM", block[10:])
    if nxt:
        block = block[:10 + nxt.start()]
    level = re.search(r"Volcano Alert Level:\s*([A-Z]+)", block)
    color = re.search(r"Aviation Color Code:\s*([A-Z]+)", block)
    summ = re.search(r"(?:Activity )?Summary:\s*(.+?)(?:\s+Volcanic Activity:|\s+[A-Z][a-z]+ "
                     r"Observations:|\s+Previous |$)", block)
    summary = summ.group(1).strip() if summ else ""
    summary = " ".join(re.split(r"(?<=[.!?])\s+", summary)[:3])
    erupting = classify_eruption(summary)
    if erupting == "unknown" and level and level.group(1) == "NORMAL":
        erupting = "no"  # USGS: NORMAL / GREEN = typical non-eruptive background state
    return {"alert_level": level.group(1) if level else None,
            "aviation_color": color.group(1) if color else None,
            "erupting": erupting, "activity_summary": summary}


def classify_eruption(summary: str) -> str:
    """'yes' | 'no' | 'episodic_pause' | 'unknown' from an HVO activity summary."""
    low = summary.lower()
    ongoing = bool(re.search(r"\bongoing\b[^.]*\beruption\b|\beruption\b[^.]*\bongoing\b", low))
    if re.search(r"\bnot erupting\b|\bno (?:active )?eruption\b", low):
        return "no"
    if (ongoing or "episode" in low) and re.search(
            r"\bepisode\b[^.]*\b(?:ended|paused|stopped)\b|\bpaused?\b[^.]*\bepisode\b", low):
        return "episodic_pause"
    if re.search(r"\beruption\b[^.]*\b(?:has )?(?:ended|paused)\b", low):
        return "no"
    if ongoing or re.search(r"\bis erupting\b|\beruption\b[^.]*\bcontinu(?:es|ed)\b|"
                            r"\bactive (?:fissures?|lava|vents?)\b|\beruption began\b|"
                            r"\bhas resumed\b|\blava fountain", low):
        return "yes"
    return "unknown"


def fetch_volcano_status(when: datetime | None, lookback_days: int = 45) -> dict:
    """Status of Kīlauea and Mauna Loa valid at `when` (None = now): the most recent
    HVO notice sent at or before that time, from the USGS HANS public search API."""
    end = when or datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    out = {"source": "USGS Hawaiian Volcano Observatory notices via HANS public API "
                     "(https://volcanoes.usgs.gov/hans-public/api/search/search)",
           "valid_at": end.isoformat(), "volcanoes": {}}
    for key, (code, name_re) in HVO_VOLCANOES.items():
        try:
            r = requests.post(HANS_SEARCH, json={
                "obsAbbr": "hvo", "noticeTypeCd": "", "volcCd": code,
                "startUnixtime": int(start.timestamp()), "endUnixtime": int(end.timestamp()),
                "searchText": "", "pageIndex": 0}, headers=UA, timeout=45)
            r.raise_for_status()
            rows = [n for n in r.json().get("noticeData", [])
                    if n.get("sentUnixtime", 0) <= end.timestamp()]
        except Exception as e:  # noqa: BLE001
            out["volcanoes"][key] = {"error": str(e)[:200]}
            continue
        if not rows:
            out["volcanoes"][key] = {"error": f"no HVO notice in the {lookback_days} days before"}
            continue
        n = max(rows, key=lambda x: x["sentUnixtime"])
        out["volcanoes"][key] = {
            **parse_hvo_notice(n.get("noticeHtml", ""), name_re),
            "notice_type": n.get("noticeTypeCd"), "notice_sent_utc": n.get("sentUtc"),
            "notice_id": n.get("noticeIdentifier"), "notice_url": n.get("permLink")}
    return out
