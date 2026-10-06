"""Test fixtures. Each test run gets fresh Postgres and Redis containers (testcontainers)."""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session", autouse=True)
def _containers() -> Iterator[None]:
    with (
        PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg,
        RedisContainer("redis:7-alpine") as redis,
    ):
        os.environ["DL360_ENV"] = "test"
        os.environ["DL360_DATABASE_URL"] = pg.get_connection_url()
        host, port = redis.get_container_host_ip(), redis.get_exposed_port(6379)
        os.environ["DL360_REDIS_URL"] = f"redis://{host}:{port}/0"

        from app.core.config import get_settings

        get_settings.cache_clear()
        yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        yield c
