"""Shared helpers for the smoke tests: client, cost logging, frame fetching.

The API key is read from .env.local and is never printed or logged.
"""

from __future__ import annotations

import base64
import csv
import io
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
RAW = ROOT / "data" / "raw"
OUT.mkdir(exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://api.meta.ai/v1"
KAHUOLA_SMOKE_SAT = "https://kahuola.org/api/hazards/smoke-sat?region=hawaii"

# Pay-as-you-go prices from dev.meta.ai/docs/pricing-rate-limits (USD).
SPARK_PER_M = {"input": 1.25, "cached_input": 0.15, "output": 4.25}
SAM_PER_IMAGE = 2.50 / 1000
MUSE_IMAGE_PER_IMAGE = 0.01

load_dotenv(ROOT / ".env.local")


def api_key() -> str:
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise SystemExit("MODEL_API_KEY missing from .env.local")
    return key


def client():
    from openai import OpenAI

    return OpenAI(base_url=BASE_URL, api_key=api_key())


def async_client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(base_url=BASE_URL, api_key=api_key())


def _get(usage, name, default=0):
    if usage is None:
        return default
    if isinstance(usage, dict):
        return usage.get(name, default) or default
    return getattr(usage, name, default) or default


def spark_cost(usage) -> tuple[float, dict]:
    inp = _get(usage, "input_tokens")
    out = _get(usage, "output_tokens")
    cached = _get(_get(usage, "input_tokens_details", None), "cached_tokens")
    reasoning = _get(_get(usage, "output_tokens_details", None), "reasoning_tokens")
    cost = (
        (inp - cached) * SPARK_PER_M["input"]
        + cached * SPARK_PER_M["cached_input"]
        + out * SPARK_PER_M["output"]
    ) / 1_000_000
    return cost, {
        "input_tokens": inp,
        "cached_tokens": cached,
        "output_tokens": out,
        "reasoning_tokens": reasoning,
    }


COST_FIELDS = [
    "timestamp_utc", "script", "model", "status",
    "input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens",
    "units", "cost_usd", "note",
]


def log_cost(script: str, model: str, cost: float, status: str = "ok",
             units: str = "", note: str = "", **tokens) -> None:
    path = OUT / "costs.csv"
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COST_FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "script": script, "model": model, "status": status,
            "input_tokens": tokens.get("input_tokens", ""),
            "cached_tokens": tokens.get("cached_tokens", ""),
            "output_tokens": tokens.get("output_tokens", ""),
            "reasoning_tokens": tokens.get("reasoning_tokens", ""),
            "units": units, "cost_usd": f"{cost:.6f}", "note": note,
        })


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


def to_data_url(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
