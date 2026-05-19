"""Tests for API routes — media listing, filtering, search, health, and edge cases."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.media import MediaFile, MediaType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_media(
    file_path: str = "test/image.png",
    file_name: str = "image.png",
    media_type: MediaType = MediaType.IMAGE,
    positive_prompt: str | None = None,
    checkpoint_name: str | None = None,
    sampler_name: str | None = None,
    seed: int | None = None,
    file_size: int = 1000,
    width: int | None = 512,
    height: int | None = 512,
    workflow_search_text: str | None = None,
) -> MediaFile:
    return MediaFile(
        file_path=file_path,
        file_name=file_name,
        file_extension=".png",
        media_type=media_type,
        file_size=file_size,
        width=width,
        height=height,
        positive_prompt=positive_prompt,
        checkpoint_name=checkpoint_name,
        sampler_name=sampler_name,
        seed=seed,
        workflow_search_text=workflow_search_text,
        file_created_at=datetime.now(timezone.utc),
        file_modified_at=datetime.now(timezone.utc),
    )


def _create_test_app(db_engine):
    """Build a FastAPI app wired to the test DB engine, with lifespan disabled."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from app.api.media import router as media_router
    from app.api.scan import router as scan_router
    from app.database import get_db

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    test_app = FastAPI(title="Test", lifespan=noop_lifespan)
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    test_app.include_router(media_router)
    test_app.include_router(scan_router)

    # Health endpoint
    @test_app.get("/api/health")
    async def health_check():
        return {"status": "ok", "version": "0.1.0"}

    # File serving endpoint (replicates main.py)
    from pathlib import Path

    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    from app.config import settings

    @test_app.get("/api/media/file/{file_path:path}")
    async def serve_media_file(file_path: str):
        media_root = Path(settings.media_root).resolve()
        full_path = (media_root / file_path).resolve()
        if not full_path.is_relative_to(media_root):
            raise HTTPException(status_code=403, detail="Access denied")
        if not full_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(full_path)

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    test_app.dependency_overrides[get_db] = override_get_db
    return test_app


