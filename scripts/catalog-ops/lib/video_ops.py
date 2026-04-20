"""Video processing helpers for Shopify-bound product videos.

Shopify accepts MP4/MOV up to 1 GB and 60 seconds. On product pages, videos
play muted-autoplay by default, but the audio track is still in the file. To
guarantee silent playback in every theme and every surface, we strip the
audio track at ingestion time.

Requires ffmpeg on PATH (install with `brew install ffmpeg`).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


INPUT_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
MAX_DURATION_SECONDS = 60
# Shopify caps at 1 GB; we target much smaller to keep the git repo sane.
TARGET_MAX_BYTES = 50 * 1024 * 1024
TARGET_MAX_HEIGHT = 1080


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def list_videos(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in INPUT_EXTS
    )


def _probe_duration(path: Path) -> float:
    """Use ffprobe (ships with ffmpeg) to read video duration in seconds."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def process_video(src: Path, dst: Path, *, trim_to_seconds: int = MAX_DURATION_SECONDS) -> None:
    """Re-encode src as H.264 MP4 without audio, trimmed to trim_to_seconds,
    scaled to fit TARGET_MAX_HEIGHT."""
    if not ffmpeg_available():
        raise RuntimeError(
            "ffmpeg is not on PATH. Install with: brew install ffmpeg"
        )
    dst.parent.mkdir(parents=True, exist_ok=True)
    duration = _probe_duration(src)
    effective_trim = min(duration, trim_to_seconds) if duration else trim_to_seconds
    scale_filter = f"scale=-2:'min({TARGET_MAX_HEIGHT},ih)'"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-t", f"{effective_trim:.2f}",
        "-an",                        # strip audio
        "-vf", scale_filter,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",        # wide compatibility
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def suggest_filename(index: int, hint: str = "") -> str:
    slug = hint.strip().lower().replace(" ", "-") or "video"
    return f"{index:02d}-{slug}.mp4"
