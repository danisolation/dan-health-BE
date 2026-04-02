"""
Dependency Injection module.
Cung cấp database session cho các endpoint thông qua FastAPI Depends.
"""
from collections.abc import Generator
from sqlalchemy.orm import Session
from backend.core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Yield một database session và tự động đóng sau khi request hoàn tất.
    Sử dụng: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
