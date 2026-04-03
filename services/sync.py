"""
Sync Service — Kéo toàn bộ dữ liệu từ Zepp API và lưu vào Aiven PostgreSQL.
Bao gồm: daily summaries, stress, SpO2, readiness, workouts.
"""
import logging
from datetime import date as date_type, datetime, timedelta

from amazfit_cli import AmazfitClient
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.models.health import (
    HeartRate, SleepRecord, ActivityRecord,
    StressReading, SpO2Reading, WorkoutRecord,
)

logger = logging.getLogger(__name__)


# ===================== Sync helpers =====================

def _sync_summaries(
    client: AmazfitClient, db: Session,
    start: datetime, end: datetime,
    start_date: date_type, end_date: date_type,
    counts: dict[str, int],
) -> list:
    """Sync daily summaries -> Activity + Heart Rate."""
    summaries = client.get_summary(start, end)

    db.query(HeartRate).filter(
        sa_func.date(HeartRate.recorded_at).between(start_date, end_date)
    ).delete(synchronize_session=False)

    for s in summaries:
        date_val = datetime.strptime(s.date, "%Y-%m-%d").date()
        stmt = pg_insert(ActivityRecord).values(
            activity_date=date_val, steps=s.total_steps or 0,
            calories=s.total_calories or 0,
            distance_meters=s.total_distance_meters or 0, active_minutes=0,
        ).on_conflict_do_update(
            index_elements=["activity_date"],
            set_={"steps": s.total_steps or 0, "calories": s.total_calories or 0,
                   "distance_meters": s.total_distance_meters or 0},
        )
        db.execute(stmt)
        counts["activity"] += 1

        if s.resting_heart_rate:
            db.add(HeartRate(recorded_at=datetime.combine(date_val, datetime.min.time()),
                             bpm=s.resting_heart_rate, measurement_type="resting"))
            counts["heart_rate"] += 1
        if s.max_heart_rate:
            db.add(HeartRate(recorded_at=datetime.combine(date_val, datetime.max.time().replace(microsecond=0)),
                             bpm=s.max_heart_rate, measurement_type="max"))
            counts["heart_rate"] += 1
        if s.min_heart_rate and s.min_heart_rate != s.resting_heart_rate:
            db.add(HeartRate(recorded_at=datetime.combine(date_val, datetime.min.time().replace(hour=12)),
                             bpm=s.min_heart_rate, measurement_type="min"))
            counts["heart_rate"] += 1

    return summaries


def _sync_daily_detail(
    client: AmazfitClient, db: Session,
    start: datetime, end: datetime, counts: dict[str, int],
) -> None:
    """Sync detailed daily data -> Sleep detail."""
    try:
        daily_data = client.get_daily_data(start, end)
        for dd in daily_data:
            dd_date = datetime.strptime(dd.date, "%Y-%m-%d").date()
            if dd.sleep:
                s = dd.sleep
                sleep_vals = {
                    "total_minutes": s.total_minutes or 0,
                    "deep_sleep_minutes": s.deep_sleep_minutes or 0,
                    "light_sleep_minutes": s.light_sleep_minutes or 0,
                    "rem_sleep_minutes": s.rem_sleep_minutes or 0,
                    "awake_minutes": s.awake_minutes or 0,
                    "sleep_score": s.sleep_score, "sleep_start": s.start_time,
                    "sleep_end": s.end_time, "sleep_onset_latency": s.sleep_onset_latency,
                    "wake_count": s.wake_count, "interruption_score": s.interruption_score,
                    "resting_heart_rate": s.resting_heart_rate,
                }
                stmt = pg_insert(SleepRecord).values(
                    sleep_date=dd_date, **sleep_vals,
                ).on_conflict_do_update(index_elements=["sleep_date"], set_=sleep_vals)
                db.execute(stmt)
                counts["sleep"] += 1
    except Exception as e:
        logger.warning(f"Daily detail data fetch failed: {e}")


