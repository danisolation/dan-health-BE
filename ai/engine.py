"""
AI Engine — Orchestrator tổng hợp dữ liệu + chạy analyzers + gọi LLM.
Cache insight results để tránh gọi LLM lại liên tục.
"""
import logging
import time
from datetime import date, timedelta

import google.generativeai as genai
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.ai.analyzers.anomaly import detect_anomalies
from backend.ai.analyzers.trends import analyze_all_trends
from backend.ai.prompts import SYSTEM_PROMPT, DAILY_INSIGHT_PROMPT
from backend.core.config import settings
from backend.models.health import (
    ActivityRecord, HeartRate, SleepRecord,
    SpO2Reading, StressReading,
)

logger = logging.getLogger(__name__)

# Simple in-memory cache: key → (timestamp, result)
_insight_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 3600  # 1 giờ


def _get_cached(key: str) -> dict | None:
    """Lấy kết quả từ cache nếu chưa hết hạn."""
    if key in _insight_cache:
        ts, result = _insight_cache[key]
        if time.time() - ts < CACHE_TTL:
            return result
        del _insight_cache[key]
    return None


def _set_cache(key: str, result: dict) -> None:
    """Lưu kết quả vào cache."""
    _insight_cache[key] = (time.time(), result)


def get_daily_data(db: Session, days: int = 30) -> list[dict]:
    """
    Lấy dữ liệu tổng hợp theo ngày từ DB — tương tự /overview endpoint.
    Trả về list dicts sorted by date ascending.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

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

    # Heart rate resting/max per day
    hr_records = (
        db.query(
            func.date(HeartRate.recorded_at).label("date"),
            HeartRate.measurement_type,
            HeartRate.bpm,
        )
        .filter(func.date(HeartRate.recorded_at).between(start_date, end_date))
        .all()
    )
    hr_by_date: dict[str, dict] = {}
    for row in hr_records:
        d = str(row.date)
        if d not in hr_by_date:
            hr_by_date[d] = {"resting": None, "max": None}
        if row.measurement_type == "resting":
            hr_by_date[d]["resting"] = row.bpm
        elif row.measurement_type == "max":
            hr_by_date[d]["max"] = row.bpm

    # Stress avg per day
    stress_avg = dict(
        db.query(
            StressReading.reading_date,
            func.round(func.avg(StressReading.stress_value)).label("avg"),
        )
        .filter(StressReading.reading_date.between(start_date, end_date))
        .group_by(StressReading.reading_date)
        .all()
    )

    # SpO2 avg per day
    spo2_avg = dict(
        db.query(
            SpO2Reading.reading_date,
            func.round(func.avg(SpO2Reading.spo2_value)).label("avg"),
        )
        .filter(SpO2Reading.reading_date.between(start_date, end_date))
        .group_by(SpO2Reading.reading_date)
        .all()
    )

    # Build daily dicts
    activity_map = {str(a.activity_date): a for a in activities}
    sleep_map = {str(s.sleep_date): s for s in sleeps}
    all_dates = set(activity_map.keys()) | set(sleep_map.keys()) | set(hr_by_date.keys())

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
            "sleep_minutes": slp.total_minutes if slp else None,
            "deep_sleep_minutes": slp.deep_sleep_minutes if slp else None,
            "light_sleep_minutes": slp.light_sleep_minutes if slp else None,
            "rem_sleep_minutes": slp.rem_sleep_minutes if slp else None,
            "sleep_score": slp.sleep_score if slp else None,
            "wake_count": slp.wake_count if slp else None,
            "resting_heart_rate": hr.get("resting"),
            "max_heart_rate": hr.get("max"),
            "avg_stress": stress_avg.get(date.fromisoformat(d)),
            "avg_spo2": spo2_avg.get(date.fromisoformat(d)),
            "hrv": act.hrv if act else None,
            "sleep_hrv": act.sleep_hrv if act else None,
            "readiness_score": act.readiness_score if act else None,
            "daily_pai": act.daily_pai if act else None,
            "mental_score": act.mental_score if act else None,
            "physical_score": act.physical_score if act else None,
            "min_stress": act.min_stress if act else None,
            "max_stress": act.max_stress if act else None,
            "stress_relax_pct": act.stress_relax_pct if act else None,
            "stress_high_pct": act.stress_high_pct if act else None,
        })

    return daily_data


def generate_daily_insight(db: Session, days: int = 30) -> dict:
    """
    Tạo AI insight tổng hợp cho ngày mới nhất.
    Sử dụng cache TTL 1 giờ.

    Returns:
        {
            "summary": "AI generated text...",
            "trends": [...],
            "anomalies": [...],
            "generated_at": "2024-01-01T12:00:00",
            "cached": bool
        }
    """
    cache_key = f"daily_insight_{date.today().isoformat()}_{days}"
    cached = _get_cached(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    # Thu thập dữ liệu
    daily_data = get_daily_data(db, days)

    if not daily_data:
        return {
            "summary": "Chưa có dữ liệu để phân tích. Hãy sync dữ liệu từ đồng hồ trước.",
            "trends": [],
            "anomalies": [],
            "generated_at": _now_iso(),
            "cached": False,
        }

    # Chạy analyzers
    trends = analyze_all_trends(daily_data)
    anomalies = detect_anomalies(daily_data, lookback_days=days)

    # Format dữ liệu mới nhất cho LLM
    latest = daily_data[-1]
    latest_str = _format_latest_data(latest)
    trends_str = _format_trends(trends)
    anomalies_str = _format_anomalies(anomalies)

    # Gọi LLM
    summary = _call_llm(
        DAILY_INSIGHT_PROMPT.format(
            date=latest["date"],
            latest_data=latest_str,
            trends=trends_str,
            anomalies=anomalies_str,
            days=days,
        )
    )

    result = {
        "summary": summary,
        "trends": trends,
        "anomalies": anomalies,
        "generated_at": _now_iso(),
        "cached": False,
    }

    _set_cache(cache_key, result)
    return result


def get_trends_only(db: Session, days: int = 30) -> dict:
    """Chỉ trả về trend analysis (không gọi LLM)."""
    daily_data = get_daily_data(db, days)
    trends = analyze_all_trends(daily_data)
    return {"trends": trends, "days": days}


def get_anomalies_only(db: Session, days: int = 30) -> dict:
    """Chỉ trả về anomaly detection (không gọi LLM)."""
    daily_data = get_daily_data(db, days)
    anomalies = detect_anomalies(daily_data, lookback_days=days)
    return {"anomalies": anomalies, "days": days}


def _call_llm(user_prompt: str) -> str:
    """
    Gọi Google Gemini API để generate insight text.
    Fallback sang summary text nếu API key chưa cấu hình.
    Retry tối đa 2 lần nếu bị rate limit.
    """
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY chưa cấu hình — trả về fallback summary")
        return "⚠️ AI insights chưa được kích hoạt. Vui lòng cấu hình GEMINI_API_KEY trong .env để sử dụng tính năng phân tích AI."

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.ai_model,
        system_instruction=SYSTEM_PROMPT,
    )

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=500,
                    temperature=0.7,
                ),
            )
            return response.text or ""
        except Exception as e:
            err_name = type(e).__name__
            if "ResourceExhausted" in err_name or "429" in str(e):
                if attempt < max_retries:
                    wait = 2 ** (attempt + 1)  # 2s, 4s
                    logger.warning(f"Gemini rate limited, retry {attempt + 1}/{max_retries} sau {wait}s")
                    import time as _time
                    _time.sleep(wait)
                    continue
                logger.error(f"Gemini rate limit sau {max_retries} retries: {e}")
                return "⚠️ API Gemini đang quá tải. Vui lòng thử lại sau vài phút."
            logger.error(f"LLM call failed: {e}")
            return f"⚠️ Không thể tạo AI insight: {err_name}"
    return "⚠️ Không thể tạo AI insight sau nhiều lần thử."


def _format_latest_data(latest: dict) -> str:
    """Format dữ liệu mới nhất thành text dễ đọc cho LLM."""
    lines = []
    field_labels = {
        "steps": ("Bước chân", ""),
        "calories": ("Calories", " kcal"),
        "sleep_minutes": ("Thời gian ngủ", " phút"),
        "sleep_score": ("Điểm ngủ", "/100"),
        "resting_heart_rate": ("Nhịp tim nghỉ", " bpm"),
        "max_heart_rate": ("Nhịp tim max", " bpm"),
        "avg_stress": ("Stress TB", "/100"),
        "avg_spo2": ("SpO2", "%"),
        "hrv": ("HRV", " ms"),
        "readiness_score": ("Readiness", "/100"),
        "daily_pai": ("PAI", ""),
        "mental_score": ("Mental", "/100"),
        "physical_score": ("Physical", "/100"),
    }

    for key, (label, unit) in field_labels.items():
        val = latest.get(key)
        if val is not None:
            lines.append(f"- {label}: {val}{unit}")

    return "\n".join(lines) if lines else "Không có dữ liệu"


def _format_trends(trends: list[dict]) -> str:
    """Format trend results thành text cho LLM."""
    if not trends:
        return "Chưa đủ dữ liệu để phân tích xu hướng."

    direction_map = {"improving": "↑ Cải thiện", "declining": "↓ Giảm", "stable": "→ Ổn định"}
    lines = []
    for t in trends:
        d = direction_map.get(t["direction"], t["direction"])
        lines.append(f"- {t['metric']}: {d} ({t['change_pct']:+.1f}%)")
    return "\n".join(lines)


def _format_anomalies(anomalies: list[dict]) -> str:
    """Format anomalies thành text cho LLM."""
    if not anomalies:
        return "Không phát hiện bất thường."
    return "\n".join(f"- [{a['severity'].upper()}] {a['message']}" for a in anomalies)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
