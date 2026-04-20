#!/usr/bin/env python3
"""Convert a portrait product photo to 2000x1333 3:2 landscape.

Strategy:
- If source is taller than wide (portrait), rotate 90° clockwise so the suit
  is oriented landscape with its neckline in the upper half of the frame.
  This preserves all content (no crop = no content loss).
- Then, if the resulting aspect is not exactly 3:2, crop minimally (centered)
  from the shorter axis so it becomes 3:2.
- Finally resize to 2000x1333.

Usage:
  smart-crop.py --src <path> --dst <path> [--rotate cw|ccw|none]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps
import pillow_heif

pillow_heif.register_heif_opener()

TARGET_W = 2000
TARGET_H = 1333  # 3:2 ratio


def _rotate(im: Image.Image, mode: str) -> Image.Image:
    if mode == "cw":
        return im.rotate(-90, expand=True)
    if mode == "ccw":
        return im.rotate(90, expand=True)
    return im


def to_landscape(src: Path, dst: Path, rotate: str = "auto") -> tuple[tuple[int, int, int, int], tuple[int, int], str]:
    """Rotate (if needed) + minimal centered 3:2 crop + resize to 2000x1333.

    Returns (crop_box, pre_rotate_size, rotate_mode_used).
    """
    im = Image.open(src)
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    pre_W, pre_H = im.size

    # Auto-rotate: if portrait, rotate 90° CW to landscape. This keeps the
    # top of the original (often the yoke side) on the LEFT of the result —
    # visually prominent and matches the existing catalog's flatlay style.
    mode_used = rotate
    if rotate == "auto":
        mode_used = "cw" if pre_H > pre_W else "none"
    im = _rotate(im, mode_used)
    W, H = im.size

    # Minimal centered crop to 3:2 (1.5 aspect)
    target_aspect = 1.5
    cur_aspect = W / H
    if cur_aspect > target_aspect:
        # Too wide — crop width
        new_w = int(round(H * target_aspect))
        left = (W - new_w) // 2
        right = left + new_w
        upper, lower = 0, H
    elif cur_aspect < target_aspect:
        # Too tall — crop height
        new_h = int(round(W / target_aspect))
        upper = (H - new_h) // 2
        lower = upper + new_h
        left, right = 0, W
    else:
        left, upper, right, lower = 0, 0, W, H

    cropped = im.crop((left, upper, right, lower))
    out = cropped.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, format="JPEG", quality=90, optimize=True, progressive=True)
    return (left, upper, right, lower), (pre_W, pre_H), mode_used


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", type=Path, required=True)
    p.add_argument("--dst", type=Path, required=True)
    p.add_argument("--rotate", choices=["auto", "cw", "ccw", "none"], default="auto")
    args = p.parse_args()
    if not args.src.exists():
        print(f"ERROR: src not found: {args.src}", file=sys.stderr)
        return 1
    crop, size, rotated = to_landscape(args.src, args.dst, args.rotate)
    print(f"src      : {args.src}  ({size[0]}x{size[1]})")
    print(f"rotate   : {rotated}")
    print(f"dst      : {args.dst}  ({TARGET_W}x{TARGET_H})")
    print(f"crop     : {crop}  -> {crop[2]-crop[0]}x{crop[3]-crop[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
