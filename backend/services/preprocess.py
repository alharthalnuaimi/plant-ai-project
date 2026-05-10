"""
Shared image hygiene for training and inference alignment.

YOLOv8 `predict()` does internal letterboxing; this module standardizes RGB + EXIF
so custom models or export pipelines see consistent inputs.
"""

from __future__ import annotations

import io
import os
from typing import Literal

from PIL import Image, ImageOps

Mode = Literal["pil", "jpeg_bytes"]


def load_rgb(image_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def standardize_for_model(
    image_bytes: bytes,
    *,
    max_side: int | None = None,
    output: Mode = "jpeg_bytes",
    jpeg_quality: int = 92,
) -> Image.Image | bytes:
    """
    Strip EXIF orientation, force RGB, optionally downscale long edge for API uploads.
    Set MAX_IMAGE_SIDE env (e.g. 2048) to cap resolution without changing aspect ratio.
    """
    img = load_rgb(image_bytes)
    cap = max_side
    if cap is None:
        env = os.getenv("MAX_IMAGE_SIDE", "").strip()
        cap = int(env) if env.isdigit() else None
    if cap and max(img.size) > cap:
        img.thumbnail((cap, cap), Image.Resampling.LANCZOS)

    if output == "pil":
        return img
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    return buf.getvalue()


def should_preprocess() -> bool:
    return os.getenv("STANDARDIZE_IMAGE_ON_PREDICT", "").lower() in ("1", "true", "yes")
