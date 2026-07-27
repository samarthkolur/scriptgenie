"""Application settings.

Settings are read from the environment (and a local ``.env`` file during
development). Every value declared here is one the application actually uses;
settings for services that are not yet wired up are added by the stage that
introduces them, so a missing variable always means a real misconfiguration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """Runtime configuration for the ScriptGenie API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Environment = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    #: Origins permitted to call the API from a browser. Comma-separated in the
    #: environment, e.g. ``ALLOWED_ORIGINS=http://localhost:3000,https://app.example``.
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Cached so that configuration is parsed and validated exactly once, and so
    tests can clear the cache to install a different environment.
    """
    return Settings()
