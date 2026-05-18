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
from app.models.media import Base
from app.services.scanner import scan_and_ingest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    # Run initial scan
    async with async_session() as db:
        try:
            stats = await scan_and_ingest(db)
            logger.info("Initial scan complete: %s", stats)
        except Exception:
            logger.error("Initial scan failed", exc_info=True)

    yield

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
    full_path = Path(settings.media_root) / file_path
    return FileResponse(full_path)


@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "0.1.0"}
