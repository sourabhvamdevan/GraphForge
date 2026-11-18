"""Environment settings."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
SAMPLE_FILE = DATA_DIR / "sample" / "tech_ecosystem.txt"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    database_url: str = "sqlite:///./kg.db"
    allowed_origins: str = "http://localhost:5173"
    max_upload_mb: int = 10
    max_pages: int = 50

    @property
    def llm_enabled(self) -> bool:
        return bool(self.gemini_api_key.strip())

    @property
    def db_path(self) -> str:
        prefix = "sqlite:///"
        url = self.database_url
        return url[len(prefix):] if url.startswith(prefix) else url

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
