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
    sleep_score: int | None = Field(default=None, ge=0, le=100)
    sleep_start: datetime | None = None
    sleep_end: datetime | None = None
    sleep_onset_latency: int | None = None
    wake_count: int | None = None
    interruption_score: int | None = None
    resting_heart_rate: int | None = None


class SleepRecordResponse(BaseModel):
    id: int
    sleep_date: date
    total_minutes: int
    deep_sleep_minutes: int
    light_sleep_minutes: int
    rem_sleep_minutes: int
    awake_minutes: int
    sleep_score: int | None
    sleep_start: datetime | None
    sleep_end: datetime | None
    sleep_onset_latency: int | None
    wake_count: int | None
    interruption_score: int | None
    resting_heart_rate: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ===================== Activity =====================

class ActivityRecordCreate(BaseModel):
    activity_date: date = Field(...)
    steps: int = Field(default=0, ge=0)
    calories: int = Field(default=0, ge=0)
    distance_meters: int = Field(default=0, ge=0)
    active_minutes: int = Field(default=0, ge=0)
    readiness_score: int | None = None
    hrv: float | None = None
    sleep_hrv: float | None = None
    # Readiness detail
    readiness_insight: int | None = None
    rhr_score: int | None = None
    rhr_baseline: int | None = None
    sleep_rhr: int | None = None
    hrv_score: int | None = None
    mental_score: int | None = None
    mental_baseline: int | None = None
    physical_score: int | None = None
    physical_baseline: int | None = None
    afib_baseline: int | None = None
    ahi_score: int | None = None
    ahi_baseline: float | None = None
    # Stress daily
    min_stress: int | None = None
    max_stress: int | None = None
    stress_relax_pct: int | None = None
    stress_normal_pct: int | None = None
    stress_medium_pct: int | None = None
    stress_high_pct: int | None = None
    # PAI detail
    daily_pai: float | None = None
    pai_low_zone_min: int | None = None
    pai_medium_zone_min: int | None = None
    pai_high_zone_min: int | None = None
    # SpO2 daily
    spo2_odi: float | None = None


class ActivityRecordResponse(BaseModel):
    id: int
    activity_date: date
    steps: int
    calories: int
    distance_meters: int
    active_minutes: int
    readiness_score: int | None
    hrv: float | None
    sleep_hrv: float | None
    readiness_insight: int | None
    rhr_score: int | None
    rhr_baseline: int | None
    sleep_rhr: int | None
    hrv_score: int | None
    mental_score: int | None
    mental_baseline: int | None
    physical_score: int | None
    physical_baseline: int | None
    afib_baseline: int | None
    ahi_score: int | None
    ahi_baseline: float | None
    min_stress: int | None
    max_stress: int | None
    stress_relax_pct: int | None
    stress_normal_pct: int | None
    stress_medium_pct: int | None
    stress_high_pct: int | None
    daily_pai: float | None
    pai_low_zone_min: int | None
    pai_medium_zone_min: int | None
    pai_high_zone_min: int | None
    spo2_odi: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ===================== Stress =====================

class StressReadingCreate(BaseModel):
    reading_date: date
    recorded_at: datetime
    stress_value: int = Field(..., ge=0, le=100)


class StressReadingResponse(BaseModel):
    id: int
    reading_date: date
    recorded_at: datetime
    stress_value: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ===================== SpO2 =====================

class SpO2ReadingCreate(BaseModel):
    reading_date: date
    recorded_at: datetime
    spo2_value: int = Field(..., ge=0, le=100)
    reading_type: str | None = None


class SpO2ReadingResponse(BaseModel):
    id: int
    reading_date: date
    recorded_at: datetime
    spo2_value: int
    reading_type: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ===================== Workout =====================

class WorkoutRecordCreate(BaseModel):
    track_id: str
    workout_type: int | None = None
    workout_name: str | None = None
    start_time: datetime
    end_time: datetime
    duration_seconds: int = Field(default=0, ge=0)
    distance_meters: int = Field(default=0, ge=0)
    calories: int = Field(default=0, ge=0)
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    min_heart_rate: int | None = None
    avg_pace: float | None = None
    total_steps: int | None = None
    training_effect: float | None = None
    anaerobic_te: float | None = None
    exercise_load: int | None = None
    avg_stride_length: float | None = None
    pause_time: int | None = None


