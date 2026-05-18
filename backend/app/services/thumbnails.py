"""Thumbnail generation for images and videos."""

import hashlib
import logging
import subprocess
from pathlib import Path

from PIL import Image

from app.config import settings
from app.models.media import MediaType

logger = logging.getLogger(__name__)


def _thumbnail_output_path(file_path: Path) -> Path:
    """Generate a deterministic thumbnail path based on the file's path."""
    path_hash = hashlib.md5(str(file_path).encode()).hexdigest()
    return Path(settings.thumbnail_dir) / f"{path_hash}.webp"


def generate_thumbnail(file_path: Path, media_type: MediaType) -> str | None:
    """Generate a thumbnail and return its relative path, or None on failure."""
    output = _thumbnail_output_path(file_path)

    if output.exists():
        return str(output.name)

    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        if media_type == MediaType.IMAGE:
            return _generate_image_thumbnail(file_path, output)
        else:
            return _generate_video_thumbnail(file_path, output)
    except Exception:
        logger.error("Failed to generate thumbnail for %s", file_path, exc_info=True)
        return None


def _generate_image_thumbnail(file_path: Path, output: Path) -> str | None:
    """Resize image to thumbnail using Pillow."""
    size = settings.thumbnail_size
    with Image.open(file_path) as img:
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        img.save(output, "WEBP", quality=80)
    return str(output.name)


def _generate_video_thumbnail(file_path: Path, output: Path) -> str | None:
    """Extract a frame from the video at 1 second (or first frame)."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(file_path),
            "-ss", "00:00:01",
            "-vframes", "1",
            "-vf", f"scale={settings.thumbnail_size}:-1",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        # Try first frame if seeking to 1s fails
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(file_path),
                "-vframes", "1",
                "-vf", f"scale={settings.thumbnail_size}:-1",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    return str(output.name) if output.exists() else None
