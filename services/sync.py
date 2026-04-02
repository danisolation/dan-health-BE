"""
Sync Service — Kéo dữ liệu từ Zepp API và lưu vào Aiven PostgreSQL.
Tái sử dụng logic từ app/sync.py, chuyển sang SQLAlchemy ORM.
"""
import logging
from datetime import datetime, timedelta

import httpx
from amazfit_cli import AmazfitClient
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.models.health import HeartRate, SleepRecord, ActivityRecord

logger = logging.getLogger(__name__)


def sync_zepp_data(days: int = 1) -> dict:
    """
    Fetch dữ liệu từ Zepp API và upsert vào PostgreSQL.

    Args:
        days: Số ngày lùi lại để sync (default=1 cho cron hàng đêm)

    Returns:
        dict với status, counts, hoặc error message
    """
    if not settings.zepp_app_token:
        return {"error": "ZEPP_APP_TOKEN chưa cấu hình trong .env"}
    if not settings.zepp_user_id:
        return {"error": "ZEPP_USER_ID chưa cấu hình trong .env"}

    start = datetime.now() - timedelta(days=days)
    end = datetime.now()
    now_str = datetime.now().isoformat()

    counts = {"heart_rate": 0, "sleep": 0, "activity": 0}
    db = SessionLocal()

    try:
        with AmazfitClient(
            app_token=settings.zepp_app_token,
            user_id=settings.zepp_user_id,
        ) as client:
            # Tắt SSL verify cho mạng có proxy/cert inspection
            client._http = httpx.Client(timeout=30.0, follow_redirects=False, verify=False)

            # --- 1. Daily summaries → Activity + Sleep + Heart Rate ---
            summaries = client.get_aggregate_summary(start, end)
            for s in summaries:
                date_val = datetime.strptime(s.date, "%Y-%m-%d").date()

                # Activity record (steps, calories, distance)
                stmt = pg_insert(ActivityRecord).values(
                    activity_date=date_val,
                    steps=s.total_steps or 0,
                    calories=s.total_calories or 0,
                    distance_meters=s.total_distance_meters or 0,
                    active_minutes=0,
                ).on_conflict_do_update(
                    index_elements=["activity_date"],
                    set_={
                        "steps": s.total_steps or 0,
                        "calories": s.total_calories or 0,
                        "distance_meters": s.total_distance_meters or 0,
                    },
                )
                db.execute(stmt)
                counts["activity"] += 1

                # Sleep record
                stmt = pg_insert(SleepRecord).values(
                    sleep_date=date_val,
                    total_minutes=s.sleep_minutes or 0,
                    deep_sleep_minutes=s.deep_sleep_minutes or 0,
                    light_sleep_minutes=s.light_sleep_minutes or 0,
                    rem_sleep_minutes=s.rem_sleep_minutes or 0,
                    awake_minutes=0,
                    sleep_score=None,
                ).on_conflict_do_update(
                    index_elements=["sleep_date"],
                    set_={
                        "total_minutes": s.sleep_minutes or 0,
                        "deep_sleep_minutes": s.deep_sleep_minutes or 0,
                        "light_sleep_minutes": s.light_sleep_minutes or 0,
                        "rem_sleep_minutes": s.rem_sleep_minutes or 0,
                    },
                )
                db.execute(stmt)
                counts["sleep"] += 1

                # Heart rate (resting + max theo ngày)
                if s.resting_heart_rate:
                    db.add(HeartRate(
                        recorded_at=datetime.combine(date_val, datetime.min.time()),
                        bpm=s.resting_heart_rate,
                        measurement_type="resting",
                    ))
                    counts["heart_rate"] += 1
                if s.max_heart_rate:
                    db.add(HeartRate(
                        recorded_at=datetime.combine(date_val, datetime.max.time().replace(microsecond=0)),
                        bpm=s.max_heart_rate,
                        measurement_type="max",
                    ))
                    counts["heart_rate"] += 1

        db.commit()
        logger.info(f"Sync thành công: {counts}, synced_at={now_str}")
        return {"status": "success", "counts": counts, "synced_at": now_str}

    except Exception as e:
        db.rollback()
        logger.error(f"Sync thất bại: {e}")
        return {"error": str(e)}
    finally:
        db.close()


def cron_sync_yesterday() -> None:
    """
    Hàm được APScheduler gọi lúc 0:00 AM mỗi ngày.
    Sync dữ liệu ngày hôm trước (days=1).
    """
    logger.info("Cron sync started — lấy dữ liệu ngày hôm qua")
    result = sync_zepp_data(days=1)
    if "error" in result:
        logger.error(f"Cron sync failed: {result['error']}")
    else:
        logger.info(f"Cron sync completed: {result['counts']}")
