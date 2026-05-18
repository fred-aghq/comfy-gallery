import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Raw ComfyUI metadata
    metadata_prompt: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_workflow: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Extracted searchable fields
    checkpoint_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    positive_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    sampler_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    scheduler: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cfg_scale: Mapped[float | None] = mapped_column(nullable=True)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    lora_names: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    file_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_media_files_media_type", "media_type"),
        Index("ix_media_files_file_created_at", "file_created_at"),
    )
