"""
Health Data Models — Schema cho dữ liệu sức khỏe từ Amazfit Bip 6.
Bao gồm: Heart Rate, Sleep, Activity, Stress, SpO2, Workouts.
"""
from datetime import date, datetime
from sqlalchemy import (
    Integer, Float, String, Date, DateTime, SmallInteger,
    CheckConstraint, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class HeartRate(Base):
    """
    Bảng lưu dữ liệu nhịp tim.
    Mỗi record = 1 lần đo (hoặc 1 bản tóm tắt theo ngày).
    """
    __tablename__ = "heart_rate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Thời điểm đo"
    )
    bpm: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="Nhịp tim (beats per minute)"
    )
    measurement_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="auto"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("bpm > 0 AND bpm < 300", name="ck_heart_rate_bpm_range"),
        Index("ix_heart_rate_recorded_at", "recorded_at"),
    )

    def __repr__(self) -> str:
        return f"<HeartRate {self.recorded_at}: {self.bpm} bpm>"


class SleepRecord(Base):
    """
    Bảng lưu dữ liệu giấc ngủ theo ngày.
    Mỗi record = 1 đêm ngủ, chứa phân tích các giai đoạn.
    """
    __tablename__ = "sleep_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sleep_date: Mapped[date] = mapped_column(
        Date, nullable=False, unique=True, comment="Ngày ghi nhận giấc ngủ"
    )
    total_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Tổng thời gian ngủ (phút)"
    )
    deep_sleep_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Ngủ sâu (phút)"
    )
    light_sleep_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Ngủ nhẹ (phút)"
    )
    rem_sleep_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="REM (phút)"
    )
    awake_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Thời gian tỉnh giấc giữa đêm (phút)"
    )
    sleep_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Điểm giấc ngủ (0-100)"
    )
    # Chi tiết giấc ngủ từ ActivityData.sleep
    sleep_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Thời gian bắt đầu ngủ"
    )
    sleep_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Thời gian thức dậy"
    )
    sleep_onset_latency: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Thời gian chìm vào giấc ngủ (phút)"
    )
    wake_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Số lần thức giấc"
    )
    interruption_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Điểm gián đoạn giấc ngủ"
    )
    resting_heart_rate: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Nhịp tim khi ngủ"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("total_minutes >= 0", name="ck_sleep_total_positive"),
        CheckConstraint(
            "sleep_score IS NULL OR (sleep_score >= 0 AND sleep_score <= 100)",
            name="ck_sleep_score_range",
        ),
        Index("ix_sleep_record_date", "sleep_date"),
    )

    def __repr__(self) -> str:
        return f"<SleepRecord {self.sleep_date}: {self.total_minutes}min>"


