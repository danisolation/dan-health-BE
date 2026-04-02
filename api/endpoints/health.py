"""
Health Data Endpoints — Query dữ liệu từ PostgreSQL.
GET endpoints cho heart rate, sleep, activity, stress, SpO2, workouts.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.models.health import (
    HeartRate, SleepRecord, ActivityRecord,
    StressReading, SpO2Reading, WorkoutRecord,
)
from backend.schemas.health import (
    HeartRateResponse,
    SleepRecordResponse,
    ActivityRecordResponse,
    StressReadingResponse,
    SpO2ReadingResponse,
    WorkoutRecordResponse,
)

router = APIRouter(tags=["health"])


# ===================== Overview / Daily Summary =====================

@router.get("/overview")
def get_overview(
    start: str = Query(default=None, description="YYYY-MM-DD"),
    end: str = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Tổng hợp dữ liệu cho trang Overview.
    Trả về activity, sleep, heart rate, stress, SpO2, HRV, PAI gộp theo ngày.
    """
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=29)

    # Activity records (bao gồm readiness, hrv, stress zones, PAI)
    activities = (
        db.query(ActivityRecord)
        .filter(ActivityRecord.activity_date.between(start_date, end_date))
        .order_by(ActivityRecord.activity_date)
        .all()
    )

    # Sleep records
    sleeps = (
        db.query(SleepRecord)
        .filter(SleepRecord.sleep_date.between(start_date, end_date))
        .order_by(SleepRecord.sleep_date)
        .all()
    )

    # Compute avg_stress per day from StressReading detail
    stress_avg = dict(
        db.query(
            StressReading.reading_date,
            func.round(func.avg(StressReading.stress_value)).label("avg"),
        )
        .filter(StressReading.reading_date.between(start_date, end_date))
        .group_by(StressReading.reading_date)
        .all()
    )

    # Compute avg_spo2 per day from SpO2Reading detail
    spo2_avg = dict(
        db.query(
            SpO2Reading.reading_date,
            func.round(func.avg(SpO2Reading.spo2_value)).label("avg"),
        )
        .filter(SpO2Reading.reading_date.between(start_date, end_date))
        .group_by(SpO2Reading.reading_date)
        .all()
    )

    # Heart rate: lấy resting + max theo ngày
    hr_records = (
        db.query(
            func.date(HeartRate.recorded_at).label("date"),
            HeartRate.measurement_type,
            HeartRate.bpm,
        )
        .filter(func.date(HeartRate.recorded_at).between(start_date, end_date))
        .order_by(func.date(HeartRate.recorded_at))
        .all()
    )

    # Gộp HR theo ngày
    hr_by_date: dict[str, dict[str, int | None]] = {}
    for row in hr_records:
        d = str(row.date)
        if d not in hr_by_date:
            hr_by_date[d] = {"resting": None, "max": None}
        if row.measurement_type == "resting":
            hr_by_date[d]["resting"] = row.bpm
        elif row.measurement_type == "max":
            hr_by_date[d]["max"] = row.bpm

    # Workout avg HR theo ngày (weighted average từ tất cả workouts trong ngày)
    workouts = (
        db.query(WorkoutRecord)
        .filter(func.date(WorkoutRecord.start_time).between(start_date, end_date))
        .all()
    )
    workout_hr_by_date: dict[str, dict] = {}
    for w in workouts:
        d = str(w.start_time.date())
        if d not in workout_hr_by_date:
            workout_hr_by_date[d] = {"total_dur": 0, "weighted_hr": 0, "max": 0, "min": 999, "count": 0}
        entry = workout_hr_by_date[d]
        entry["count"] += 1
        if w.avg_heart_rate and w.duration_seconds:
            entry["total_dur"] += w.duration_seconds
            entry["weighted_hr"] += w.avg_heart_rate * w.duration_seconds
        if w.max_heart_rate:
            entry["max"] = max(entry["max"], w.max_heart_rate)
        if w.min_heart_rate:
            entry["min"] = min(entry["min"], w.min_heart_rate)

    # Build daily summary list
    all_dates = set[str]()
    activity_map = {str(a.activity_date): a for a in activities}
    sleep_map = {str(s.sleep_date): s for s in sleeps}

    all_dates.update(activity_map.keys())
    all_dates.update(sleep_map.keys())
    all_dates.update(hr_by_date.keys())

    all_dates.update(workout_hr_by_date.keys())

    daily_data = []
    for d in sorted(all_dates):
        act = activity_map.get(d)
        slp = sleep_map.get(d)
        hr = hr_by_date.get(d, {})
        whr = workout_hr_by_date.get(d)
        daily_data.append({
            "date": d,
            # Activity basics
            "steps": act.steps if act else 0,
            "calories": act.calories if act else 0,
            "distance_meters": act.distance_meters if act else 0,
            # Sleep
            "sleep_minutes": slp.total_minutes if slp else 0,
            "deep_sleep_minutes": slp.deep_sleep_minutes if slp else 0,
            "light_sleep_minutes": slp.light_sleep_minutes if slp else 0,
            "rem_sleep_minutes": slp.rem_sleep_minutes if slp else 0,
            "awake_minutes": slp.awake_minutes if slp else 0,
            "sleep_score": slp.sleep_score if slp else None,
            "sleep_start": slp.sleep_start.isoformat() if slp and slp.sleep_start else None,
            "sleep_end": slp.sleep_end.isoformat() if slp and slp.sleep_end else None,
            "sleep_onset_latency": slp.sleep_onset_latency if slp else None,
            "wake_count": slp.wake_count if slp else None,
            "interruption_score": slp.interruption_score if slp else None,
            "sleep_resting_hr": slp.resting_heart_rate if slp else None,
            # Heart rate
            "resting_heart_rate": hr.get("resting"),
            "max_heart_rate": hr.get("max"),
            # Stress
            "avg_stress": stress_avg.get(date.fromisoformat(d)),
            "min_stress": act.min_stress if act else None,
            "max_stress": act.max_stress if act else None,
            "stress_relax_pct": act.stress_relax_pct if act else None,
            "stress_normal_pct": act.stress_normal_pct if act else None,
            "stress_medium_pct": act.stress_medium_pct if act else None,
            "stress_high_pct": act.stress_high_pct if act else None,
            # SpO2
            "avg_spo2": spo2_avg.get(date.fromisoformat(d)),
            "spo2_odi": act.spo2_odi if act else None,
            # PAI
            "daily_pai": act.daily_pai if act else None,
            "pai_low_zone_min": act.pai_low_zone_min if act else None,
            "pai_medium_zone_min": act.pai_medium_zone_min if act else None,
            "pai_high_zone_min": act.pai_high_zone_min if act else None,
            # Readiness / HRV
            "readiness_score": act.readiness_score if act else None,
            "readiness_insight": act.readiness_insight if act else None,
            "hrv": act.hrv if act else None,
            "sleep_hrv": act.sleep_hrv if act else None,
            "hrv_score": act.hrv_score if act else None,
            # Body scores
            "rhr_score": act.rhr_score if act else None,
            "rhr_baseline": act.rhr_baseline if act else None,
            "sleep_rhr": act.sleep_rhr if act else None,
            "mental_score": act.mental_score if act else None,
            "mental_baseline": act.mental_baseline if act else None,
            "physical_score": act.physical_score if act else None,
            "physical_baseline": act.physical_baseline if act else None,
            # Medical
            "afib_baseline": act.afib_baseline if act else None,
            "ahi_score": act.ahi_score if act else None,
            "ahi_baseline": act.ahi_baseline if act else None,
            # Workout HR
            "workout_avg_hr": round(whr["weighted_hr"] / whr["total_dur"]) if whr and whr["total_dur"] > 0 else None,
            "workout_max_hr": whr["max"] if whr and whr["max"] > 0 else None,
            "workout_min_hr": whr["min"] if whr and whr["min"] < 999 else None,
            "workout_count": whr["count"] if whr else 0,
        })

    return {"data": daily_data}