def _sync_sleep_fallback(db: Session, summaries: list) -> None:
    """Insert sleep tu summary neu chua co tu daily_data."""
    for s in summaries:
        date_val = datetime.strptime(s.date, "%Y-%m-%d").date()
        stmt = pg_insert(SleepRecord).values(
            sleep_date=date_val, total_minutes=s.sleep_minutes or 0,
            deep_sleep_minutes=s.deep_sleep_minutes or 0,
            light_sleep_minutes=s.light_sleep_minutes or 0,
            rem_sleep_minutes=s.rem_sleep_minutes or 0, awake_minutes=0,
        ).on_conflict_do_nothing(index_elements=["sleep_date"])
        db.execute(stmt)


def _sync_stress(
    client: AmazfitClient, db: Session,
    start: datetime, end: datetime,
    start_date: date_type, end_date: date_type,
    counts: dict[str, int],
) -> None:
    """Sync stress detail readings + daily summary."""
    try:
        stress_list = client.get_stress_data(start, end)
        db.query(StressReading).filter(
            StressReading.reading_date.between(start_date, end_date)
        ).delete(synchronize_session=False)
        for sd in stress_list:
            reading_date = datetime.strptime(sd.date, "%Y-%m-%d").date()
            stress_vals = {
                "min_stress": sd.min_stress, "max_stress": sd.max_stress,
                "stress_relax_pct": sd.relax_proportion, "stress_normal_pct": sd.normal_proportion,
                "stress_medium_pct": sd.medium_proportion, "stress_high_pct": sd.high_proportion,
            }
            stmt = pg_insert(ActivityRecord).values(
                activity_date=reading_date, steps=0, calories=0, distance_meters=0,
                active_minutes=0, **stress_vals,
            ).on_conflict_do_update(index_elements=["activity_date"], set_=stress_vals)
            db.execute(stmt)
            for r in sd.readings:
                db.add(StressReading(reading_date=reading_date, recorded_at=r.timestamp,
                                     stress_value=r.value))
                counts["stress_readings"] += 1
    except Exception as e:
        logger.warning(f"Stress data fetch failed: {e}")


def _sync_spo2(
    client: AmazfitClient, db: Session,
    start: datetime, end: datetime,
    start_date: date_type, end_date: date_type,
    counts: dict[str, int],
) -> None:
    """Sync SpO2 detail readings + ODI."""
    try:
        spo2_list = client.get_spo2_data(start, end)
        db.query(SpO2Reading).filter(
            SpO2Reading.reading_date.between(start_date, end_date)
        ).delete(synchronize_session=False)
        for sp in spo2_list:
            reading_date = datetime.strptime(sp.date, "%Y-%m-%d").date()
            if sp.odi is not None:
                stmt = pg_insert(ActivityRecord).values(
                    activity_date=reading_date, steps=0, calories=0,
                    distance_meters=0, active_minutes=0, spo2_odi=sp.odi,
                ).on_conflict_do_update(index_elements=["activity_date"], set_={"spo2_odi": sp.odi})
                db.execute(stmt)
            for r in sp.readings:
                db.add(SpO2Reading(reading_date=reading_date, recorded_at=r.timestamp,
                                    spo2_value=r.spo2, reading_type=getattr(r, "reading_type", None)))
                counts["spo2_readings"] += 1
    except Exception as e:
        logger.warning(f"SpO2 data fetch failed: {e}")