class WorkoutRecordResponse(BaseModel):
    id: int
    track_id: str
    workout_type: int | None
    workout_name: str | None
    start_time: datetime
    end_time: datetime
    duration_seconds: int
    distance_meters: int
    calories: int
    avg_heart_rate: int | None
    max_heart_rate: int | None
    min_heart_rate: int | None
    avg_pace: float | None
    total_steps: int | None
    training_effect: float | None
    anaerobic_te: float | None
    exercise_load: int | None
    avg_stride_length: float | None
    pause_time: int | None
    synced_at: str | None
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


# ===================== Overview =====================

class DailySummaryResponse(BaseModel):
    """Một ngày trong overview data."""
    date: str
    steps: int = 0
    calories: int = 0
    distance_meters: int = 0
    sleep_minutes: int = 0
    deep_sleep_minutes: int = 0
    light_sleep_minutes: int = 0
    rem_sleep_minutes: int = 0
    awake_minutes: int = 0
    sleep_score: int | None = None
    sleep_start: str | None = None
    sleep_end: str | None = None
    sleep_onset_latency: int | None = None
    wake_count: int | None = None
    interruption_score: int | None = None
    sleep_resting_hr: int | None = None
    resting_heart_rate: int | None = None
    max_heart_rate: int | None = None
    avg_stress: float | None = None
    min_stress: int | None = None
    max_stress: int | None = None
    stress_relax_pct: int | None = None
    stress_normal_pct: int | None = None
    stress_medium_pct: int | None = None
    stress_high_pct: int | None = None
    avg_spo2: float | None = None
    spo2_odi: float | None = None
    daily_pai: float | None = None
    pai_low_zone_min: int | None = None
    pai_medium_zone_min: int | None = None
    pai_high_zone_min: int | None = None
    readiness_score: int | None = None
    readiness_insight: int | None = None
    hrv: float | None = None
    sleep_hrv: float | None = None
    hrv_score: int | None = None
    rhr_score: int | None = None
    rhr_baseline: int | None = None
    sleep_rhr: int | None = None
    mental_score: int | None = None
    mental_baseline: int | None = None
    physical_score: int | None = None
    physical_baseline: int | None = None
    afib_baseline: int | None = None
    ahi_score: int | None = None
    ahi_baseline: float | None = None
    workout_avg_hr: int | None = None
    workout_max_hr: int | None = None
    workout_min_hr: int | None = None
    workout_count: int = 0


class OverviewResponse(BaseModel):
    """Response cho /overview endpoint."""
    data: list[DailySummaryResponse]


# ===================== Sync =====================

class SyncTriggerResponse(BaseModel):
    """Response cho POST /sync."""
    status: str | None = None
    counts: dict[str, int] | None = None
    synced_at: str | None = None
    error: str | None = None


class SyncStatusResponse(BaseModel):
    """Response cho GET /sync/status."""
    status: str
    message: str


# ===================== AI Insights =====================

class TrendItem(BaseModel):
    metric: str
    direction: str
    change_pct: float
    current_avg: float
    previous_avg: float
    latest_value: float | None = None


class AnomalyItem(BaseModel):
    metric: str
    date: str
    value: float
    baseline: float
    z_score: float
    severity: str
    message: str


class DailyInsightResponse(BaseModel):
    """Response cho /insights/daily."""
    summary: str
    trends: list[TrendItem] = Field(default_factory=list)
    anomalies: list[AnomalyItem] = Field(default_factory=list)
    generated_at: str
    cached: bool = False


class TrendsOnlyResponse(BaseModel):
    """Response cho /insights/trends."""
    trends: list[TrendItem] = Field(default_factory=list)
    days: int


class AnomaliesOnlyResponse(BaseModel):
    """Response cho /insights/anomalies."""
    anomalies: list[AnomalyItem] = Field(default_factory=list)
    days: int
