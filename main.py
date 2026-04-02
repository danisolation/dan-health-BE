"""
FastAPI Application — Entry point cho Backend server.
Bao gồm cron job sync dữ liệu Zepp lúc 00:00 mỗi ngày.
"""
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.database import init_db
from backend.api.router import api_router
from backend.services.sync import cron_sync_yesterday

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Scheduler instance (module-level để có thể truy cập từ endpoint nếu cần)
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Khởi tạo DB + start cron scheduler khi server start."""
    init_db()

    # Cron job: sync dữ liệu ngày hôm trước lúc 00:00 mỗi ngày
    scheduler.add_job(
        cron_sync_yesterday,
        trigger=CronTrigger(hour=0, minute=0),
        id="daily_zepp_sync",
        name="Sync Zepp data at midnight",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Cron scheduler started — daily sync at 00:00")

    yield

    # Shutdown scheduler khi server tắt
    scheduler.shutdown(wait=False)
    logger.info("Cron scheduler stopped")


app = FastAPI(
    title="Amazfit Health Analytics API",
    description="Backend API phân tích dữ liệu sức khỏe từ Amazfit Bip 6",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount API router
app.include_router(api_router)

# CORS — cho phép frontend dev server gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
