"""Folder scanner service — discovers media files and ingests them into the database."""

import logging
import os
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


def discover_media_files(root: str) -> list[Path]:
    """Recursively walk root directory and return all supported media files."""
    media_files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS:
                media_files.append(Path(dirpath) / filename)
    return sorted(media_files)


async def scan_and_ingest(db: AsyncSession) -> dict:
    """Scan the media root, extract metadata, and upsert into the database."""
    media_root = settings.media_root
    logger.info("Starting scan of %s", media_root)

    discovered = discover_media_files(media_root)
    logger.info("Discovered %d media files", len(discovered))

    stats = {"discovered": len(discovered), "new": 0, "updated": 0, "errors": 0}

    existing_query = select(MediaFile)
    result = await db.execute(existing_query)
    existing_records = {m.file_path: m for m in result.scalars().all()}

    for file_path in discovered:
        try:
            relative_path = str(file_path.relative_to(media_root))
            stat = file_path.stat()
            file_mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

            existing = existing_records.get(relative_path)
            if existing is not None:
                if existing.file_modified_at and existing.file_modified_at >= file_mtime:
                    continue
                # File has been modified — update it
                prompt, workflow = extract_metadata(file_path)
                searchable = parse_searchable_fields(prompt)
                ext = file_path.suffix.lower()
                media_type = MediaType.IMAGE if ext in IMAGE_EXTENSIONS else MediaType.VIDEO
                if media_type == MediaType.IMAGE:
                    width, height = get_image_dimensions(file_path)
                else:
                    width, height = get_video_dimensions(file_path)
                thumbnail_path = generate_thumbnail(file_path, media_type)

                existing.file_size = stat.st_size
                existing.width = width
                existing.height = height
                existing.thumbnail_path = thumbnail_path
                existing.metadata_prompt = prompt
                existing.metadata_workflow = workflow
                existing.checkpoint_name = searchable["checkpoint_name"]
                existing.positive_prompt = searchable["positive_prompt"]
                existing.negative_prompt = searchable["negative_prompt"]
                existing.sampler_name = searchable["sampler_name"]
                existing.scheduler = searchable["scheduler"]
                existing.cfg_scale = searchable["cfg_scale"]
                existing.steps = searchable["steps"]
                existing.seed = searchable["seed"]
                existing.lora_names = searchable["lora_names"]
                existing.file_modified_at = file_mtime
                stats["updated"] += 1
                continue

            ext = file_path.suffix.lower()
            media_type = MediaType.IMAGE if ext in IMAGE_EXTENSIONS else MediaType.VIDEO

            prompt, workflow = extract_metadata(file_path)
            searchable = parse_searchable_fields(prompt)

            if media_type == MediaType.IMAGE:
                width, height = get_image_dimensions(file_path)
            else:
                width, height = get_video_dimensions(file_path)

            thumbnail_path = generate_thumbnail(file_path, media_type)

            media_file = MediaFile(
                file_path=relative_path,
                file_name=file_path.name,
                file_extension=ext,
                media_type=media_type,
                file_size=stat.st_size,
                width=width,
                height=height,
                thumbnail_path=thumbnail_path,
                metadata_prompt=prompt,
                metadata_workflow=workflow,
                checkpoint_name=searchable["checkpoint_name"],
                positive_prompt=searchable["positive_prompt"],
                negative_prompt=searchable["negative_prompt"],
                sampler_name=searchable["sampler_name"],
                scheduler=searchable["scheduler"],
                cfg_scale=searchable["cfg_scale"],
                steps=searchable["steps"],
                seed=searchable["seed"],
                lora_names=searchable["lora_names"],
                file_created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
                file_modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            )

            db.add(media_file)
            stats["new"] += 1

        except Exception:
            logger.error("Error processing %s", file_path, exc_info=True)
            stats["errors"] += 1

    await db.commit()
    logger.info("Scan complete: %s", stats)
    return stats
