import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class MediaFileResponse(BaseModel):
    id: int
    file_path: str
    file_name: str
    file_extension: str
    media_type: str
    file_size: int
    width: int | None = None
    height: int | None = None
    thumbnail_url: str | None = None

    checkpoint_name: str | None = None
    positive_prompt: str | None = None
    negative_prompt: str | None = None
    sampler_name: str | None = None
    scheduler: str | None = None
    cfg_scale: float | None = None
    steps: int | None = None
    seed: int | None = None
    lora_names: list[str] | None = None

    metadata_prompt: dict[str, Any] | None = None
    metadata_workflow: dict[str, Any] | None = None

    file_created_at: datetime | None = None
    file_modified_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("metadata_prompt", "metadata_workflow", mode="before")
    @classmethod
    def _parse_json_string(cls, v: object) -> dict[str, Any] | None:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            return None
        return v


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


class MediaListResponse(BaseModel):
    items: list[MediaFileResponse]
    pagination: PaginationMeta


class FolderNode(BaseModel):
    name: str
    path: str
    children: list["FolderNode"] = []
    file_count: int = 0
