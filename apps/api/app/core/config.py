"""Application settings.

Settings are read from the environment (and a local ``.env`` file during
development). Every value declared here is one the application actually uses;
settings for services that are not yet wired up are added by the stage that
introduces them, so a missing variable always means a real misconfiguration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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

    # ------------------------------------------------------------------ Groq
    #
    # ``SecretStr`` so the key cannot be printed by accident: repr, str, log
    # formatting and pydantic serialisation all render it as ``**********``.
    # Reading it requires calling ``get_secret_value()``, which is greppable
    # and appears exactly once, in the client's auth header.
    groq_api_key: SecretStr | None = None

    #: Verified against Groq's model documentation. ``openai/gpt-oss-120b`` is
    #: the production-tier model that supports strict JSON-schema constrained
    #: decoding, which the Llama models do not; on the free tier both carry the
    #: same limits, so the schema guarantee is free.
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    #: Per-attempt timeout. A slow call is retried rather than waited out.
    groq_timeout_seconds: float = Field(default=30.0, gt=0)
    #: Attempts after the first. Capped so a 5xx storm cannot retry forever.
    groq_max_retries: int = Field(default=3, ge=0, le=10)
    #: Ceiling on one logical request including every retry and backoff.
    groq_deadline_seconds: float = Field(default=60.0, gt=0)
    #: Consecutive failures before the breaker opens.
    groq_breaker_threshold: int = Field(default=5, ge=1)
    #: How long the breaker stays open before allowing a trial request.
    groq_breaker_cooldown_seconds: float = Field(default=30.0, gt=0)

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
