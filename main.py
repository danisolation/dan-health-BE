"""
FastAPI Application — Entry point cho Backend server.
Bao gồm cron job sync dữ liệu Zepp lúc 00:00 mỗi ngày.
"""
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

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

# GZip compression cho large responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS — cho phép frontend dev server gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


# --- Simple rate limiting cho sync/upload endpoints ---
import time
from collections import defaultdict

_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 5  # max requests per window


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limit cho POST endpoints (sync, upload) — 5 requests/phút mỗi IP."""
    if request.method == "POST":
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        # Xóa entries cũ
        _rate_limits[client_ip] = [t for t in _rate_limits[client_ip] if now - t < RATE_LIMIT_WINDOW]
        if len(_rate_limits[client_ip]) >= RATE_LIMIT_MAX:
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=429,
                media_type="application/json",
            )
        _rate_limits[client_ip].append(now)
    return await call_next(request)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
