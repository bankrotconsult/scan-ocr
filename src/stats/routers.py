import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from src.db.db import db_session
from src.stats.repository import StatsRepository
from src.stats.service import StatsService

router = APIRouter(prefix="/stats", tags=["Stats"])

_STATS_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "stats.html")


@router.get("/", response_class=HTMLResponse)
async def stats_page():
    with open(_STATS_TEMPLATE_PATH, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/data")
async def stats_data():
    async with db_session() as s:
        stat = await StatsService(StatsRepository(s)).get_stats()
        if stat is None or stat.total == 0:
            return {
                "total": 0, "success": 0, "no_case": 0,
                "bad_case": 0, "no_person": 0, "error": 0,
                "avg_seconds": None,
            }
        avg_seconds = (stat.total_seconds / stat.ocr_count) if stat.ocr_count > 0 else None
        return {
            "total": stat.total,
            "success": stat.success,
            "no_case": stat.no_case,
            "bad_case": stat.bad_case,
            "no_person": stat.no_person,
            "error": stat.error,
            "avg_seconds": round(avg_seconds, 1) if avg_seconds is not None else None,
        }