@pytest_asyncio.fixture
async def app_client(db_engine):
    """Client fixture that creates a fresh test app with DB override."""
    test_app = _create_test_app(db_engine)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seeded_db(db_engine):
    """Insert test data and return the session factory."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        items = [
            _make_media("folder_a/img1.png", "img1.png", positive_prompt="a sunset landscape",
                        checkpoint_name="sd_xl_base", sampler_name="euler", seed=42,
                        workflow_search_text="a sunset landscape sd_xl_base euler CheckpointLoaderSimple KSampler"),
            _make_media("folder_a/img2.png", "img2.png", positive_prompt="a portrait photo",
                        checkpoint_name="sd_xl_base", sampler_name="dpmpp_2m", seed=100,
                        workflow_search_text="a portrait photo sd_xl_base dpmpp_2m CheckpointLoaderSimple KSampler"),
            _make_media("folder_b/img3.png", "img3.png", positive_prompt="abstract art",
                        checkpoint_name="deliberate_v3", sampler_name="euler",
                        workflow_search_text="abstract art deliberate_v3 euler CheckpointLoaderSimple KSampler"),
            _make_media("folder_b/video1.mp4", "video1.mp4", media_type=MediaType.VIDEO,
                        file_size=5000),
            _make_media("img4.png", "img4.png", positive_prompt="night city landscape",
                        seed=721897303308196,
                        workflow_search_text="night city landscape CLIPTextEncode"),
        ]
        for item in items:
            session.add(item)
        await session.commit()
    return session_factory


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    async def test_health_check(self, app_client):
        resp = await app_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# GET /api/media
# ---------------------------------------------------------------------------

class TestListMedia:
    async def test_empty_db(self, app_client):
        resp = await app_client.get("/api/media")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["pagination"]["total"] == 0
        assert data["pagination"]["total_pages"] == 0

    async def test_returns_all_items(self, app_client, seeded_db):
        resp = await app_client.get("/api/media")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["total"] == 5
        assert len(data["items"]) == 5

    async def test_pagination(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?page=1&per_page=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["pagination"]["total"] == 5
        assert data["pagination"]["total_pages"] == 3
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["per_page"] == 2

    async def test_pagination_page_2(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?page=2&per_page=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2

    async def test_filter_by_media_type(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?media_type=video")
        data = resp.json()
        assert resp.status_code == 200
        assert data["pagination"]["total"] == 1
        assert data["items"][0]["media_type"] == "video"

    async def test_filter_by_folder(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?folder=folder_a/")
        data = resp.json()
        assert resp.status_code == 200
        assert data["pagination"]["total"] == 2
        for item in data["items"]:
            assert item["file_path"].startswith("folder_a/")

    async def test_search_by_prompt(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?search=landscape")
        data = resp.json()
        assert resp.status_code == 200
        assert data["pagination"]["total"] == 2

    async def test_search_by_node_type(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?search=CheckpointLoaderSimple")
        data = resp.json()
        assert resp.status_code == 200
        assert data["pagination"]["total"] == 3

    async def test_filter_by_checkpoint(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?checkpoint=sd_xl_base")
        data = resp.json()
        assert resp.status_code == 200
        assert data["pagination"]["total"] == 2
        for item in data["items"]:
            assert item["checkpoint_name"] == "sd_xl_base"

    async def test_filter_by_sampler(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?sampler=euler")
        data = resp.json()
        assert resp.status_code == 200
        assert data["pagination"]["total"] == 2

    async def test_sort_ascending(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?sort_by=file_name&sort_order=asc")
        data = resp.json()
        names = [item["file_name"] for item in data["items"]]
        assert names == sorted(names)

    async def test_sort_descending(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?sort_by=file_name&sort_order=desc")
        data = resp.json()
        names = [item["file_name"] for item in data["items"]]
        assert names == sorted(names, reverse=True)

    async def test_invalid_sort_by(self, app_client):
        resp = await app_client.get("/api/media?sort_by=invalid_column")
        assert resp.status_code == 422

    async def test_page_below_minimum(self, app_client):
        resp = await app_client.get("/api/media?page=0")
        assert resp.status_code == 422

    async def test_per_page_above_max(self, app_client):
        resp = await app_client.get("/api/media?per_page=300")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/media/{id}
# ---------------------------------------------------------------------------

class TestGetMediaById:
    async def test_valid_id(self, app_client, seeded_db):
        list_resp = await app_client.get("/api/media?per_page=1")
        item_id = list_resp.json()["items"][0]["id"]

        resp = await app_client.get(f"/api/media/{item_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == item_id

    async def test_nonexistent_id_returns_404(self, app_client):
        resp = await app_client.get("/api/media/999999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Media not found"


# ---------------------------------------------------------------------------
# GET /api/media/folders/tree
# ---------------------------------------------------------------------------

class TestFolderTree:
    async def test_with_folders(self, app_client, seeded_db):
        resp = await app_client.get("/api/media/folders/tree")
        assert resp.status_code == 200
        data = resp.json()
        names = [node["name"] for node in data]
        assert "folder_a" in names
        assert "folder_b" in names

    async def test_empty_db(self, app_client):
        resp = await app_client.get("/api/media/folders/tree")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /api/scan
# ---------------------------------------------------------------------------

class TestScanEndpoint:
    async def test_scan_returns_ok(self, app_client):
        mock_stats = {"discovered": 0, "new": 0, "updated": 0, "errors": 0}
        with patch("app.api.scan.scan_and_ingest", new_callable=AsyncMock, return_value=mock_stats):
            resp = await app_client.post("/api/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["stats"] == mock_stats


# ---------------------------------------------------------------------------
# GET /api/media/file/{path} — path traversal protection
# ---------------------------------------------------------------------------

class TestServeMediaFile:
    async def test_path_traversal_blocked(self, db_engine, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        # Create /etc/passwd adjacent to media_dir to prove it won't be served
        (tmp_path / "secret.txt").write_text("secret data")

        from app.config import settings

        original = settings.media_root
        settings.media_root = str(media_dir)
        try:
            test_app = _create_test_app(db_engine)
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Use %2e%2e to bypass URL normalization
                resp = await client.get(
                    "/api/media/file/%2e%2e/secret.txt",
                    follow_redirects=False,
                )
            # Should be 403 (access denied) or 404 (not found inside media_root)
            assert resp.status_code in (403, 404)
            if resp.status_code == 403:
                assert resp.json()["detail"] == "Access denied"
        finally:
            settings.media_root = original

    async def test_nonexistent_file_returns_404(self, db_engine, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()

        from app.config import settings

        original = settings.media_root
        settings.media_root = str(media_dir)
        try:
            test_app = _create_test_app(db_engine)
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/media/file/nonexistent.png")
            assert resp.status_code == 404
        finally:
            settings.media_root = original

    async def test_valid_file_served(self, db_engine, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        test_file = media_dir / "test.png"
        test_file.write_bytes(b"\x89PNG fake content")

        from app.config import settings

        original = settings.media_root
        settings.media_root = str(media_dir)
        try:
            test_app = _create_test_app(db_engine)
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/media/file/test.png")
            assert resp.status_code == 200
        finally:
            settings.media_root = original


# ---------------------------------------------------------------------------
# Large seed values (BigInteger)
# ---------------------------------------------------------------------------

class TestLargeSeedValues:
    async def test_large_seed_stored_and_returned(self, app_client, seeded_db):
        resp = await app_client.get("/api/media?search=night+city")
        data = resp.json()
        assert data["pagination"]["total"] == 1
        assert data["items"][0]["seed"] == 721897303308196
