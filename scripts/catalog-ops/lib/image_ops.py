"""Image processing helpers for Shopify-bound product photos.

Handles HEIC/HEIF, JPEG, PNG, WEBP. Rotates by EXIF orientation, strips EXIF,
converts to sRGB, resizes longest edge to 2048 px (Shopify recommended max),
saves as progressive JPEG at quality 90.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps
import pillow_heif

pillow_heif.register_heif_opener()  # enables HEIC via PIL.Image.open


SHOPIFY_MAX_EDGE = 2048
JPEG_QUALITY = 90
INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def list_images(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in INPUT_EXTS
    )


def process_image(src: Path, dst: Path) -> None:
    """Open src, auto-rotate, strip EXIF, convert sRGB, resize, save as JPEG."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)          # apply orientation, then drop EXIF
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        w, h = im.size
        longest = max(w, h)
        if longest > SHOPIFY_MAX_EDGE:
            scale = SHOPIFY_MAX_EDGE / longest
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(
            dst,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
            progressive=True,
            icc_profile=None,  # sRGB assumed; strip embedded profiles for size
        )


def suggest_filename(index: int, hint: str = "") -> str:
    """Produce filenames like 01-flatlay.jpg, 02-yoke-detail.jpg.

    `hint` is optional free text (e.g. 'yoke-detail') the caller supplies from
    a mapping file. When absent, falls back to 'image'.
    """
    slug = hint.strip().lower().replace(" ", "-") or "image"
    return f"{index:02d}-{slug}.jpg"
