from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root .env (shared with docker-compose); a backend/.env overrides it if present.
ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=(ROOT_ENV_FILE, ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "SmartStock AI"
    environment: str = "development"
    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
