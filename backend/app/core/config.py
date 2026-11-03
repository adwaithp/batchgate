"""Application settings, read from the environment and backend/.env."""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """All settings; environment variables use the BATCHGATE_ prefix."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="BATCHGATE_", extra="ignore")

    app_name: str = "BatchGate"
    # Database: either the separate parts or one full URL.
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "batchgate"
    db_user: str = "batchgate"
    db_password: str = ""
    database_url: str | None = None
    # Schema other than public (tests and evals use their own).
    db_schema: str | None = None
    check_schema_on_start: bool = True

    secret_key: str = "dev-only-secret-change-me-in-production-0123456789"
    access_token_expire_minutes: int = 60 * 12
    jwt_algorithm: str = "HS256"
    bcrypt_rounds: int = 12

    # Show one-click demo accounts on the login page.
    demo_mode: bool = True
    demo_password: str = "demo1234"

    cors_origins: list[str] = ["http://localhost:5173"]

    # Claude models (the API key comes from ANTHROPIC_API_KEY).
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "BATCHGATE_ANTHROPIC_API_KEY"),
    )
    extraction_model: str = "claude-sonnet-5-5"
    copilot_model: str = "claude-sonnet-5-5"
    # COA reading: queue (worker + Redis), inline (in the request) or auto.
    extraction_mode: Literal["auto", "queue", "inline"] = "auto"
    mcp_user: str = "arjun@batchgate.dev"  # BatchGate user the MCP server acts as

    # Redis for the worker queue and reading progress.
    redis_url: str = "redis://localhost:6379"

    upload_dir: str = "./uploads"
    max_upload_mb: int = 15

    # Release policy (see app/services/rules/engine.py).
    require_lab_coa: bool = True
    default_tolerance_pct: float = 2.0
    low_confidence_threshold: float = 0.8

    @property
    def sqlalchemy_url(self) -> URL | str:
        """Return the database URL, built from parts unless given."""
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password or None,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings."""
    return Settings()
