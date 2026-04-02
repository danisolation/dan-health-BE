"""
Sync Service — Kéo toàn bộ dữ liệu từ Zepp API và lưu vào Aiven PostgreSQL.
Bao gồm: daily summaries, stress, SpO2, readiness, workouts.
"""
import logging
from datetime import datetime, timedelta

import httpx
from amazfit_cli import AmazfitClient
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.models.health import (
    HeartRate, SleepRecord, ActivityRecord,
    StressReading, SpO2Reading, WorkoutRecord,
)

logger = logging.getLogger(__name__)


def sync_zepp_data(days: int = 1) -> dict:
    """
    Fetch toàn bộ dữ liệu từ Zepp API và upsert vào PostgreSQL.
    Bao gồm: daily summaries, stress detail, SpO2 detail, readiness, workouts.
    """
    if not settings.zepp_app_token:
        return {"error": "ZEPP_APP_TOKEN chưa cấu hình trong .env"}
    if not settings.zepp_user_id:
        return {"error": "ZEPP_USER_ID chưa cấu hình trong .env"}

    start = datetime.now() - timedelta(days=days)
    end = datetime.now()
    now_str = datetime.now().isoformat()

    counts = {
        "heart_rate": 0, "sleep": 0, "activity": 0,
        "stress_readings": 0, "spo2_readings": 0, "workouts": 0,
        "hr_detail": 0,
    }
    db = SessionLocal()

    try:
        with AmazfitClient(
            app_token=settings.zepp_app_token,
            user_id=settings.zepp_user_id,
        ) as client:
            # Tắt SSL verify cho mạng có proxy/cert inspection
            client._http = httpx.Client(timeout=30.0, follow_redirects=False, verify=False)

            # --- 1. Daily summaries → Activity + Heart Rate ---
            # Use get_summary (has min_heart_rate) instead of get_aggregate_summary
            summaries = client.get_summary(start, end)
            
            # Delete existing HR records for this date range to avoid duplicates
            start_date = start.date() if hasattr(start, 'date') else start
            end_date = end.date() if hasattr(end, 'date') else end
            from sqlalchemy import func as sa_func
            db.query(HeartRate).filter(
                sa_func.date(HeartRate.recorded_at).between(start_date, end_date)
            ).delete(synchronize_session=False)
            
            for s in summaries:
                date_val = datetime.strptime(s.date, "%Y-%m-%d").date()

                # Activity record (steps, calories, distance + daily aggregates)
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

                # Heart rate (resting + min theo ngày, 1 record mỗi loại)
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
                if s.min_heart_rate and s.min_heart_rate != s.resting_heart_rate:
                    db.add(HeartRate(
                        recorded_at=datetime.combine(date_val, datetime.min.time().replace(hour=12)),
                        bpm=s.min_heart_rate,
                        measurement_type="min",
                    ))
                    counts["heart_rate"] += 1

            # --- 1b. Detailed daily data → Sleep detail + HR detail ---
            try:
                daily_data = client.get_daily_data(start, end)
                for dd in daily_data:
                    dd_date = datetime.strptime(dd.date, "%Y-%m-%d").date()

                    # Sleep detail
                    if dd.sleep:
                        s = dd.sleep
                        stmt = pg_insert(SleepRecord).values(
                            sleep_date=dd_date,
                            total_minutes=s.total_minutes or 0,
                            deep_sleep_minutes=s.deep_sleep_minutes or 0,
                            light_sleep_minutes=s.light_sleep_minutes or 0,
                            rem_sleep_minutes=s.rem_sleep_minutes or 0,
                            awake_minutes=s.awake_minutes or 0,
                            sleep_score=s.sleep_score,
                            sleep_start=s.start_time,
                            sleep_end=s.end_time,
                            sleep_onset_latency=s.sleep_onset_latency,
                            wake_count=s.wake_count,
                            interruption_score=s.interruption_score,
                            resting_heart_rate=s.resting_heart_rate,
                        ).on_conflict_do_update(
                            index_elements=["sleep_date"],
                            set_={
                                "total_minutes": s.total_minutes or 0,
                                "deep_sleep_minutes": s.deep_sleep_minutes or 0,
                                "light_sleep_minutes": s.light_sleep_minutes or 0,
                                "rem_sleep_minutes": s.rem_sleep_minutes or 0,
                                "awake_minutes": s.awake_minutes or 0,
                                "sleep_score": s.sleep_score,
                                "sleep_start": s.start_time,
                                "sleep_end": s.end_time,
                                "sleep_onset_latency": s.sleep_onset_latency,
                                "wake_count": s.wake_count,
                                "interruption_score": s.interruption_score,
                                "resting_heart_rate": s.resting_heart_rate,
                            },
                        )
                        db.execute(stmt)
                        counts["sleep"] += 1

                    # HR detail from daily_data is same as summary resting HR
                    # (Zepp API doesn't provide per-minute HR via cloud)
                    # Skip to avoid duplicates - resting HR already captured in section 1
            except Exception as e:
                logger.warning(f"Daily detail data fetch failed: {e}")

            # --- Fallback: insert sleep từ summary nếu chưa có từ daily_data ---
            for s in summaries:
                date_val = datetime.strptime(s.date, "%Y-%m-%d").date()
                stmt = pg_insert(SleepRecord).values(
                    sleep_date=date_val,
                    total_minutes=s.sleep_minutes or 0,
                    deep_sleep_minutes=s.deep_sleep_minutes or 0,
                    light_sleep_minutes=s.light_sleep_minutes or 0,
                    rem_sleep_minutes=s.rem_sleep_minutes or 0,
                    awake_minutes=0,
                ).on_conflict_do_nothing(index_elements=["sleep_date"])
                db.execute(stmt)

            # --- 2. Stress detail readings + daily summary ---
            try:
                stress_list = client.get_stress_data(start, end)
                # Delete existing stress readings for date range to avoid duplicates
                db.query(StressReading).filter(
                    StressReading.reading_date.between(start_date, end_date)
                ).delete(synchronize_session=False)
                for sd in stress_list:
                    reading_date = datetime.strptime(sd.date, "%Y-%m-%d").date()
                    # Update activity_record with stress daily summary
                    stmt = pg_insert(ActivityRecord).values(
                        activity_date=reading_date,
                        steps=0, calories=0, distance_meters=0, active_minutes=0,
                        min_stress=sd.min_stress,
                        max_stress=sd.max_stress,
                        stress_relax_pct=sd.relax_proportion,
                        stress_normal_pct=sd.normal_proportion,
                        stress_medium_pct=sd.medium_proportion,
                        stress_high_pct=sd.high_proportion,
                    ).on_conflict_do_update(
                        index_elements=["activity_date"],
                        set_={
                            "min_stress": sd.min_stress,
                            "max_stress": sd.max_stress,
                            "stress_relax_pct": sd.relax_proportion,
                            "stress_normal_pct": sd.normal_proportion,
                            "stress_medium_pct": sd.medium_proportion,
                            "stress_high_pct": sd.high_proportion,
                        },
                    )
                    db.execute(stmt)
                    for r in sd.readings:
                        db.add(StressReading(
                            reading_date=reading_date,
                            recorded_at=r.timestamp,
                            stress_value=r.value,
                        ))
                        counts["stress_readings"] += 1
            except Exception as e:
                logger.warning(f"Stress data fetch failed: {e}")

            # --- 3. SpO2 detail readings + ODI ---
            try:
                spo2_list = client.get_spo2_data(start, end)
                # Delete existing SpO2 readings for date range to avoid duplicates
                db.query(SpO2Reading).filter(
                    SpO2Reading.reading_date.between(start_date, end_date)
                ).delete(synchronize_session=False)
                for sp in spo2_list:
                    reading_date = datetime.strptime(sp.date, "%Y-%m-%d").date()
                    # Update activity_record with SpO2 ODI
                    if sp.odi is not None:
                        stmt = pg_insert(ActivityRecord).values(
                            activity_date=reading_date,
                            steps=0, calories=0, distance_meters=0, active_minutes=0,
                            spo2_odi=sp.odi,
                        ).on_conflict_do_update(
                            index_elements=["activity_date"],
                            set_={"spo2_odi": sp.odi},
                        )
                        db.execute(stmt)
                    for r in sp.readings:
                        db.add(SpO2Reading(
                            reading_date=reading_date,
                            recorded_at=r.timestamp,
                            spo2_value=r.spo2,
                            reading_type=getattr(r, "reading_type", None),
                        ))
                        counts["spo2_readings"] += 1
            except Exception as e:
                logger.warning(f"SpO2 data fetch failed: {e}")

            # --- 4. Readiness data (HRV, skin temp, mental, physical, etc.) → update ActivityRecord ---
            try:
                readiness_list = client.get_readiness_data(start, end)
                for r in readiness_list:
                    r_date = datetime.strptime(r.date, "%Y-%m-%d").date()
                    readiness_vals = {
                        "readiness_score": r.readiness_score,
                        "readiness_insight": getattr(r, "readiness_insight", None),
                        "hrv": r.hrv_baseline,
                        "sleep_hrv": r.sleep_hrv,
                        "hrv_score": getattr(r, "hrv_score", None),
                        "rhr_score": getattr(r, "rhr_score", None),
                        "rhr_baseline": getattr(r, "rhr_baseline", None),
                        "sleep_rhr": getattr(r, "sleep_rhr", None),
                        "mental_score": getattr(r, "mental_score", None),
                        "mental_baseline": getattr(r, "mental_baseline", None),
                        "physical_score": getattr(r, "physical_score", None),
                        "physical_baseline": getattr(r, "physical_baseline", None),
                        "afib_baseline": getattr(r, "afib_baseline", None),
                        "ahi_score": getattr(r, "ahi_score", None),
                        "ahi_baseline": getattr(r, "ahi_baseline", None),
                    }
                    stmt = pg_insert(ActivityRecord).values(
                        activity_date=r_date,
                        steps=0, calories=0, distance_meters=0, active_minutes=0,
                        **readiness_vals,
                    ).on_conflict_do_update(
                        index_elements=["activity_date"],
                        set_=readiness_vals,
                    )
                    db.execute(stmt)
            except Exception as e:
                logger.warning(f"Readiness data fetch failed: {e}")

            # --- 5. Workouts (full detail) ---
            try:
                workouts = client.get_workouts(start, end)
                for w in workouts:
                    workout_vals = {
                        "workout_name": w.workout_name,
                        "duration_seconds": w.duration_seconds,
                        "distance_meters": w.distance_meters or 0,
                        "calories": w.calories or 0,
                        "avg_heart_rate": w.avg_heart_rate,
                        "max_heart_rate": w.max_heart_rate,
                        "min_heart_rate": w.min_heart_rate,
                        "avg_pace": w.avg_pace,
                        "total_steps": w.total_steps,
                        "training_effect": w.training_effect,
                        "anaerobic_te": getattr(w, "anaerobic_te", None),
                        "exercise_load": getattr(w, "exercise_load", None),
                        "avg_stride_length": getattr(w, "avg_stride_length", None),
                        "pause_time": getattr(w, "pause_time", None),
                        "synced_at": now_str,
                    }
                    stmt = pg_insert(WorkoutRecord).values(
                        track_id=w.track_id,
                        workout_type=w.workout_type,
                        start_time=w.start_time,
                        end_time=w.end_time,
                        **workout_vals,
                    ).on_conflict_do_update(
                        index_elements=["track_id"],
                        set_=workout_vals,
                    )
                    db.execute(stmt)
                    counts["workouts"] += 1
            except Exception as e:
                logger.warning(f"Workouts fetch failed: {e}")

            # --- 6. PAI detail → update ActivityRecord ---
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
                        activity_date=p_date,
                        steps=0, calories=0, distance_meters=0, active_minutes=0,
                        **pai_vals,
                    ).on_conflict_do_update(
                        index_elements=["activity_date"],
                        set_=pai_vals,
                    )
                    db.execute(stmt)
            except Exception as e:
                logger.warning(f"PAI data fetch failed: {e}")

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
