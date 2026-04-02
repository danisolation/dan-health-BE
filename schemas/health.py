"""
Pydantic Schemas — Validate dữ liệu đầu vào cho health data.
Sử dụng cho request body validation trong FastAPI endpoints.
"""
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator


# ===================== Heart Rate =====================

class HeartRateCreate(BaseModel):
    """Schema validate dữ liệu nhịp tim khi upload."""
    recorded_at: datetime = Field(..., description="Thời điểm đo (ISO 8601)")
    bpm: int = Field(..., ge=1, le=300, description="Nhịp tim (beats per minute)")
    measurement_type: str | None = Field(
        default="auto", description="Loại đo: resting, active, max, auto"
    )

    @field_validator("measurement_type")
    @classmethod
    def validate_measurement_type(cls, v: str | None) -> str | None:
        allowed = {"resting", "active", "max", "auto", None}
        if v not in allowed:
            raise ValueError(f"measurement_type phải là một trong: {allowed}")
        return v


class HeartRateResponse(BaseModel):
    """Schema response trả về cho heart rate data."""
    id: int
    recorded_at: datetime
    bpm: int
    measurement_type: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ===================== Sleep =====================

class SleepRecordCreate(BaseModel):
    """Schema validate dữ liệu giấc ngủ khi upload."""
    sleep_date: date = Field(..., description="Ngày ghi nhận giấc ngủ")
    total_minutes: int = Field(default=0, ge=0, description="Tổng thời gian ngủ (phút)")
    deep_sleep_minutes: int = Field(default=0, ge=0, description="Ngủ sâu (phút)")
    light_sleep_minutes: int = Field(default=0, ge=0, description="Ngủ nhẹ (phút)")
    rem_sleep_minutes: int = Field(default=0, ge=0, description="REM (phút)")
    awake_minutes: int = Field(default=0, ge=0, description="Thức giữa đêm (phút)")
    sleep_score: int | None = Field(
        default=None, ge=0, le=100, description="Điểm giấc ngủ (0-100)"
    )


class SleepRecordResponse(BaseModel):
    """Schema response cho sleep data."""
    id: int
    sleep_date: date
    total_minutes: int
    deep_sleep_minutes: int
    light_sleep_minutes: int
    rem_sleep_minutes: int
    awake_minutes: int
    sleep_score: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ===================== Activity =====================

class ActivityRecordCreate(BaseModel):
    """Schema validate dữ liệu vận động khi upload."""
    activity_date: date = Field(..., description="Ngày ghi nhận hoạt động")
    steps: int = Field(default=0, ge=0, description="Tổng bước chân")
    calories: int = Field(default=0, ge=0, description="Calories tiêu hao (kcal)")
    distance_meters: int = Field(default=0, ge=0, description="Quãng đường (mét)")
    active_minutes: int = Field(default=0, ge=0, description="Phút vận động tích cực")


class ActivityRecordResponse(BaseModel):
    """Schema response cho activity data."""
    id: int
    activity_date: date
    steps: int
    calories: int
    distance_meters: int
    active_minutes: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ===================== Upload Wrapper =====================

class AmazfitUploadData(BaseModel):
    """
    Schema tổng hợp cho endpoint upload.
    Client có thể gửi 1 hoặc nhiều loại dữ liệu trong 1 lần upload.
    """
    heart_rates: list[HeartRateCreate] = Field(default_factory=list)
    sleep_records: list[SleepRecordCreate] = Field(default_factory=list)
    activity_records: list[ActivityRecordCreate] = Field(default_factory=list)


class UploadResponse(BaseModel):
    """Response sau khi upload thành công."""
    status: str = "success"
    inserted: dict[str, int] = Field(
        default_factory=dict,
        description="Số records đã insert theo từng loại",
    )
