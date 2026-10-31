"""Shared helpers for the smoke tests: client, cost logging, frame fetching.

The API key is read from .env.local and is never printed or logged.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.common import (  # noqa: E402,F401
    BASE_URL, MUSE_IMAGE_PER_IMAGE, OUT, RAW, ROOT, SAM_PER_IMAGE, SPARK_PER_M,
    api_key, async_client, client, log_cost, spark_cost, to_data_url,
)

KAHUOLA_SMOKE_SAT = "https://kahuola.org/api/hazards/smoke-sat?region=hawaii"


def fetch_frame(image_arg: str | None = None) -> tuple[Image.Image, str]:
    """Return (RGB image, label). Default: latest Kahu Ola GOES-18 haze frame.

    Kahu Ola frames are RGBA overlays (transparent where no haze), so they
    are composited onto black before sending to the models.
    """
    if image_arg:
        if image_arg.startswith("http"):
            data = requests.get(image_arg, timeout=30).content
        else:
            data = Path(image_arg).read_bytes()
        label = image_arg
    else:
        meta = requests.get(KAHUOLA_SMOKE_SAT, timeout=30).json()
        url = meta["frame_url"]
        data = requests.get(url, timeout=30).content
        name = url.rsplit("%2F", 1)[-1]
        (RAW / "frames").mkdir(exist_ok=True)
        (RAW / "frames" / name).write_bytes(data)
        label = (f"{url} (scan {meta.get('scan_start_utc')}, "
                 f"haze_pixels={meta.get('haze_pixels')}, state={meta.get('state')})")
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
    return Image.alpha_composite(bg, im).convert("RGB"), label
