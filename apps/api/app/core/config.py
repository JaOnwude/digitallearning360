from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _asyncpg_url(url: str) -> str:
    """Normalise a host-provided Postgres URL (Render, Neon, ...) for SQLAlchemy + asyncpg.

    - `postgres://` / `postgresql://` → `postgresql+asyncpg://`
    - libpq's `sslmode=require` → asyncpg's `ssl=require`
    - libpq-only options asyncpg rejects (e.g. Neon's `channel_binding`) are dropped
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix) :]
            break
    parts = urlsplit(url)
    if not parts.query:
        return url
    params = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            if value != "disable":
                params.append(("ssl", "require" if value in ("prefer", "allow") else value))
        elif key not in _LIBPQ_ONLY:
            params.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(params)))


_LIBPQ_ONLY = frozenset({"channel_binding", "gssencmode", "target_session_attrs", "options"})


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

    # Paystack secret key: sk_test_… locally/staging, sk_live_… in production only.
    paystack_secret_key: SecretStr | None = None
    paystack_base_url: str = "https://api.paystack.co"

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
        # Real money only moves in production; test money never does.
        key = self.paystack_secret_key.get_secret_value() if self.paystack_secret_key else ""
        if self.env == "production" and key.startswith("sk_test_"):
            raise ValueError("Production must use a live Paystack key (sk_live_…)")
        if self.env != "production" and key.startswith("sk_live_"):
            raise ValueError(f"A live Paystack key must never be used in {self.env}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
