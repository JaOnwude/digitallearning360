from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from environment variables or `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="DL360_", extra="ignore")

    env: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False

    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://dl360:dl360@localhost:5436/dl360"),
    )
    redis_url: RedisDsn = Field(default=RedisDsn("redis://localhost:6380/0"))

    # Schools are served at {slug}.{base_domain}. The real domain is not chosen yet.
    base_domain: str = "digitallearning360.localhost"
    web_origin_scheme: Literal["http", "https"] = "http"
    web_port: int | None = 3360

    sentry_dsn: str | None = None

    @property
    def cors_origin_regex(self) -> str:
        """Allow the bare base domain and any single-label school subdomain."""
        domain = self.base_domain.replace(".", r"\.")
        port = rf":{self.web_port}" if self.web_port else ""
        return rf"^{self.web_origin_scheme}://([a-z0-9-]+\.)?{domain}{port}$"


@lru_cache
def get_settings() -> Settings:
    return Settings()
