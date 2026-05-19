import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.media import router as media_router
from app.api.scan import router as scan_router
from app.config import settings
from app.database import async_session, engine
from app.models.media import Base, MediaFile
from app.services.metadata import flatten_json_values
from app.services.scanner import scan_and_ingest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _backfill_search_text() -> None:
    """Populate workflow_search_text for rows that have JSONB metadata but no search text."""
    from sqlalchemy import or_, select

    async with async_session() as db:
        try:
            query = select(MediaFile).where(
                MediaFile.workflow_search_text.is_(None),
                or_(
                    MediaFile.metadata_prompt.isnot(None),
                    MediaFile.metadata_workflow.isnot(None),
                ),
            )
            result = await db.execute(query)
            rows = result.scalars().all()
            if not rows:
                return
            logger.info("Backfilling workflow_search_text for %d rows", len(rows))
            for row in rows:
                row.workflow_search_text = flatten_json_values(
                    row.metadata_prompt, row.metadata_workflow
                )
            await db.commit()
            logger.info("Backfill complete")
        except Exception:
            logger.error("Backfill failed", exc_info=True)


async def _run_initial_scan() -> None:
    """Run the initial media scan as a background task."""
    await _backfill_search_text()
    async with async_session() as db:
        try:
            stats = await scan_and_ingest(db)
            logger.info("Initial scan complete: %s", stats)
        except Exception:
            logger.error("Initial scan failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    # Run initial scan in background so the server can start accepting requests
    scan_task = asyncio.create_task(_run_initial_scan())

    yield

    scan_task.cancel()
    try:
        await scan_task
    except asyncio.CancelledError:
        pass
    await engine.dispose()


app = FastAPI(
    title="ComfyUI Gallery API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(media_router)
app.include_router(scan_router)

# Serve thumbnails
thumbnail_dir = Path(settings.thumbnail_dir)
thumbnail_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/thumbnails", StaticFiles(directory=str(thumbnail_dir)), name="thumbnails")


@app.get("/api/media/file/{file_path:path}")
async def serve_media_file(file_path: str) -> FileResponse:
    """Serve the actual media file for the viewer."""
    from fastapi import HTTPException

    media_root = Path(settings.media_root).resolve()
    full_path = (media_root / file_path).resolve()
    if not full_path.is_relative_to(media_root):
        raise HTTPException(status_code=403, detail="Access denied")
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)


@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "0.1.0"}