def _sync_readiness(client: AmazfitClient, db: Session, start: datetime, end: datetime) -> None:
    """Sync readiness data (HRV, mental, physical, etc.) -> ActivityRecord."""
    try:
        readiness_list = client.get_readiness_data(start, end)
        for r in readiness_list:
            r_date = datetime.strptime(r.date, "%Y-%m-%d").date()
            readiness_vals = {
                "readiness_score": r.readiness_score, "readiness_insight": getattr(r, "readiness_insight", None),
                "hrv": r.hrv_baseline, "sleep_hrv": r.sleep_hrv,
                "hrv_score": getattr(r, "hrv_score", None), "rhr_score": getattr(r, "rhr_score", None),
                "rhr_baseline": getattr(r, "rhr_baseline", None), "sleep_rhr": getattr(r, "sleep_rhr", None),
                "mental_score": getattr(r, "mental_score", None), "mental_baseline": getattr(r, "mental_baseline", None),
                "physical_score": getattr(r, "physical_score", None), "physical_baseline": getattr(r, "physical_baseline", None),
                "afib_baseline": getattr(r, "afib_baseline", None), "ahi_score": getattr(r, "ahi_score", None),
                "ahi_baseline": getattr(r, "ahi_baseline", None),
            }
            stmt = pg_insert(ActivityRecord).values(
                activity_date=r_date, steps=0, calories=0, distance_meters=0,
                active_minutes=0, **readiness_vals,
            ).on_conflict_do_update(index_elements=["activity_date"], set_=readiness_vals)
            db.execute(stmt)
    except Exception as e:
        logger.warning(f"Readiness data fetch failed: {e}")


def _sync_workouts(
    client: AmazfitClient, db: Session,
    start: datetime, end: datetime,
    now_str: str, counts: dict[str, int],
) -> None:
    """Sync workouts (full detail)."""
    try:
        workouts = client.get_workouts(start, end)
        for w in workouts:
            workout_vals = {
                "workout_name": w.workout_name, "duration_seconds": w.duration_seconds,
                "distance_meters": w.distance_meters or 0, "calories": w.calories or 0,
                "avg_heart_rate": w.avg_heart_rate, "max_heart_rate": w.max_heart_rate,
                "min_heart_rate": w.min_heart_rate, "avg_pace": w.avg_pace,
                "total_steps": w.total_steps, "training_effect": w.training_effect,
                "anaerobic_te": getattr(w, "anaerobic_te", None),
                "exercise_load": getattr(w, "exercise_load", None),
                "avg_stride_length": getattr(w, "avg_stride_length", None),
                "pause_time": getattr(w, "pause_time", None), "synced_at": now_str,
            }
            stmt = pg_insert(WorkoutRecord).values(
                track_id=w.track_id, workout_type=w.workout_type,
                start_time=w.start_time, end_time=w.end_time, **workout_vals,
            ).on_conflict_do_update(index_elements=["track_id"], set_=workout_vals)
            db.execute(stmt)
            counts["workouts"] += 1
    except Exception as e:
        logger.warning(f"Workouts fetch failed: {e}")


def _sync_pai(client: AmazfitClient, db: Session, start: datetime, end: datetime) -> None:
    """Sync PAI detail -> ActivityRecord."""
    try:
        pai_list = client.get_pai_data(start, end)
        for p in pai_list:
            p_date = datetime.strptime(p.date, "%Y-%m-%d").date()
            pai_vals = {
                "daily_pai": getattr(p, "daily_pai", None),
                "pai_low_zone_min": getattr(p, "low_zone_minutes", None),
                "pai_medium_zone_min": getattr(p, "medium_zone_minutes", None),
                "pai_high_zone_min": getattr(p, "high_zone_minutes", None),
            }
            stmt = pg_insert(ActivityRecord).values(
                activity_date=p_date, steps=0, calories=0, distance_meters=0,
                active_minutes=0, **pai_vals,
            ).on_conflict_do_update(index_elements=["activity_date"], set_=pai_vals)
            db.execute(stmt)
    except Exception as e:
        logger.warning(f"PAI data fetch failed: {e}")


# ===================== Main sync orchestrator =====================

