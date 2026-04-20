#!/usr/bin/env python3
"""Ingest raw product videos for a given handle.

Reads a raw folder (MP4/MOV/WEBM/AVI/MKV/M4V), trims to 60s max, strips audio,
scales to ≤1080p, re-encodes as H.264 MP4, and writes into
catalog/products/<handle>/videos/ with filenames like 01-drape.mp4.

Shopify accepts MP4/MOV up to 1GB and 60s. CSV import does NOT support video.
Videos must be uploaded to the product via the Shopify admin UI (or, later,
the Admin GraphQL API once you have an app token). The diff.md emitted by
generate-csv.py will list which video files to upload to which product.

Requires ffmpeg on PATH (install with `brew install ffmpeg`).

Usage:
  ingest-videos.py --raw <raw-folder> --handle <product-handle> [options]

Options:
  --raw PATH     Folder containing raw videos. Required.
  --handle STR   Product handle. Required.
  --names PATH   Optional hints file, one per line (e.g. "drape" / "yoke-macro").
  --trim N       Trim each video to at most N seconds. Default: 60.
  --force        Overwrite existing destination files.
  --dry-run      Print plan; write nothing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.video_ops import (  # noqa: E402
    MAX_DURATION_SECONDS, ffmpeg_available, list_videos, process_video, suggest_filename,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--handle", type=str, required=True)
    p.add_argument("--names", type=Path)
    p.add_argument("--trim", type=int, default=MAX_DURATION_SECONDS)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def load_hints(path: Path | None) -> list[str]:
    if not path:
        return []
    return [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> int:
    args = parse_args()
    if not args.raw.exists() or not args.raw.is_dir():
        print(f"ERROR: raw folder not found: {args.raw}", file=sys.stderr)
        return 1
    if not ffmpeg_available():
        print("ERROR: ffmpeg not on PATH. Install with: brew install ffmpeg", file=sys.stderr)
        return 1

    dst_dir = REPO_ROOT / "catalog" / "products" / args.handle / "videos"
    src_videos = list_videos(args.raw)
    if not src_videos:
        print(f"ERROR: no videos found in {args.raw}", file=sys.stderr)
        return 1

    hints = load_hints(args.names)

    print(f"Source folder : {args.raw}")
    print(f"Handle        : {args.handle}")
    print(f"Destination   : {dst_dir}")
    print(f"Video count   : {len(src_videos)}")
    print(f"Trim to       : {args.trim}s (audio will be stripped)")
    print(f"Force         : {args.force}")
    print(f"Dry run       : {args.dry_run}")
    print()

    plan: list[tuple[Path, Path]] = []
    for i, src in enumerate(src_videos, start=1):
        hint = hints[i - 1] if i - 1 < len(hints) and hints[i - 1].strip() else ""
        dst_name = suggest_filename(i, hint)
        dst = dst_dir / dst_name
        if dst.exists() and not args.force:
            print(f"  SKIP  {src.name}  →  {dst.relative_to(REPO_ROOT)}  (exists; pass --force)")
            continue
        plan.append((src, dst))
        print(f"  PLAN  {src.name}  →  {dst.relative_to(REPO_ROOT)}")

    if args.dry_run:
        print("\n--dry-run: nothing encoded.")
        return 0
    if not plan:
        print("\nNothing to do.")
        return 0

    print()
    for src, dst in plan:
        process_video(src, dst, trim_to_seconds=args.trim)
        size_kb = dst.stat().st_size // 1024
        print(f"  DONE  {dst.relative_to(REPO_ROOT)}  ({size_kb} KB)")

    print(f"\nWrote {len(plan)} videos to {dst_dir.relative_to(REPO_ROOT)}/")
    print("Next: git add + commit + push, then note the video filenames in your")
    print("change-spec YAML so generate-csv.py's diff.md lists them as manual-")
    print("upload TODOs (Shopify CSV does not support video media).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
