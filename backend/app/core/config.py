from functools import lru_cache
from pathlib import Path

from decimal import Decimal
from typing import Literal

from pydantic import Field, SecretStr
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

    # LLM (any OpenAI-compatible chat completions API; defaults target Groq's free tier).
    # "openai_compatible" calls llm_base_url; "fake" is an offline stand-in (no network).
    llm_provider: Literal["openai_compatible", "fake"] = "openai_compatible"
    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-20b"
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=5)  # transport retries (429/5xx/timeouts)
    # Extra attempts when the model's answer is unusable (bad JSON / breaks business rules).
    llm_invalid_response_retries: int = Field(default=1, ge=0, le=3)
    # USD per 1M tokens, for cost logging only. 0 = free tier (Groq free plan costs nothing).
    llm_input_cost_per_million: Decimal = Field(default=Decimal("0"), ge=0)
    llm_output_cost_per_million: Decimal = Field(default=Decimal("0"), ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
