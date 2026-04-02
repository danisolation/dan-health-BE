"""
Config module — Quản lý toàn bộ cấu hình ứng dụng qua biến môi trường.
Sử dụng Pydantic Settings để validate và type-check config values.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Thư mục gốc của project (d:\tracking)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """
    Cấu hình Backend được load từ file .env.
    Tất cả secrets (password, connection string) KHÔNG được hard-code.
    """
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",  # Bỏ qua các biến không liên quan (ZEPP_*)
    )

    # --- Aiven PostgreSQL ---
    aiven_pg_host: str = "localhost"
    aiven_pg_port: int = 5432
    aiven_pg_user: str = "avnadmin"
    aiven_pg_password: str = ""
    aiven_pg_database: str = "defaultdb"
    aiven_pg_ssl_ca_path: str = ""  # Đường dẫn tới CA cert (ca.pem)

    # --- Zepp API (shared với app/) ---
    zepp_app_token: str = ""
    zepp_user_id: str = ""

    # --- Server ---
    backend_host: str = "0.0.0.0"
    backend_port: int = 8001
    backend_debug: bool = False

    @property
    def database_url(self) -> str:
        """
        Tạo connection string cho SQLAlchemy.
        Format: postgresql+psycopg2://user:pass@host:port/dbname
        """
        return (
            f"postgresql+psycopg2://{self.aiven_pg_user}:{self.aiven_pg_password}"
            f"@{self.aiven_pg_host}:{self.aiven_pg_port}/{self.aiven_pg_database}"
        )

    @property
    def ssl_ca_full_path(self) -> Path | None:
        """Trả về absolute path tới CA cert nếu được cấu hình."""
        if self.aiven_pg_ssl_ca_path:
            ca_path = Path(self.aiven_pg_ssl_ca_path)
            if not ca_path.is_absolute():
                ca_path = BASE_DIR / ca_path
            return ca_path
        return None


# Singleton instance — import trực tiếp: from backend.core.config import settings
settings = Settings()
