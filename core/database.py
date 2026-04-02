"""
Database module — Kết nối SQLAlchemy tới Aiven PostgreSQL.
Hỗ trợ SSL/TLS bắt buộc khi kết nối tới Aiven Cloud.
"""
import ssl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from backend.core.config import settings


def _build_connect_args() -> dict:
    """
    Tạo connect_args cho psycopg2 với SSL context.
    Aiven yêu cầu kết nối SSL; nếu có CA cert thì verify server,
    nếu không thì vẫn dùng SSL nhưng không verify (dev mode).
    """
    ca_path = settings.ssl_ca_full_path

    if ca_path and ca_path.exists():
        # Production: verify server certificate bằng CA cert từ Aiven
        ssl_ctx = ssl.create_default_context(cafile=str(ca_path))
        return {"sslmode": "verify-ca", "ssl_context": ssl_ctx}

    # Dev/fallback: SSL required nhưng không verify certificate
    return {"sslmode": "require"}


# Engine — connection pool tới PostgreSQL
engine = create_engine(
    settings.database_url,
    connect_args=_build_connect_args(),
    pool_size=5,           # Số connection giữ sẵn
    max_overflow=10,       # Thêm tối đa 10 connection khi load cao
    pool_pre_ping=True,    # Kiểm tra connection sống trước khi dùng
    echo=settings.backend_debug,  # Log SQL khi debug=True
)

# Session factory — mỗi request sẽ nhận 1 session riêng
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Base class cho tất cả SQLAlchemy models."""
    pass


def init_db() -> None:
    """
    Tạo tất cả tables từ models.
    Import models trước khi gọi để metadata được register.
    """
    import backend.models.health  # noqa: F401 — đảm bảo models được load
    Base.metadata.create_all(bind=engine)
