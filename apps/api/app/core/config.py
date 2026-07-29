"""Application settings.

Settings are read from the environment (and a local ``.env`` file during
development). Every value declared here is one the application actually uses;
settings for services that are not yet wired up are added by the stage that
introduces them, so a missing variable always means a real misconfiguration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
    #:
    #: ``NoDecode`` is load-bearing. Without it, pydantic-settings treats any
    #: list-typed field as JSON and parses the raw value *before* validators
    #: run, so a comma-separated value raises `SettingsError` at import time and
    #: the validator below never sees it. The failure only appears where a
    #: ``.env`` file exists, which is every developer machine and no CI runner.
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

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

    # -------------------------------------------------------------- Supabase
    #
    # The API talks to Supabase two ways and the distinction is a security
    # boundary, not a convenience. Everything a user owns is read and written
    # through PostgREST **with that user's own access token**, so row level
    # security is enforced by the database on every statement and a repository
    # that forgets its filter returns nothing rather than someone else's rows.
    # The service role key bypasses RLS entirely and is used only where no user
    # may be trusted to write: usage accounting.
    supabase_url: str = ""
    supabase_anon_key: SecretStr | None = None
    supabase_service_role_key: SecretStr | None = None

    #: Set only for projects still on Supabase's legacy symmetric signing keys.
    #: When present, tokens are verified with HS256 against this secret; when
    #: absent, they are verified against the project's published JWKS. The two
    #: are never both accepted for one token — see ``app.core.security``.
    supabase_jwt_secret: SecretStr | None = None

    #: How long a fetched JWKS is trusted before it is re-fetched.
    supabase_jwks_cache_seconds: float = Field(default=600.0, gt=0)
    #: Floor on the interval between JWKS fetches triggered by an unknown key
    #: id. Without it, tokens carrying random ``kid`` values would turn every
    #: request into an outbound fetch, which is a denial of service with extra
    #: steps.
    supabase_jwks_min_refresh_seconds: float = Field(default=30.0, gt=0)
    #: Timeout for Supabase HTTP calls, both JWKS and PostgREST.
    supabase_timeout_seconds: float = Field(default=10.0, gt=0)

    @property
    def auth_issuer(self) -> str:
        """The ``iss`` every Supabase access token for this project carries."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        """Where this project publishes its asymmetric verification keys."""
        return f"{self.auth_issuer}/.well-known/jwks.json"

    @property
    def postgrest_url(self) -> str:
        """The PostgREST base for this project's ``public`` schema."""
        return f"{self.supabase_url.rstrip('/')}/rest/v1"

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