def sync_zepp_data(days: int = 1) -> dict:
    """
    Fetch toan bo du lieu tu Zepp API va upsert vao PostgreSQL.
    Bao gom: daily summaries, stress detail, SpO2 detail, readiness, workouts, PAI.
    """
    if not settings.zepp_app_token:
        return {"error": "ZEPP_APP_TOKEN chua cau hinh trong .env"}
    if not settings.zepp_user_id:
        return {"error": "ZEPP_USER_ID chua cau hinh trong .env"}

    start = datetime.now() - timedelta(days=days)
    end = datetime.now()
    now_str = datetime.now().isoformat()
    start_date = start.date()
    end_date = end.date()

    counts: dict[str, int] = {
        "heart_rate": 0, "sleep": 0, "activity": 0,
        "stress_readings": 0, "spo2_readings": 0, "workouts": 0,
    }
    db = SessionLocal()

    try:
        with AmazfitClient(
            app_token=settings.zepp_app_token,
            user_id=settings.zepp_user_id,
        ) as client:
            # Zepp API uses self-signed certificate
            client._http = client._http.__class__(
                timeout=30.0, follow_redirects=False, verify=False,
            )
            summaries = _sync_summaries(client, db, start, end, start_date, end_date, counts)
            _sync_daily_detail(client, db, start, end, counts)
            _sync_sleep_fallback(db, summaries)
            _sync_stress(client, db, start, end, start_date, end_date, counts)
            _sync_spo2(client, db, start, end, start_date, end_date, counts)
            _sync_readiness(client, db, start, end)
            _sync_workouts(client, db, start, end, now_str, counts)
            _sync_pai(client, db, start, end)

        db.commit()
        logger.info(f"Sync thanh cong: {counts}, synced_at={now_str}")
        return {"status": "success", "counts": counts, "synced_at": now_str}

    except Exception as e:
        db.rollback()
        logger.error(f"Sync that bai: {e}")
        return {"error": str(e)}
    finally:
        db.close()


def cron_sync_yesterday() -> None:
    """
    Ham duoc APScheduler goi luc 0:00 AM moi ngay.
    Sync du lieu ngay hom truoc (days=1) + xoa du lieu > 90 ngay.
    """
    logger.info("Cron sync started")
    result = sync_zepp_data(days=1)
    if "error" in result:
        logger.error(f"Cron sync failed: {result['error']}")
    else:
        logger.info(f"Cron sync completed: {result['counts']}")

    # Cleanup: xoa du lieu cu hon 90 ngay
    cleanup_old_data(keep_days=90)


def cleanup_old_data(keep_days: int = 90) -> dict[str, int]:
    """Xoa tat ca du lieu cu hon keep_days ngay."""
    cutoff = (datetime.now() - timedelta(days=keep_days)).date()
    db = SessionLocal()
    deleted: dict[str, int] = {}

    try:
        deleted["heart_rate"] = db.query(HeartRate).filter(
            sa_func.date(HeartRate.recorded_at) < cutoff
        ).delete(synchronize_session=False)

        deleted["sleep"] = db.query(SleepRecord).filter(
            SleepRecord.sleep_date < cutoff
        ).delete(synchronize_session=False)

        deleted["activity"] = db.query(ActivityRecord).filter(
            ActivityRecord.activity_date < cutoff
        ).delete(synchronize_session=False)

        deleted["stress"] = db.query(StressReading).filter(
            StressReading.reading_date < cutoff
        ).delete(synchronize_session=False)

        deleted["spo2"] = db.query(SpO2Reading).filter(
            SpO2Reading.reading_date < cutoff
        ).delete(synchronize_session=False)

        deleted["workouts"] = db.query(WorkoutRecord).filter(
            sa_func.date(WorkoutRecord.start_time) < cutoff
        ).delete(synchronize_session=False)

        db.commit()
        total = sum(deleted.values())
        if total > 0:
            logger.info(f"Cleanup: xoa {total} records cu hon {keep_days} ngay: {deleted}")
        return deleted
    except Exception as e:
        db.rollback()
        logger.error(f"Cleanup failed: {e}")
        return {}
    finally:
        db.close()