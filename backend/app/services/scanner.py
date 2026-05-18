"""Folder scanner service — discovers media files and ingests them into the database."""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.media import MediaFile, MediaType
from app.services.metadata import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    extract_metadata,
    get_image_dimensions,
    get_video_dimensions,
    parse_searchable_fields,
)
from app.services.thumbnails import generate_thumbnail

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


# Log progress every N files or every N seconds, whichever comes first
_PROGRESS_LOG_INTERVAL_FILES = 50
_PROGRESS_LOG_INTERVAL_SECONDS = 5.0


def discover_media_files(root: str) -> list[Path]:
    """Recursively walk root directory and return all supported media files."""
    logger.info("Discovering media files in %s …", root)
    media_files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS:
                media_files.append(Path(dirpath) / filename)
    return sorted(media_files)


def _should_log_progress(
    idx: int, total: int, now: float, last_log_time: float
) -> bool:
    """Return True when it's time to emit a progress log line."""
    if idx == total:
        return True
    if idx % _PROGRESS_LOG_INTERVAL_FILES == 0:
        return True
    if now - last_log_time >= _PROGRESS_LOG_INTERVAL_SECONDS:
        return True
    return False


def _log_progress(idx: int, total: int, stats: dict, skipped: int) -> None:
    pct = idx * 100 // total if total else 0
    logger.info(
        "Scan progress: %d/%d files (%d%%) "
        "[new=%d, updated=%d, skipped=%d, errors=%d]",
        idx,
        total,
        pct,
        stats["new"],
        stats["updated"],
        skipped,
        stats["errors"],
    )


def _process_file(file_path: Path) -> dict:
    """Extract metadata & dimensions and generate thumbnail (sync, CPU/IO-bound)."""
    ext = file_path.suffix.lower()
    media_type = MediaType.IMAGE if ext in IMAGE_EXTENSIONS else MediaType.VIDEO
    prompt, workflow = extract_metadata(file_path)
    searchable = parse_searchable_fields(prompt)
    if media_type == MediaType.IMAGE:
        width, height = get_image_dimensions(file_path)
    else:
        width, height = get_video_dimensions(file_path)
    thumbnail_path = generate_thumbnail(file_path, media_type)
    return {
        "ext": ext,
        "media_type": media_type,
        "prompt": prompt,
        "workflow": workflow,
        "searchable": searchable,
        "width": width,
        "height": height,
        "thumbnail_path": thumbnail_path,
    }


async def scan_and_ingest(db: AsyncSession) -> dict:
    """Scan the media root, extract metadata, and upsert into the database."""
    media_root = settings.media_root
    logger.info("Starting scan of %s", media_root)

    discovered = await asyncio.to_thread(discover_media_files, media_root)
    logger.info("Discovered %d media files", len(discovered))

    total = len(discovered)
    stats: dict = {
        "discovered": total,
        "new": 0,
        "updated": 0,
        "errors": 0,
        "error_details": [],
    }

    existing_query = select(MediaFile)
    result = await db.execute(existing_query)
    existing_records = {m.file_path: m for m in result.scalars().all()}

    skipped = 0
    last_log_time = time.monotonic()

    for idx, file_path in enumerate(discovered, start=1):
        try:
            relative_path = str(file_path.relative_to(media_root))
            stat = await asyncio.to_thread(file_path.stat)
            file_mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

            existing = existing_records.get(relative_path)
            if existing is not None:
                if existing.file_modified_at and existing.file_modified_at >= file_mtime:
                    skipped += 1
                    now = time.monotonic()
                    if _should_log_progress(idx, total, now, last_log_time):
                        _log_progress(idx, total, stats, skipped)
                        last_log_time = now
                    continue
                # File has been modified — re-process it
                info = await asyncio.to_thread(_process_file, file_path)

                async with db.begin_nested():
                    existing.file_size = stat.st_size
                    existing.width = info["width"]
                    existing.height = info["height"]
                    existing.thumbnail_path = info["thumbnail_path"]
                    existing.metadata_prompt = info["prompt"]
                    existing.metadata_workflow = info["workflow"]
                    existing.checkpoint_name = info["searchable"]["checkpoint_name"]
                    existing.positive_prompt = info["searchable"]["positive_prompt"]
                    existing.negative_prompt = info["searchable"]["negative_prompt"]
                    existing.sampler_name = info["searchable"]["sampler_name"]
                    existing.scheduler = info["searchable"]["scheduler"]
                    existing.cfg_scale = info["searchable"]["cfg_scale"]
                    existing.steps = info["searchable"]["steps"]
                    existing.seed = info["searchable"]["seed"]
                    existing.lora_names = info["searchable"]["lora_names"]
                    existing.file_modified_at = file_mtime
                stats["updated"] += 1
                continue

            info = await asyncio.to_thread(_process_file, file_path)

            media_file = MediaFile(
                file_path=relative_path,
                file_name=file_path.name,
                file_extension=info["ext"],
                media_type=info["media_type"],
                file_size=stat.st_size,
                width=info["width"],
                height=info["height"],
                thumbnail_path=info["thumbnail_path"],
                metadata_prompt=info["prompt"],
                metadata_workflow=info["workflow"],
                checkpoint_name=info["searchable"]["checkpoint_name"],
                positive_prompt=info["searchable"]["positive_prompt"],
                negative_prompt=info["searchable"]["negative_prompt"],
                sampler_name=info["searchable"]["sampler_name"],
                scheduler=info["searchable"]["scheduler"],
                cfg_scale=info["searchable"]["cfg_scale"],
                steps=info["searchable"]["steps"],
                seed=info["searchable"]["seed"],
                lora_names=info["searchable"]["lora_names"],
                file_created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
                file_modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            )

            async with db.begin_nested():
                db.add(media_file)
            stats["new"] += 1

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error(
                "Skipping %s — %s", file_path, error_msg, exc_info=True,
            )
            stats["errors"] += 1
            stats["error_details"].append(
                {"file": str(file_path), "error": error_msg}
            )

        now = time.monotonic()
        if _should_log_progress(idx, total, now, last_log_time):
            _log_progress(idx, total, stats, skipped)
            last_log_time = now

    await db.commit()
    logger.info(
        "Scan complete: %d files processed "
        "[new=%d, updated=%d, skipped=%d, errors=%d]",
        total, stats["new"], stats["updated"], skipped, stats["errors"],
    )
    return stats
