"""Smoke test (d): Muse Image renders one simple alert card.

Uses the single-shot /v1/images/generations endpoint (flat $0.01 per image).
"""

import base64

from _common import MUSE_IMAGE_PER_IMAGE, OUT, client, log_cost

MODEL = "muse-image-1.0"
PROMPT = (
    "A clean, flat public-safety alert card, landscape. Large bold headline text "
    "exactly: \"Vog advisory – Kaʻū\". Smaller subtitle exactly: \"Volcanic haze "
    "possible. Limit outdoor exertion if sensitive.\" Amber/orange warning color "
    "band at the top with a simple haze icon, white background, high-contrast "
    "dark text, generous margins, sans-serif type. No photos, no logos, no "
    "other text."
)


def main() -> None:
    c = client()
    r = c.images.generate(
        model=MODEL,
        prompt=PROMPT,
        n=1,
        size="1536x1024",
        output_format="png",
        extra_body={
            "reasoning_strength": "low",
            "tool_enablement": {"enable_web_search": False, "enable_image_search": False},
        },
    )
    n = len(r.data or [])
    usage = r.usage.model_dump() if getattr(r, "usage", None) else None
    log_cost("image_test", MODEL, n * MUSE_IMAGE_PER_IMAGE, units=f"{n} image",
             note=f"usage={usage}")
    out_path = OUT / "alert_card_vog_kau_en.png"
    out_path.write_bytes(base64.b64decode(r.data[0].b64_json))
    print(f"model: {MODEL}  images: {n}  output_format: {getattr(r, 'output_format', '?')}")
    print(f"usage: {usage}  cost: ${n * MUSE_IMAGE_PER_IMAGE:.4f}")
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
