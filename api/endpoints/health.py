"""
Health Data Endpoints — Query dữ liệu từ PostgreSQL.
GET endpoints cho heart rate, sleep, activity.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.models.health import HeartRate, SleepRecord, ActivityRecord
from backend.schemas.health import (
    HeartRateResponse,
    SleepRecordResponse,
    ActivityRecordResponse,
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
    Trả về activity, sleep, heart rate gộp theo ngày.
    """
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=29)

    # Activity records
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

    # Build daily summary list
    all_dates = set[str]()
    activity_map = {str(a.activity_date): a for a in activities}
    sleep_map = {str(s.sleep_date): s for s in sleeps}

    all_dates.update(activity_map.keys())
    all_dates.update(sleep_map.keys())
    all_dates.update(hr_by_date.keys())

    daily_data = []
    for d in sorted(all_dates):
        act = activity_map.get(d)
        slp = sleep_map.get(d)
        hr = hr_by_date.get(d, {})
        daily_data.append({
            "date": d,
            "steps": act.steps if act else 0,
            "calories": act.calories if act else 0,
            "distance_meters": act.distance_meters if act else 0,
            "sleep_minutes": slp.total_minutes if slp else 0,
            "deep_sleep_minutes": slp.deep_sleep_minutes if slp else 0,
            "light_sleep_minutes": slp.light_sleep_minutes if slp else 0,
            "rem_sleep_minutes": slp.rem_sleep_minutes if slp else 0,
            "awake_minutes": slp.awake_minutes if slp else 0,
            "sleep_score": slp.sleep_score if slp else None,
            "resting_heart_rate": hr.get("resting"),
            "max_heart_rate": hr.get("max"),
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
