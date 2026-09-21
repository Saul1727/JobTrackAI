"""
Centralized application configuration, read from environment variables
(loaded from a local .env file when present). Secrets are never
hardcoded in source: an .env file is git-ignored, and production values
are provided by the hosting platform's environment.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

# Exposed separately so main.py can compare against it (to warn if a
# deployment is still using the example secret) without duplicating the
# literal string in two places.
CLAVE_SECRETA_DE_DESARROLLO = "clave-de-desarrollo-cambiar-en-produccion"


class Settings(BaseSettings):
    app_name: str = "JobTrack AI"
    debug: bool = False
    database_url: str = "sqlite:///./radar.db"

    # Empty by default: the app still starts without it (the base CRUD
    # keeps working) and only fails, with a clear message, if AI
    # extraction is actually attempted without a configured key.
    gemini_api_key: str = ""

    # Optional automatic fallback used only when Gemini's request fails
    # (quota exhausted or a persistent outage). Groq has its own,
    # separate free quota. Left empty, the app behaves exactly as before —
    # there is simply no fallback, and Gemini's error is surfaced as-is.
    groq_api_key: str = ""

    # Signing key for session tokens (JWT) — see app/auth.py. Anyone who
    # knows this value can mint a valid token for any user, so production
    # deployments must override it with a unique, random value via the
    # environment. The default below exists only so the app can start
    # without any configuration in local development and tests.
    secret_key: str = CLAVE_SECRETA_DE_DESARROLLO

    # Session lifetime. 30 days, favoring convenience over strict
    # expiration for this use case.
    jwt_expira_minutos: int = 60 * 24 * 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
