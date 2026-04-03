"""
Upload Endpoint — Nhận dữ liệu health từ Amazfit Bip 6.
Hỗ trợ JSON body hoặc file upload (CSV/JSON).
"""
import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.api.deps import get_db
from backend.models.health import HeartRate, SleepRecord, ActivityRecord
from backend.schemas.health import (
    AmazfitUploadData,
    HeartRateCreate,
    SleepRecordCreate,
    ActivityRecordCreate,
    UploadResponse,
)

router = APIRouter(tags=["upload"])

# Giới hạn kích thước file upload (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post("/upload-amazfit-data", response_model=UploadResponse)
def upload_amazfit_json(
    data: AmazfitUploadData,
    db: Session = Depends(get_db),
) -> UploadResponse:
    """
    Upload dữ liệu Amazfit dạng JSON body.

    Body structure:
    ```json
    {
        "heart_rates": [{"recorded_at": "...", "bpm": 72}],
        "sleep_records": [{"sleep_date": "2026-04-01", "total_minutes": 420, ...}],
        "activity_records": [{"activity_date": "2026-04-01", "steps": 8500, ...}]
    }
    ```
    """
    counts = _insert_health_data(db, data)
    return UploadResponse(status="success", inserted=counts)


@router.post("/upload-amazfit-file", response_model=UploadResponse)
async def upload_amazfit_file(
    file: UploadFile = File(..., description="File CSV hoặc JSON từ Amazfit"),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """
    Upload file CSV hoặc JSON chứa dữ liệu Amazfit.
    - **JSON**: cùng format với /upload-amazfit-data
    - **CSV**: cần header row, tự detect loại data dựa trên columns
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="Tên file không hợp lệ")

    filename_lower = file.filename.lower()
    if not filename_lower.endswith((".csv", ".json")):
        raise HTTPException(
            status_code=400,
            detail="Chỉ hỗ trợ file .csv hoặc .json",
        )

    # Validate content type
    allowed_types = {
        "application/json", "text/csv", "text/plain",
        "application/csv", "application/octet-stream",
    }
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Content-Type không hợp lệ: {file.content_type}",
        )

    # Đọc nội dung file với giới hạn kích thước
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File vượt quá 10MB")

    try:
        if filename_lower.endswith(".json"):
            data = _parse_json_file(content)
        else:
            data = _parse_csv_file(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    counts = _insert_health_data(db, data)
    return UploadResponse(status="success", inserted=counts)


def _insert_health_data(db: Session, data: AmazfitUploadData) -> dict[str, int]:
    """
    Insert dữ liệu health vào database.
    Sử dụng upsert (ON CONFLICT) để tránh duplicate.
    """
    counts: dict[str, int] = {"heart_rates": 0, "sleep_records": 0, "activity_records": 0}

    # --- Heart Rate: insert tất cả records ---
    for hr in data.heart_rates:
        db_record = HeartRate(
            recorded_at=hr.recorded_at,
            bpm=hr.bpm,
            measurement_type=hr.measurement_type,
        )
        db.add(db_record)
        counts["heart_rates"] += 1

    # --- Sleep: upsert theo sleep_date (1 record/ngày) ---
    for sleep in data.sleep_records:
        stmt = pg_insert(SleepRecord).values(
            sleep_date=sleep.sleep_date,
            total_minutes=sleep.total_minutes,
            deep_sleep_minutes=sleep.deep_sleep_minutes,
            light_sleep_minutes=sleep.light_sleep_minutes,
            rem_sleep_minutes=sleep.rem_sleep_minutes,
            awake_minutes=sleep.awake_minutes,
            sleep_score=sleep.sleep_score,
        ).on_conflict_do_update(
            index_elements=["sleep_date"],
            set_={
                "total_minutes": sleep.total_minutes,
                "deep_sleep_minutes": sleep.deep_sleep_minutes,
                "light_sleep_minutes": sleep.light_sleep_minutes,
                "rem_sleep_minutes": sleep.rem_sleep_minutes,
                "awake_minutes": sleep.awake_minutes,
                "sleep_score": sleep.sleep_score,
            },
        )
        db.execute(stmt)
        counts["sleep_records"] += 1

    # --- Activity: upsert theo activity_date (1 record/ngày) ---
    for activity in data.activity_records:
        stmt = pg_insert(ActivityRecord).values(
            activity_date=activity.activity_date,
            steps=activity.steps,
            calories=activity.calories,
            distance_meters=activity.distance_meters,
            active_minutes=activity.active_minutes,
        ).on_conflict_do_update(
            index_elements=["activity_date"],
            set_={
                "steps": activity.steps,
                "calories": activity.calories,
                "distance_meters": activity.distance_meters,
                "active_minutes": activity.active_minutes,
            },
        )
        db.execute(stmt)
        counts["activity_records"] += 1

    db.commit()
    return counts


def _parse_json_file(content: bytes) -> AmazfitUploadData:
    """Parse file JSON thành AmazfitUploadData."""
    try:
        raw = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"File JSON không hợp lệ: {e}")
    return AmazfitUploadData.model_validate(raw)


def _parse_csv_file(content: bytes) -> AmazfitUploadData:
    """
    Parse file CSV thành AmazfitUploadData.
    Tự nhận diện loại data dựa trên header columns:
    - Có "bpm" → heart_rate
    - Có "deep_sleep_minutes" → sleep_record
    - Có "steps" → activity_record
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = set(reader.fieldnames or [])

    heart_rates: list[HeartRateCreate] = []
    sleep_records: list[SleepRecordCreate] = []
    activity_records: list[ActivityRecordCreate] = []

    if "bpm" in fieldnames:
        for row in reader:
            heart_rates.append(HeartRateCreate(
                recorded_at=datetime.fromisoformat(row["recorded_at"]),
                bpm=int(row["bpm"]),
                measurement_type=row.get("measurement_type", "auto"),
            ))
    elif "deep_sleep_minutes" in fieldnames:
        for row in reader:
            sleep_records.append(SleepRecordCreate(
                sleep_date=row["sleep_date"],
                total_minutes=int(row.get("total_minutes", 0)),
                deep_sleep_minutes=int(row.get("deep_sleep_minutes", 0)),
                light_sleep_minutes=int(row.get("light_sleep_minutes", 0)),
                rem_sleep_minutes=int(row.get("rem_sleep_minutes", 0)),
                awake_minutes=int(row.get("awake_minutes", 0)),
                sleep_score=int(row["sleep_score"]) if row.get("sleep_score") else None,
            ))
    elif "steps" in fieldnames:
        for row in reader:
            activity_records.append(ActivityRecordCreate(
                activity_date=row["activity_date"],
                steps=int(row.get("steps", 0)),
                calories=int(row.get("calories", 0)),
                distance_meters=int(row.get("distance_meters", 0)),
                active_minutes=int(row.get("active_minutes", 0)),
            ))
    else:
        raise ValueError(
            f"Không nhận diện được loại data từ CSV headers: {fieldnames}. "
            "Cần có column 'bpm', 'deep_sleep_minutes', hoặc 'steps'."
        )

    return AmazfitUploadData(
        heart_rates=heart_rates,
        sleep_records=sleep_records,
        activity_records=activity_records,
    )
