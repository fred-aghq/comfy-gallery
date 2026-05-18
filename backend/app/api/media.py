import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.media import MediaFile, MediaType
from app.schemas.media import (
    FolderNode,
    MediaFileResponse,
    MediaListResponse,
    PaginationMeta,
)

router = APIRouter(prefix="/api/media", tags=["media"])


def _to_response(media: MediaFile) -> MediaFileResponse:
    thumbnail_url = None
    if media.thumbnail_path:
        thumbnail_url = f"/api/thumbnails/{media.thumbnail_path}"
    return MediaFileResponse(
        id=media.id,
        file_path=media.file_path,
        file_name=media.file_name,
        file_extension=media.file_extension,
        media_type=media.media_type.value,
        file_size=media.file_size,
        width=media.width,
        height=media.height,
        thumbnail_url=thumbnail_url,
        checkpoint_name=media.checkpoint_name,
        positive_prompt=media.positive_prompt,
        negative_prompt=media.negative_prompt,
        sampler_name=media.sampler_name,
        scheduler=media.scheduler,
        cfg_scale=media.cfg_scale,
        steps=media.steps,
        seed=media.seed,
        lora_names=media.lora_names,
        metadata_prompt=media.metadata_prompt,
        metadata_workflow=media.metadata_workflow,
        file_created_at=media.file_created_at,
        file_modified_at=media.file_modified_at,
        created_at=media.created_at,
    )


@router.get("", response_model=MediaListResponse)
async def list_media(
    page: int = Query(1, ge=1),
    per_page: int = Query(settings.items_per_page, ge=1, le=200),
    media_type: MediaType | None = None,
    folder: str | None = None,
    search: str | None = None,
    checkpoint: str | None = None,
    sampler: str | None = None,
    sort_by: str = Query("file_created_at", pattern="^(file_created_at|file_name|file_size)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
) -> MediaListResponse:
    query = select(MediaFile)
    count_query = select(func.count(MediaFile.id))

    if media_type:
        query = query.where(MediaFile.media_type == media_type)
        count_query = count_query.where(MediaFile.media_type == media_type)

    if folder:
        query = query.where(MediaFile.file_path.startswith(folder))
        count_query = count_query.where(MediaFile.file_path.startswith(folder))

    if search:
        search_filter = MediaFile.positive_prompt.ilike(f"%{search}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if checkpoint:
        query = query.where(MediaFile.checkpoint_name == checkpoint)
        count_query = count_query.where(MediaFile.checkpoint_name == checkpoint)

    if sampler:
        query = query.where(MediaFile.sampler_name == sampler)
        count_query = count_query.where(MediaFile.sampler_name == sampler)

    sort_column = getattr(MediaFile, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc().nulls_last())
    else:
        query = query.order_by(sort_column.asc().nulls_last())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    items = [_to_response(row) for row in result.scalars().all()]

    return MediaListResponse(
        items=items,
        pagination=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=math.ceil(total / per_page) if total > 0 else 0,
        ),
    )


@router.get("/{media_id}", response_model=MediaFileResponse)
async def get_media(media_id: int, db: AsyncSession = Depends(get_db)) -> MediaFileResponse:
    result = await db.execute(select(MediaFile).where(MediaFile.id == media_id))
    media = result.scalar_one()
    return _to_response(media)


@router.get("/folders/tree", response_model=list[FolderNode])
async def get_folder_tree(db: AsyncSession = Depends(get_db)) -> list[FolderNode]:
    result = await db.execute(select(MediaFile.file_path))
    paths = [row[0] for row in result.fetchall()]

    tree: dict = {}
    for path in paths:
        parts = path.split("/")[:-1]  # Remove filename
        current = tree
        for part in parts:
            if part not in current:
                current[part] = {}
            current = current[part]

    def build_nodes(subtree: dict, prefix: str = "") -> list[FolderNode]:
        nodes = []
        for name, children in sorted(subtree.items()):
            path = f"{prefix}{name}/" if prefix else f"{name}/"
            file_count = sum(1 for p in paths if p.startswith(path))
            nodes.append(
                FolderNode(
                    name=name,
                    path=path,
                    children=build_nodes(children, path),
                    file_count=file_count,
                )
            )
        return nodes

    return build_nodes(tree)
