"""Shared fixtures for the test suite."""

import os
from collections.abc import AsyncGenerator
from pathlib import Path

# Set environment variables before any app imports to avoid pydantic-settings connecting to PG
os.environ.setdefault("GALLERY_DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("GALLERY_MEDIA_ROOT", "/tmp/test-media")
os.environ.setdefault("GALLERY_THUMBNAIL_DIR", "/tmp/test-thumbs")

import pytest
import pytest_asyncio
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.media import Base

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Swap JSONB → JSON for SQLite compatibility

    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
def sample_png_path() -> Path:
    return FIXTURES_DIR / "comfyui_sample.png"


@pytest.fixture
def tmp_media_dir(tmp_path) -> Path:
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    return media_dir