# ===================== Heart Rate =====================

@router.get("/heart-rate", response_model=list[HeartRateResponse])
def get_heart_rates(
    start: str = Query(default=None, description="YYYY-MM-DD"),
    end: str = Query(default=None, description="YYYY-MM-DD"),
    measurement_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[HeartRate]:
    """Query heart rate records theo khoảng ngày và loại đo."""
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=29)

    query = db.query(HeartRate).filter(
        func.date(HeartRate.recorded_at).between(start_date, end_date)
    )
    if measurement_type:
        query = query.filter(HeartRate.measurement_type == measurement_type)

    return query.order_by(HeartRate.recorded_at).all()


# ===================== Sleep =====================

@router.get("/sleep", response_model=list[SleepRecordResponse])
def get_sleep_records(
    start: str = Query(default=None, description="YYYY-MM-DD"),
    end: str = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> list[SleepRecord]:
    """Query sleep records theo khoảng ngày."""
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=29)

    return (
        db.query(SleepRecord)
        .filter(SleepRecord.sleep_date.between(start_date, end_date))
        .order_by(SleepRecord.sleep_date)
        .all()
    )


# ===================== Activity =====================

@router.get("/activity", response_model=list[ActivityRecordResponse])
def get_activity_records(
    start: str = Query(default=None, description="YYYY-MM-DD"),
    end: str = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> list[ActivityRecord]:
    """Query activity records theo khoảng ngày."""
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=29)

    return (
        db.query(ActivityRecord)
        .filter(ActivityRecord.activity_date.between(start_date, end_date))
        .order_by(ActivityRecord.activity_date)
        .all()
    )


# ===================== Stress =====================

@router.get("/stress", response_model=list[StressReadingResponse])
def get_stress_readings(
    start: str = Query(default=None, description="YYYY-MM-DD"),
    end: str = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> list[StressReading]:
    """Query stress detail readings theo khoảng ngày."""
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=29)

    return (
        db.query(StressReading)
        .filter(StressReading.reading_date.between(start_date, end_date))
        .order_by(StressReading.recorded_at)
        .all()
    )


# ===================== SpO2 =====================

@router.get("/spo2", response_model=list[SpO2ReadingResponse])
def get_spo2_readings(
    start: str = Query(default=None, description="YYYY-MM-DD"),
    end: str = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> list[SpO2Reading]:
    """Query SpO2 detail readings theo khoảng ngày."""
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=29)

    return (
        db.query(SpO2Reading)
        .filter(SpO2Reading.reading_date.between(start_date, end_date))
        .order_by(SpO2Reading.recorded_at)
        .all()
    )


# ===================== Workouts =====================

@router.get("/workouts", response_model=list[WorkoutRecordResponse])
def get_workouts(
    start: str = Query(default=None, description="YYYY-MM-DD"),
    end: str = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> list[WorkoutRecord]:
    """Query workouts theo khoảng ngày."""
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=29)

    return (
        db.query(WorkoutRecord)
        .filter(func.date(WorkoutRecord.start_time).between(start_date, end_date))
        .order_by(WorkoutRecord.start_time.desc())
        .all()
    )
