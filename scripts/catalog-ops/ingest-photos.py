#!/usr/bin/env python3
"""Ingest raw product photos for a given handle.

Reads a raw folder (HEIC/JPEG/PNG/WEBP), resizes + re-encodes each image as a
Shopify-compliant progressive JPEG (longest edge 2048, sRGB, no EXIF), and
writes into catalog/products/<handle>/ with filenames like 01-flatlay.jpg,
02-yoke-detail.jpg, …

Does NOT git-commit. The user is expected to review, git add, and push
manually before running generate-csv.py.

Usage:
  ingest-photos.py --raw <raw-folder> --handle <product-handle> [options]

Options:
  --raw PATH           Folder containing raw images. Required.
  --handle STR         Product handle (e.g. 20-blush-pink-chikankari-suit). Required.
  --names PATH         Optional text file with one hint per line, in source-sort order.
                       E.g.:  flatlay / yoke-detail / portrait / macro
                       Missing or blank lines fall back to "image".
  --force              Overwrite existing files in the destination folder.
  --dry-run            Print what would happen; write nothing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.image_ops import list_images, process_image, suggest_filename  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw", type=Path, required=True, help="Folder of raw images.")
    p.add_argument("--handle", type=str, required=True, help="Product handle, e.g. 20-blush-pink-chikankari-suit.")
    p.add_argument("--names", type=Path, help="Optional hints file, one filename hint per line.")
    p.add_argument("--force", action="store_true", help="Overwrite existing destination files.")
    p.add_argument("--dry-run", action="store_true", help="Preview actions without writing.")
    return p.parse_args()


def load_hints(path: Path | None) -> list[str]:
    if not path:
        return []
    return [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()]


def write_product_md_stub(dst_dir: Path, handle: str, image_count: int) -> None:
    md = dst_dir / "PRODUCT.md"
    if md.exists():
        return  # never clobber a real PRODUCT.md
    template = (
        f"# {handle}\n\n"
        "- **Title:** TBD\n"
        "- **Fabric:** TBD\n"
        "- **Colour:** TBD\n"
        "- **Price (INR):** TBD\n"
        "- **Type:** Semistitched Suit\n"
        "- **Status:** draft\n"
        "- **Qty:** 1\n"
        "- **Tags:** chikankari, lucknow\n\n"
        "## Description\n\n"
        "<One or two paragraphs, warm-luxury voice. Describe the piece — "
        "fabric weight, embroidery style, motifs, what occasion it suits.>\n\n"
        f"## Images ({image_count})\n\n"
        "See files in this directory.\n"
    )
    md.write_text(template, encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not args.raw.exists() or not args.raw.is_dir():
        print(f"ERROR: raw folder not found: {args.raw}", file=sys.stderr)
        return 1

    dst_dir = REPO_ROOT / "catalog" / "products" / args.handle
    src_images = list_images(args.raw)
    if not src_images:
        print(f"ERROR: no images found in {args.raw} (looked for .jpg/.jpeg/.png/.webp/.heic/.heif)", file=sys.stderr)
        return 1

    hints = load_hints(args.names)

    print(f"Source folder : {args.raw}")
    print(f"Handle        : {args.handle}")
    print(f"Destination   : {dst_dir}")
    print(f"Image count   : {len(src_images)}")
    print(f"Force         : {args.force}")
    print(f"Dry run       : {args.dry_run}")
    print()

    plan: list[tuple[Path, Path]] = []
    for i, src in enumerate(src_images, start=1):
        hint = hints[i - 1] if i - 1 < len(hints) and hints[i - 1].strip() else ""
        dst_name = suggest_filename(i, hint)
        dst = dst_dir / dst_name
        if dst.exists() and not args.force:
            print(f"  SKIP  {src.name}  →  {dst.relative_to(REPO_ROOT)}  (exists; pass --force to overwrite)")
            continue
        plan.append((src, dst))
        print(f"  PLAN  {src.name}  →  {dst.relative_to(REPO_ROOT)}")

    if args.dry_run:
        print("\n--dry-run: no files written.")
        return 0

    if not plan:
        print("\nNothing to do (all destinations exist; use --force to overwrite).")
        return 0

    print()
    for src, dst in plan:
        process_image(src, dst)
        print(f"  DONE  {dst.relative_to(REPO_ROOT)}  ({dst.stat().st_size // 1024} KB)")

    write_product_md_stub(dst_dir, args.handle, len(src_images))
    print(f"\nWrote {len(plan)} images to {dst_dir.relative_to(REPO_ROOT)}/")
    print("Next: review the folder, git add + commit + push, then run generate-csv.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
