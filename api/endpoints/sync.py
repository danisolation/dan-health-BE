"""
Sync Endpoint — Trigger sync dữ liệu từ Zepp API vào PostgreSQL.
"""
from fastapi import APIRouter, Query

from backend.services.sync import sync_zepp_data, cleanup_old_data
from backend.schemas.health import SyncTriggerResponse, SyncStatusResponse, CronSyncResponse

router = APIRouter(tags=["sync"])


@router.post("/sync", response_model=SyncTriggerResponse)
def trigger_sync(
    days: int = Query(default=1, ge=1, le=90, description="Số ngày lùi lại để sync"),
) -> dict:
    """
    Trigger sync thủ công từ Zepp API.
    - default: sync 1 ngày gần nhất
    - max: 90 ngày
    """
    return sync_zepp_data(days=days)


@router.post("/sync/cron", response_model=CronSyncResponse)
def trigger_cron_sync() -> dict:
    """
    Giống cron job hàng ngày: sync 1 ngày + xóa dữ liệu cũ > 90 ngày.
    """
    sync_result = sync_zepp_data(days=1)
    cleanup_result = cleanup_old_data(keep_days=90)
    return {"sync": sync_result, "cleanup": cleanup_result}


@router.get("/sync/status", response_model=SyncStatusResponse)
def sync_status() -> dict:
    """Kiểm tra trạng thái sync (placeholder cho Phase 2)."""
    return {"status": "ok", "message": "Cron job chạy lúc 00:00 mỗi ngày"}
