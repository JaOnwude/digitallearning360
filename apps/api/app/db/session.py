from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(
            str(get_settings().database_url), pool_pre_ping=True, pool_size=10, max_overflow=10
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed by the caller."""
    async with get_sessionmaker()() as session:
        yield session


async def database_role_problems(engine: AsyncEngine | None = None) -> list[str]:
    """Why the app's database role could defeat tenant isolation (spec R1), if it could.

    Postgres row-level security is the last line between schools. It does nothing for a
    superuser or a BYPASSRLS role, and a table owner can switch it off or ignore the ledger's
    append-only grants. The app must connect as a restricted role (infra/postgres-init.sql);
    migrations run separately as the owner (DL360_MIGRATION_DATABASE_URL).
    """
    async with (engine or get_engine()).connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT r.rolname, r.rolsuper, r.rolbypassrls,"
                    " (SELECT count(*) FROM pg_tables t WHERE t.schemaname = 'public'"
                    "  AND t.tableowner = r.rolname) AS owned"
                    " FROM pg_roles r WHERE r.rolname = current_user"
                )
            )
        ).one()
    problems = []
    if row.rolsuper:
        problems.append(f"{row.rolname} is a superuser")
    if row.rolbypassrls:
        problems.append(f"{row.rolname} has BYPASSRLS")
    if row.owned:
        problems.append(f"{row.rolname} owns {row.owned} tables")
    return problems
