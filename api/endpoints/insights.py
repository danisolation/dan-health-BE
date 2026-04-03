"""
AI Insights Endpoint — API endpoints cho AI health analysis.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.ai.engine import (
    generate_daily_insight,
    get_anomalies_only,
    get_trends_only,
)
from backend.api.deps import get_db
from backend.schemas.health import (
    DailyInsightResponse,
    TrendsOnlyResponse,
    AnomaliesOnlyResponse,
)

router = APIRouter(prefix="/insights", tags=["ai-insights"])


@router.get("/daily", response_model=DailyInsightResponse)
def get_daily_insight(
    days: int = Query(default=30, ge=7, le=90, description="Số ngày để phân tích"),
    db: Session = Depends(get_db),
) -> dict:
    """
    AI insight tổng hợp cho ngày mới nhất.
    Bao gồm: summary text (LLM), trends, anomalies.
    Cached 1 giờ.
    """
    return generate_daily_insight(db, days)


@router.get("/trends", response_model=TrendsOnlyResponse)
def get_trends(
    days: int = Query(default=30, ge=7, le=90, description="Số ngày để phân tích"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Trend analysis cho tất cả metrics chính.
    Không gọi LLM — chỉ statistical analysis.
    """
    return get_trends_only(db, days)


@router.get("/anomalies", response_model=AnomaliesOnlyResponse)
def get_anomalies(
    days: int = Query(default=30, ge=7, le=90, description="Số ngày baseline"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Anomaly detection — phát hiện giá trị bất thường.
    Không gọi LLM — chỉ Z-score analysis.
    """
    return get_anomalies_only(db, days)
