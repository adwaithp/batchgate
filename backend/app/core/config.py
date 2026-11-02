from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BATCHGATE_", extra="ignore")

    app_name: str = "BatchGate"
    database_url: str = "sqlite:///./batchgate.db"

    # Auth
    secret_key: str = "dev-only-secret-change-me-in-production-0123456789"
    access_token_expire_minutes: int = 60 * 12
    jwt_algorithm: str = "HS256"
    bcrypt_rounds: int = 12

    # Demo mode exposes one-click demo accounts on the login page.
    demo_mode: bool = True
    demo_password: str = "demo1234"

    cors_origins: list[str] = ["http://localhost:5173"]

    # LLM: the standard ANTHROPIC_API_KEY works, from the shell or from backend/.env
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "BATCHGATE_ANTHROPIC_API_KEY"),
    )
    extraction_model: str = "claude-sonnet-5-5"

    # The arq worker reads COAs in the background; progress reaches the browser via Redis.
    redis_url: str = "redis://localhost:6379"

    upload_dir: str = "./uploads"
    max_upload_mb: int = 15

    # Release policy (see app/services/rules/engine.py)
    require_lab_coa: bool = True
    default_tolerance_pct: float = 2.0
    low_confidence_threshold: float = 0.8


@lru_cache
def get_settings() -> Settings:
    return Settings()
