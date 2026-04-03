"""
Anomaly Detector — Phát hiện giá trị bất thường trong health metrics.
Sử dụng Z-score so với baseline cá nhân (rolling average).
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class AnomalyResult:
    """Một anomaly được phát hiện."""
    metric: str
    date: str
    value: float
    baseline: float         # Trung bình baseline
    std_dev: float          # Độ lệch chuẩn baseline
    z_score: float          # Z-score so với baseline
    severity: str           # "info" | "warning" | "critical"
    message: str            # Mô tả bằng tiếng Việt

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "date": self.date,
            "value": round(self.value, 1),
            "baseline": round(self.baseline, 1),
            "z_score": round(self.z_score, 2),
            "severity": self.severity,
            "message": self.message,
        }


# Ngưỡng Z-score cho severity levels
Z_WARNING = 2.0
Z_CRITICAL = 3.0

# Metric labels và hướng cảnh báo
METRIC_CONFIG: dict[str, dict] = {
    "resting_heart_rate": {
        "label": "Nhịp tim nghỉ",
        "unit": "bpm",
        "alert_high": True,     # Cảnh báo khi cao bất thường
        "alert_low": True,      # Cảnh báo khi thấp bất thường
    },
    "avg_stress": {
        "label": "Stress trung bình",
        "unit": "",
        "alert_high": True,
        "alert_low": False,
    },
    "avg_spo2": {
        "label": "SpO2",
        "unit": "%",
        "alert_high": False,
        "alert_low": True,     # Chỉ cảnh báo khi SpO2 thấp
    },
    "sleep_minutes": {
        "label": "Thời gian ngủ",
        "unit": "phút",
        "alert_high": False,
        "alert_low": True,     # Cảnh báo khi ngủ ít
    },
    "sleep_score": {
        "label": "Điểm giấc ngủ",
        "unit": "",
        "alert_high": False,
        "alert_low": True,
    },
    "steps": {
        "label": "Số bước",
        "unit": "bước",
        "alert_high": False,
        "alert_low": True,
    },
    "hrv": {
        "label": "HRV",
        "unit": "ms",
        "alert_high": False,
        "alert_low": True,     # HRV thấp = cần chú ý
    },
    "readiness_score": {
        "label": "Readiness",
        "unit": "",
        "alert_high": False,
        "alert_low": True,
    },
}


def detect_anomalies(daily_data: list[dict], lookback_days: int = 30) -> list[dict]:
    """
    Phát hiện anomalies trong dữ liệu health hàng ngày.
    So sánh giá trị mới nhất với baseline (trung bình lookback_days trước đó).

    Args:
        daily_data: List dicts từ /overview endpoint (sorted by date ascending)
        lookback_days: Số ngày dùng làm baseline (default 30)

    Returns:
        List anomaly results dạng dict
    """
    if len(daily_data) < 7:
        return []

    anomalies: list[dict] = []

    for metric, config in METRIC_CONFIG.items():
        # Lấy tất cả giá trị non-None
        values_with_dates = [
            (d["date"], d.get(metric))
            for d in daily_data
            if d.get(metric) is not None
        ]

        if len(values_with_dates) < 7:
            continue

        all_values = np.array([v for _, v in values_with_dates], dtype=float)

        # Baseline = tất cả trừ ngày cuối cùng (hoặc lookback_days)
        baseline_values = all_values[:-1]
        if len(baseline_values) > lookback_days:
            baseline_values = baseline_values[-lookback_days:]

        mean = float(np.mean(baseline_values))
        std = float(np.std(baseline_values))

        if std == 0:
            continue

        # Check ngày mới nhất
        latest_date, latest_val = values_with_dates[-1]
        latest_val = float(latest_val)
        z = (latest_val - mean) / std

        # Xác định severity
        severity = None
        if config["alert_high"] and z > Z_CRITICAL:
            severity = "critical"
        elif config["alert_high"] and z > Z_WARNING:
            severity = "warning"
        elif config["alert_low"] and z < -Z_CRITICAL:
            severity = "critical"
        elif config["alert_low"] and z < -Z_WARNING:
            severity = "warning"

        if severity:
            direction = "cao" if z > 0 else "thấp"
            message = (
                f"{config['label']} {direction} bất thường: "
                f"{latest_val:.0f}{config['unit']} "
                f"(baseline: {mean:.0f}{config['unit']})"
            )
            anomalies.append(AnomalyResult(
                metric=metric,
                date=latest_date,
                value=latest_val,
                baseline=mean,
                std_dev=std,
                z_score=z,
                severity=severity,
                message=message,
            ).to_dict())

    # Sort: critical trước, rồi warning
    anomalies.sort(key=lambda a: (0 if a["severity"] == "critical" else 1, abs(a["z_score"])))
    return anomalies
