"""Image validation and compression before an image is sent to Gemini.

Every image is decoded, EXIF-rotated, converted to RGB, downscaled so its
long edge is at most ``GEMINI_MAX_IMAGE_SIDE`` and re-encoded as JPEG.
Re-encoding also strips EXIF metadata (e.g. GPS) before the photo leaves
the server.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps

from services.gemini.config import GeminiConfig
from services.gemini.errors import ImageTooLargeError, InvalidImageError

MIN_SIDE_PX = 32


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    mime_type: str
    sha256: str  # of the ORIGINAL upload, used for de-duplication
    original_size: tuple[int, int]
    sent_size: tuple[int, int]
    original_bytes: int

    def describe(self) -> dict:
        return {
            "original_size": list(self.original_size),
            "sent_size": list(self.sent_size),
            "original_bytes": self.original_bytes,
            "sent_bytes": len(self.data),
        }


def image_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare_image(data: bytes, config: GeminiConfig) -> PreparedImage:
    if not data:
        raise InvalidImageError("The uploaded image is empty.")
    if len(data) > config.max_upload_bytes:
        raise ImageTooLargeError(config.max_upload_bytes)
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
    except Exception as exc:  # noqa: BLE001 - Pillow raises many types for bad input
        raise InvalidImageError("The uploaded file is not a readable image.") from exc

    original_size = img.size
    if min(original_size) < MIN_SIDE_PX:
        raise InvalidImageError(
            f"The image is too small to analyse (minimum {MIN_SIDE_PX}x{MIN_SIDE_PX} pixels)."
        )

    if max(img.size) > config.max_image_side:
        img.thumbnail((config.max_image_side, config.max_image_side), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=config.jpeg_quality, optimize=True)
    return PreparedImage(
        data=buf.getvalue(),
        mime_type="image/jpeg",
        sha256=image_sha256(data),
        original_size=original_size,
        sent_size=img.size,
        original_bytes=len(data),
    )
