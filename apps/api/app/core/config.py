"""Typed application settings — single config class for compose and hybrid modes (D-09).

Env vars injected by compose take precedence over the repo-root .env file
(pydantic-settings default source ordering: init kwargs > env vars > env_file).
"""

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../../.env",  # repo-root .env when run from apps/api (hybrid host mode)
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str  # env DATABASE_URL
    redis_url: str  # env REDIS_URL
    jwt_secret: str  # env JWT_SECRET
    # env TARGET_CREDENTIAL_KEY, comma-separated (MultiFernet rotation: first key
    # encrypts, all keys decrypt). NoDecode disables JSON parsing so the
    # before-validator below owns the comma-split.
    credential_keys: Annotated[list[str], NoDecode] = Field(
        validation_alias="TARGET_CREDENTIAL_KEY"
    )
    admin_email: str  # env ADMIN_EMAIL
    admin_password: str  # env ADMIN_PASSWORD
    cookie_secure: bool = False  # env COOKIE_SECURE

    # --- LLM gateway (Phase 2, plan 02-01) ---
    # Provider-prefixed default model passed straight to init_chat_model
    # (e.g. "anthropic:claude-..." / "openai:gpt-..."), D-13.
    llm_default_model: str  # env LLM_DEFAULT_MODEL
    # Provider keys default None so the app boots without them; live tests skip
    # when absent (RESEARCH Pitfall 6). Never logged, never stored in the ledger.
    anthropic_api_key: str | None = None  # env ANTHROPIC_API_KEY
    openai_api_key: str | None = None  # env OPENAI_API_KEY
    # Optional LangSmith tracing — env-gated, OFF by default (RESEARCH Q3).
    langsmith_tracing: bool = False  # env LANGSMITH_TRACING
    langsmith_api_key: str | None = None  # env LANGSMITH_API_KEY

    @field_validator("credential_keys", mode="before")
    @classmethod
    def _split_credential_keys(cls, value: object) -> object:
        if isinstance(value, str):
            return [key.strip() for key in value.split(",") if key.strip()]
        return value


settings = Settings()  # module-level singleton: `from app.core.config import settings`
