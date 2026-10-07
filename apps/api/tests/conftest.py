"""Test fixtures.

Each run gets fresh Postgres and Redis containers. The schema is built by the real Alembic
migrations (as the owner), and the app connects as the restricted `dl360_app` role, so
row-level security behaves exactly as in production.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

API_DIR = Path(__file__).resolve().parents[1]
INIT_SQL = API_DIR.parents[1] / "infra" / "postgres-init.sql"
PROXY_KEY = "test-proxy-key"
BASE_DOMAIN = "dl360.test"


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="session", autouse=True)
def _infrastructure() -> Iterator[None]:
    with (
        PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg,
        RedisContainer("redis:7-alpine") as redis,
    ):
        owner_url = pg.get_connection_url()
        asyncio.run(_run_init_sql(owner_url))  # restricted app role, as infra does locally

        app_url = owner_url.replace(f"{pg.username}:{pg.password}@", "dl360_app:dl360_app@")
        host, port = redis.get_container_host_ip(), redis.get_exposed_port(6379)
        os.environ.update(
            DL360_ENV="test",
            DL360_DATABASE_URL=app_url,
            DL360_MIGRATION_DATABASE_URL=owner_url,
            DL360_REDIS_URL=f"redis://{host}:{port}/0",
            DL360_BASE_DOMAIN=BASE_DOMAIN,
            DL360_PROXY_KEY=PROXY_KEY,
            DL360_DEFAULT_SCHOOL_SLUG="",
        )
        from app.core.config import get_settings

        get_settings.cache_clear()
        _migrate()
        yield


async def _run_init_sql(owner_url: str) -> None:
    conn = await asyncpg.connect(_plain(owner_url))
    try:
        await conn.execute(INIT_SQL.read_text(encoding="utf-8"))
    finally:
        await conn.close()


def _migrate() -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def _clean_state() -> AsyncIterator[None]:
    """Each test starts with empty Redis (sessions, rate limits) and an empty outbox."""
    from app.core.redis import get_redis
    from app.notifications.service import sent_messages

    await get_redis().flushdb()
    sent_messages.clear()
    yield


@pytest.fixture
async def app_instance() -> AsyncIterator[FastAPI]:
    from app.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        yield app


ClientFactory = Callable[[str | None], AsyncClient]


@pytest.fixture
async def client_for(app_instance: FastAPI) -> AsyncIterator[ClientFactory]:
    """`client_for("progress")` → a client that looks like a browser on progress's site.

    Requests carry the headers our Next.js proxy adds. Pass None for no school host.
    Each client keeps its own cookies, like a separate browser.
    """
    clients: list[AsyncClient] = []

    def make(slug: str | None) -> AsyncClient:
        headers = {"x-dl360-proxy-key": PROXY_KEY}
        if slug is not None:
            headers["x-dl360-host"] = f"{slug}.{BASE_DOMAIN}"
        c = AsyncClient(
            transport=ASGITransport(app=app_instance), base_url="http://test", headers=headers
        )
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()


@pytest.fixture
async def client(client_for: ClientFactory) -> AsyncClient:
    """A client with no school context (health checks etc.)."""
    return client_for(None)


@pytest.fixture
async def owner_conn() -> AsyncIterator[asyncpg.Connection]:
    """A raw connection as the owner role, for assertions about the database itself."""
    conn = await asyncpg.connect(_plain(os.environ["DL360_MIGRATION_DATABASE_URL"]))
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def app_conn() -> AsyncIterator[asyncpg.Connection]:
    """A raw connection as the restricted app role (RLS applies)."""
    conn = await asyncpg.connect(_plain(os.environ["DL360_DATABASE_URL"]))
    try:
        yield conn
    finally:
        await conn.close()
