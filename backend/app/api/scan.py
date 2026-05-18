from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.scanner import scan_and_ingest

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.post("")
async def trigger_scan(db: AsyncSession = Depends(get_db)) -> dict:
    """Manually trigger a scan of the media directory."""
    stats = await scan_and_ingest(db)
    return {"status": "ok", "stats": stats}
