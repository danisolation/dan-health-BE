"""
Trend Analyzer — Phân tích xu hướng health metrics.
Sử dụng linear regression + moving averages để xác định trend direction.
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class TrendResult:
    """Kết quả phân tích trend cho 1 metric."""
    metric: str
    direction: str          # "improving" | "declining" | "stable"
    change_pct: float       # % thay đổi so với nửa đầu → nửa sau
    current_avg: float      # Trung bình giai đoạn gần nhất (nửa sau)
    previous_avg: float     # Trung bình giai đoạn trước (nửa đầu)
    latest_value: float | None  # Giá trị mới nhất

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "direction": self.direction,
            "change_pct": round(self.change_pct, 1),
            "current_avg": round(self.current_avg, 1),
            "previous_avg": round(self.previous_avg, 1),
            "latest_value": round(self.latest_value, 1) if self.latest_value is not None else None,
        }


# Ngưỡng thay đổi (%) để xác định trend — tùy metric
# Metrics "higher is better" (steps, sleep, HRV, readiness, SpO2)
# Metrics "lower is better" (stress, resting HR)
HIGHER_IS_BETTER = {"steps", "calories", "sleep_minutes", "deep_sleep_pct", "sleep_score", "hrv", "readiness_score", "avg_spo2", "daily_pai", "mental_score", "physical_score"}
LOWER_IS_BETTER = {"avg_stress", "resting_heart_rate", "wake_count", "sleep_onset_latency"}

# Ngưỡng tối thiểu (%) để coi là có thay đổi rõ ràng
SIGNIFICANCE_THRESHOLD = 5.0


def analyze_trend(metric: str, values: list[float | None]) -> TrendResult | None:
    """
    Phân tích trend cho 1 metric dựa trên chuỗi giá trị thời gian.
    Chia dữ liệu thành nửa trước / nửa sau, so sánh trung bình + linear regression.

    Args:
        metric: Tên metric (e.g. "steps", "avg_stress")
        values: Danh sách giá trị theo thứ tự thời gian (có thể chứa None)

    Returns:
        TrendResult hoặc None nếu không đủ dữ liệu
    """
    # Lọc None values
    clean = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(clean) < 4:
        return None

    indices = np.array([c[0] for c in clean], dtype=float)
    vals = np.array([c[1] for c in clean], dtype=float)

    # Chia nửa trước / nửa sau
    mid = len(vals) // 2
    first_half = vals[:mid]
    second_half = vals[mid:]

    prev_avg = float(np.mean(first_half))
    curr_avg = float(np.mean(second_half))

    # Tính % thay đổi
    if prev_avg == 0:
        change_pct = 0.0
    else:
        change_pct = ((curr_avg - prev_avg) / abs(prev_avg)) * 100

    # Xác định direction dựa trên loại metric
    if abs(change_pct) < SIGNIFICANCE_THRESHOLD:
        direction = "stable"
    elif metric in HIGHER_IS_BETTER:
        direction = "improving" if change_pct > 0 else "declining"
    elif metric in LOWER_IS_BETTER:
        direction = "improving" if change_pct < 0 else "declining"
    else:
        # Default: tăng = improving
        direction = "improving" if change_pct > 0 else ("declining" if change_pct < -SIGNIFICANCE_THRESHOLD else "stable")

    latest_value = float(vals[-1]) if len(vals) > 0 else None

    return TrendResult(
        metric=metric,
        direction=direction,
        change_pct=change_pct,
        current_avg=curr_avg,
        previous_avg=prev_avg,
        latest_value=latest_value,
    )


def analyze_all_trends(daily_data: list[dict]) -> list[dict]:
    """
    Phân tích trends cho tất cả metrics chính từ daily summary data.

    Args:
        daily_data: List dicts từ /overview endpoint (sorted by date ascending)

    Returns:
        List trend results dạng dict
    """
    if not daily_data:
        return []

    # Các metrics cần phân tích
    metrics = [
        "steps", "calories", "sleep_minutes", "sleep_score",
        "resting_heart_rate", "avg_stress", "avg_spo2",
        "hrv", "readiness_score", "daily_pai",
        "mental_score", "physical_score",
    ]

    results = []
    for metric in metrics:
        values = [d.get(metric) for d in daily_data]
        trend = analyze_trend(metric, values)
        if trend:
            results.append(trend.to_dict())

    return results
