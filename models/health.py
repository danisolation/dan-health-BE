"""
Health Data Models — Schema cho dữ liệu sức khỏe từ Amazfit Bip 6.
Bao gồm: Heart Rate, Sleep, Activity (Steps/Calories).

Thiết kế dựa trên cấu trúc dữ liệu existing trong app/database.py
nhưng tách riêng thành các bảng chuyên biệt hơn cho phân tích.
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
    # Loại đo: "resting", "active", "max", "auto" (đo tự động từ đồng hồ)
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
    Bảng lưu dữ liệu vận động theo ngày.
    Mỗi record = tóm tắt hoạt động 1 ngày (steps, calories, distance).
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