class ActivityRecord(Base):
    """
    Bảng lưu dữ liệu vận động + tổng hợp metrics hàng ngày.
    Bao gồm: steps, calories, distance + avg_stress, avg_spo2, PAI, readiness, HRV.
    """
    __tablename__ = "activity_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_date: Mapped[date] = mapped_column(
        Date, nullable=False, unique=True, comment="Ngày ghi nhận"
    )
    steps: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Tổng số bước"
    )
    calories: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Calories tiêu hao (kcal)"
    )
    distance_meters: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Quãng đường (mét)"
    )
    active_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Thời gian vận động tích cực (phút)"
    )
    # (avg_stress, avg_spo2, total_pai removed — always null from Zepp API)
    # Readiness / HRV
    readiness_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Điểm readiness (0-100)"
    )
    hrv: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="HRV baseline (ms)"
    )
    sleep_hrv: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="HRV khi ngủ (ms)"
    )

    # Readiness chi tiết
    readiness_insight: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Readiness insight"
    )
    rhr_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Resting HR score"
    )
    rhr_baseline: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Resting HR baseline"
    )
    sleep_rhr: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Nhịp tim khi ngủ"
    )
    hrv_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="HRV score"
    )

    # Mức thể chất & mệt mỏi
    mental_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Mental score (mức mệt mỏi)"
    )
    mental_baseline: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Mental baseline"
    )
    physical_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Physical score (mức thể chất)"
    )
    physical_baseline: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Physical baseline"
    )
    # AFib & AHI
    afib_baseline: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="AFib baseline"
    )
    ahi_score: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="AHI score"
    )
    ahi_baseline: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="AHI baseline"
    )
    # Stress daily summary
    min_stress: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Stress thấp nhất ngày"
    )
    max_stress: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Stress cao nhất ngày"
    )
    stress_relax_pct: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="% thời gian thư giãn"
    )
    stress_normal_pct: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="% thời gian bình thường"
    )
    stress_medium_pct: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="% thời gian stress trung bình"
    )
    stress_high_pct: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="% thời gian stress cao"
    )
    # PAI chi tiết
    daily_pai: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="PAI kiếm được trong ngày"
    )
    pai_low_zone_min: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="PAI low zone minutes"
    )
    pai_medium_zone_min: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="PAI medium zone minutes"
    )
    pai_high_zone_min: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="PAI high zone minutes"
    )
    # SpO2 daily
    spo2_odi: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Oxygen Desaturation Index"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("steps >= 0", name="ck_activity_steps_positive"),
        CheckConstraint("calories >= 0", name="ck_activity_calories_positive"),
        Index("ix_activity_record_date", "activity_date"),
    )

    def __repr__(self) -> str:
        return f"<ActivityRecord {self.activity_date}: {self.steps} steps>"


class StressReading(Base):
    """Chi tiết stress từng lần đo trong ngày."""
    __tablename__ = "stress_reading"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Ngày đo"
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Timestamp đo"
    )
    stress_value: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="Giá trị stress (0-100)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("stress_value >= 0 AND stress_value <= 100", name="ck_stress_range"),
        Index("ix_stress_reading_date", "reading_date"),
        Index("ix_stress_reading_recorded_at", "recorded_at"),
    )

    def __repr__(self) -> str:
        return f"<StressReading {self.recorded_at}: {self.stress_value}>"


class SpO2Reading(Base):
    """Chi tiết SpO2 từng lần đo trong ngày."""
    __tablename__ = "spo2_reading"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Ngày đo"
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Timestamp đo"
    )
    spo2_value: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="SpO2 (%)"
    )
    reading_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="Loại đo: auto, manual"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("spo2_value >= 0 AND spo2_value <= 100", name="ck_spo2_range"),
        Index("ix_spo2_reading_date", "reading_date"),
        Index("ix_spo2_reading_recorded_at", "recorded_at"),
    )

    def __repr__(self) -> str:
        return f"<SpO2Reading {self.recorded_at}: {self.spo2_value}%>"


class WorkoutRecord(Base):
    """Bảng lưu workout/exercise sessions."""
    __tablename__ = "workout_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, comment="Zepp track ID"
    )
    workout_type: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Mã loại bài tập"
    )
    workout_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Tên bài tập"
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Thời gian bắt đầu"
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Thời gian kết thúc"
    )
    duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Thời lượng (giây)"
    )
    distance_meters: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Quãng đường (mét)"
    )
    calories: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Calories tiêu hao"
    )
    avg_heart_rate: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Nhịp tim trung bình"
    )
    max_heart_rate: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Nhịp tim tối đa"
    )
    min_heart_rate: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="Nhịp tim tối thiểu"
    )
    avg_pace: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Pace trung bình (min/km)"
    )
    total_steps: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Tổng bước"
    )
    training_effect: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Training Effect (1.0-5.0)"
    )
    # Extended workout fields
    anaerobic_te: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Anaerobic Training Effect"
    )
    exercise_load: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Exercise Load (gắng sức)"
    )
    avg_stride_length: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Bước chân trung bình (m)"
    )
    pause_time: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Thời gian nghỉ (giây)"
    )
    synced_at: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="Thời điểm sync"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("duration_seconds >= 0", name="ck_workout_duration_positive"),
        Index("ix_workout_start_time", "start_time"),
    )

    def __repr__(self) -> str:
        return f"<WorkoutRecord {self.workout_name} @ {self.start_time}>"
