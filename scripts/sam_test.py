"""Smoke test (b): SAM 3.1 segments "haze plume" in one GOES-18 haze frame.

Default input is the latest Kahu Ola frame; pass --image PATH_OR_URL to use
another picture. Parses the stream with meta-sam-parser and writes an
overlay PNG to out/.
"""

import argparse
import asyncio

from PIL import Image, ImageDraw

from meta_sam_parser import (
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
)

from _common import OUT, SAM_PER_IMAGE, async_client, fetch_frame, log_cost, to_data_url

MODEL = "sam-3.1"
PROMPT = "haze plume"
COLORS = [(255, 80, 80), (80, 200, 255), (255, 210, 60), (140, 255, 120)]


async def segment(im: Image.Image, prompt: str):
    c = async_client()
    stream = await c.responses.create(
        model=MODEL,
        input=[{
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": to_data_url(im)},
            ],
        }],
        metadata={"include_confidence": "true"},
        stream=True,
    )
    captured = {}

    async def tee():
        async for event in stream:
            if event.type in ("response.completed", "response.incomplete"):
                captured["usage"] = getattr(event.response, "usage", None)
            yield event

    async with stream:
        parsed = parse_responses_stream(tee(), image_segmentation_format())
        async for _ in parsed:
            pass
        result = await parsed.final_result()
    await c.close()
    return result, captured.get("usage")


def render(im: Image.Image, result) -> tuple[Image.Image, list[str]]:
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    lines = []
    for rec in result.records:
        color = COLORS[int(rec.object_id) % len(COLORS)]
        if rec.kind == "mask":
            raster = decode_mask_to_raster(rec.mask)
            w, h = rec.mask.width, rec.mask.height
            m = Image.frombytes("L", (w, h), bytes(v * 140 for v in raster))
            b = rec.bounds
            bw, bh = max(1, round(b.right - b.left)), max(1, round(b.bottom - b.top))
            if (w, h) != (bw, bh):
                m = m.resize((bw, bh), Image.NEAREST)
            fill = Image.new("RGBA", m.size, color + (255,))
            fill.putalpha(m)
            overlay.alpha_composite(fill, (round(b.left), round(b.top)))
        elif rec.kind == "box":
            draw.rectangle([rec.left, rec.top, rec.right - 1, rec.bottom - 1],
                           outline=color + (255,), width=2)
            lines.append(f"object {rec.object_id}: box=({rec.left:.0f},{rec.top:.0f},"
                         f"{rec.right:.0f},{rec.bottom:.0f}) conf={rec.confidence}")
    return Image.alpha_composite(im.convert("RGBA"), overlay), lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="path or URL; default = latest Kahu Ola frame")
    ap.add_argument("--prompt", default=PROMPT)
    ap.add_argument("--out", default="sam_overlay.png")
    args = ap.parse_args()

    im, label = fetch_frame(args.image)
    print(f"input: {label}  size={im.size}  prompt={args.prompt!r}")
    im.save(OUT / "sam_input.png")

    result, usage = asyncio.run(segment(im, args.prompt))
    log_cost("sam_test", MODEL, SAM_PER_IMAGE, units="1 image",
             note=f"prompt={args.prompt!r}; outcome={result.outcome}; usage={usage}")

    out_img, lines = render(im, result)
    out_path = OUT / args.out
    out_img.save(out_path)

    print(f"outcome: {result.outcome}")
    print(f"matches: {len(lines)}")
    for ln in lines:
        print("  " + ln)
    for d in result.diagnostics:
        print(f"  diagnostic: {d}")
    print(f"usage: {usage}  cost: ${SAM_PER_IMAGE:.4f}")
    print(f"overlay: {out_path}")


if __name__ == "__main__":
    main()
