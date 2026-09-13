from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The single .env file lives at the repo root (shared by docker-compose and
# as the reference for frontend/.env), not under backend/ — resolve it by
# path rather than relying on the process being launched from a particular
# working directory (pydantic-settings' env_file is otherwise CWD-relative).
_REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    # Supabase — publishable/secret keys (replacing the legacy anon/service_role
    # JWT keys, which Supabase is retiring; see docs/SETUP.md). Session JWTs
    # are verified via the Supabase SDK's own JWKS-based `get_claims` (see
    # app/core/security.py), so no separate JWT secret is configured here.
    supabase_url: str
    supabase_publishable_key: str
    supabase_secret_key: str

    # API
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    backend_cors_origins: list[str] = ["http://localhost:5173"]

    project_name: str = "ConnectSphere"


@lru_cache
def get_settings() -> Settings:
    return Settings()
