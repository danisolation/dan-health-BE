"""
API Router — Tập trung tất cả endpoint routers.
"""
from fastapi import APIRouter
from backend.api.endpoints import sync, health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(sync.router)
api_router.include_router(health.router)
