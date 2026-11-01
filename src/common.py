"""Shared plumbing: Meta Model API clients, pricing, cost log, budget guard.

MODEL_API_KEY is read from .env.local and is never printed or logged.
"""

from __future__ import annotations

import base64
import csv
import io
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
RAW = ROOT / "data" / "raw"
# CI writes to its own ledger (SMOKEVOG_COSTS_CSV); budget checks sum every ledger
# listed in SMOKEVOG_EXTRA_LEDGERS (comma-separated) plus COSTS_CSV.
COSTS_CSV = Path(os.environ.get("SMOKEVOG_COSTS_CSV") or OUT / "costs.csv")
EXTRA_LEDGERS = [Path(p) for p in os.environ.get("SMOKEVOG_EXTRA_LEDGERS", "").split(",") if p]
OUT.mkdir(exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://api.meta.ai/v1"

# Pay-as-you-go prices from dev.meta.ai/docs/pricing-rate-limits (USD).
SPARK_PER_M = {"input": 1.25, "cached_input": 0.15, "output": 4.25}
SAM_PER_IMAGE = 2.50 / 1000
MUSE_IMAGE_PER_IMAGE = 0.01

HACKATHON_BUDGET_USD = 60.00  # total dev cap (raised from $20 on Nov 1); live job keeps its own $15 stop

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


def _get(obj, name, default=0):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default) or default
    return getattr(obj, name, default) or default


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
    COSTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    new = not COSTS_CSV.exists()
    with COSTS_CSV.open("a", newline="") as f:
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


def ledger_spend(path: Path) -> float:
    if not path.exists():
        return 0.0
    with path.open() as f:
        return sum(float(r["cost_usd"] or 0) for r in csv.DictReader(f))


def total_spend() -> float:
    paths = {COSTS_CSV.resolve(), *(p.resolve() for p in EXTRA_LEDGERS)}
    return sum(ledger_spend(p) for p in paths)


def check_budget(planned: float) -> None:
    spent = total_spend()
    if spent + planned > HACKATHON_BUDGET_USD:
        raise SystemExit(
            f"Budget guard: spent ${spent:.4f} + planned ${planned:.4f} "
            f"exceeds ${HACKATHON_BUDGET_USD:.2f}"
        )


def to_data_url(im: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    im.save(buf, format=fmt)
    mime = "image/png" if fmt == "PNG" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()
