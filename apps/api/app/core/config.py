from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _asyncpg_url(url: str) -> str:
    """Hosts hand out `postgres://` / `postgresql://` URLs; SQLAlchemy async needs asyncpg."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    """All runtime configuration. Values come from environment variables or `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="DL360_", extra="ignore")

    env: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False

    # The app connects as a non-superuser role so Postgres RLS applies (R1).
    database_url: str = "postgresql+asyncpg://dl360_app:dl360_app@localhost:5436/dl360"
    # Migrations run as the table owner. Falls back to database_url when unset (managed hosts).
    migration_database_url: str | None = None
    redis_url: str = "redis://localhost:6380/0"

    # Schools are served at {slug}.{base_domain}. The real domain is not chosen yet.
    base_domain: str = "digitallearning360.localhost"
    # Used when the request host is not a school subdomain (e.g. a vercel.app staging URL).
    default_school_slug: str | None = None

    # Shared secret proving a request came through the Next.js proxy (see apps/web/src/proxy.ts).
    proxy_key: SecretStr = SecretStr("dev-proxy-key-change-me")
    # 32-byte key, base64url. Encrypts TOTP secrets and other sensitive fields.
    encryption_key: SecretStr = SecretStr("ZGV2LW9ubHktZW5jcnlwdGlvbi1rZXktMzJieXRlcyE=")

    resend_api_key: SecretStr | None = None
    email_from: str = "DigitalLearning360 <no-reply@digitallearning360.localhost>"

    sentry_dsn: str | None = None

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _normalise_db_url(cls, v: str | None) -> str | None:
        return _asyncpg_url(v) if v else v

    @property
    def is_deployed(self) -> bool:
        return self.env in ("staging", "production")

    @property
    def effective_migration_url(self) -> str:
        return self.migration_database_url or self.database_url

    def model_post_init(self, __context: object) -> None:
        if self.is_deployed:
            insecure = {
                "proxy_key": "dev-proxy-key-change-me",
                "encryption_key": "ZGV2LW9ubHktZW5jcnlwdGlvbi1rZXktMzJieXRlcyE=",
            }
            for name, dev_value in insecure.items():
                if getattr(self, name).get_secret_value() == dev_value:
                    raise ValueError(f"DL360_{name.upper()} must be set in {self.env}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
