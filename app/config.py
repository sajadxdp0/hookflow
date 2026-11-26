"""HookFlow configuration — environment-driven, no secrets in code."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "hookflow"
    environment: Literal["development", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("HOOKFLOW_ENVIRONMENT", "ENVIRONMENT"),
    )
    # SQLite by default for local dev/tests; PostgreSQL is required in production.
    database_url: str = Field(
        default="sqlite:///./hookflow.db",
        validation_alias=AliasChoices("DATABASE_URL", "HOOKFLOW_DATABASE_URL"),
    )
    # Optional in development. Production readiness requires Redis so quotas
    # and delivery rate limits are shared across replicas.
    redis_url: str = Field(
        default="",
        validation_alias=AliasChoices("REDIS_URL", "HOOKFLOW_REDIS_URL"),
    )
    max_body_bytes: int = 256 * 1024
    delivery_timeout_seconds: float = 10.0
    max_attempts: int = 5
    backoff_schedule_seconds: list[int] = Field(
        default_factory=lambda: [60, 300, 1800, 7200, 43200]
    )
    default_rate_limit_per_minute: int = 60
    ingest_rate_limit_per_minute: int = 600
    max_endpoints_per_tenant: int = 100
    # Symmetric key protecting webhook secrets at rest. Empty uses a published
    # development key and is rejected by /ready in production.
    secret_encryption_key: str = Field(
        default="",
        validation_alias=AliasChoices("SECRET_ENCRYPTION_KEY", "HOOKFLOW_SECRET_ENCRYPTION_KEY"),
    )
    # Must exceed the connect, write and response-header read phases of one
    # HTTP attempt. Each queued row renews its lease immediately before POSTing,
    # so serial batch processing cannot expire it.
    claim_lease_seconds: float = 60.0

    # Empty disables admin routes with 503. Production readiness requires a
    # high-entropy token; HOOKFLOW_ADMIN_TOKEN is accepted as an alias.
    admin_token: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_TOKEN", "HOOKFLOW_ADMIN_TOKEN"),
    )

    @field_validator("backoff_schedule_seconds")
    @classmethod
    def valid_backoff_schedule(cls, value: list[int]) -> list[int]:
        if not value or any(delay < 0 for delay in value):
            raise ValueError("backoff schedule must contain non-negative delays")
        if any(later < earlier for earlier, later in zip(value, value[1:], strict=False)):
            raise ValueError("backoff schedule must be monotonic")
        return value

    @model_validator(mode="after")
    def valid_operating_bounds(self) -> Settings:
        if self.max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        if self.delivery_timeout_seconds <= 0:
            raise ValueError("delivery_timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.default_rate_limit_per_minute < 1:
            raise ValueError("default_rate_limit_per_minute must be positive")
        if self.ingest_rate_limit_per_minute < 1:
            raise ValueError("ingest_rate_limit_per_minute must be positive")
        if self.max_endpoints_per_tenant < 1:
            raise ValueError("max_endpoints_per_tenant must be positive")
        if self.claim_lease_seconds <= self.delivery_timeout_seconds * 3:
            raise ValueError(
                "claim_lease_seconds must exceed three delivery timeout phases"
            )
        if self.environment == "production":
            if not self.database_url.startswith(("postgresql", "postgresql+psycopg")):
                raise ValueError("production requires PostgreSQL")
            if not self.redis_url:
                raise ValueError("production requires REDIS_URL")
            if not self.secret_encryption_key:
                raise ValueError("production requires SECRET_ENCRYPTION_KEY")
            if len(self.admin_token) < 32:
                raise ValueError("production requires a 32-character admin token")
        return self


@lru_cache
def _from_environment() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Forget the settings read from the environment."""
    _from_environment.cache_clear()


_settings_override: Settings | None = None


def set_settings(settings: Settings) -> None:
    """Pin the settings the whole process should use."""
    global _settings_override
    _settings_override = settings
    _from_environment.cache_clear()


def clear_settings_override() -> None:
    global _settings_override
    _settings_override = None
    _from_environment.cache_clear()


def get_settings() -> Settings:
    if _settings_override is not None:
        return _settings_override
    return _from_environment()
