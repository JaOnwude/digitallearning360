"""Database-level school isolation (spec R1, AC1). These hold even if app code has a bug."""

import asyncpg
import pytest

from app.db.registry import tenant_table_names
from tests.conftest import ClientFactory
from tests.factories import make_school, make_structure


async def test_every_school_table_has_forced_rls_policy(owner_conn: asyncpg.Connection) -> None:
    rows = await owner_conn.fetch(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
               EXISTS (SELECT 1 FROM pg_policies p
                       WHERE p.tablename = c.relname AND p.policyname = 'tenant_isolation') AS pol
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
          AND EXISTS (SELECT 1 FROM information_schema.columns i
                      WHERE i.table_name = c.relname AND i.column_name = 'school_id')
        """
    )
    in_db = {r["relname"]: (r["relrowsecurity"], r["relforcerowsecurity"], r["pol"]) for r in rows}
    assert sorted(in_db) == tenant_table_names(), "models and migrations disagree on tenant tables"
    missing = [t for t, flags in in_db.items() if flags != (True, True, True)]
    assert not missing, f"tables without enabled+forced RLS policy: {missing}"


async def test_app_role_sees_nothing_without_school_context(app_conn: asyncpg.Connection) -> None:
    school = await make_school()
    await make_structure(school)
    async with app_conn.transaction():
        count = await app_conn.fetchval("SELECT count(*) FROM sections")
    assert count == 0


async def test_app_role_sees_only_its_school(app_conn: asyncpg.Connection) -> None:
    a, b = await make_school(), await make_school()
    sa, sb = await make_structure(a), await make_structure(b)
    async with app_conn.transaction():
        await app_conn.execute("SELECT set_config('app.school_id', $1, true)", str(a.id))
        ids = {r["id"] for r in await app_conn.fetch("SELECT id FROM sections")}
    assert sa.section.id in ids
    assert sb.section.id not in ids


async def test_app_role_cannot_write_into_another_school(app_conn: asyncpg.Connection) -> None:
    a, b = await make_school(), await make_school()
    with pytest.raises(asyncpg.InsufficientPrivilegeError):  # RLS WITH CHECK violation
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('app.school_id', $1, true)", str(a.id))
            await app_conn.execute(
                "INSERT INTO houses (id, school_id, name) VALUES (gen_random_uuid(), $1, 'Red')",
                b.id,
            )


async def test_rows_cannot_reference_another_schools_rows(owner_conn: asyncpg.Connection) -> None:
    """Composite (school_id, id) foreign keys, even for a role that bypasses RLS."""
    a, b = await make_school(), await make_school()
    sb = await make_structure(b)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await owner_conn.execute(
            "INSERT INTO class_levels (id, school_id, section_id, name, sort) "
            "VALUES (gen_random_uuid(), $1, $2, 'JSS9', 9)",
            a.id,
            sb.section.id,
        )


async def test_audit_log_is_append_only_for_app(app_conn: asyncpg.Connection) -> None:
    school = await make_school()
    async with app_conn.transaction():
        await app_conn.execute("SELECT set_config('app.school_id', $1, true)", str(school.id))
        await app_conn.execute(
            "INSERT INTO audit_log (id, school_id, action) VALUES (gen_random_uuid(), $1, 't')",
            school.id,
        )
    for sql in ("UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with app_conn.transaction():
                await app_conn.execute(sql)


async def test_requests_must_come_through_the_web_proxy(client_for: ClientFactory) -> None:
    school = await make_school()
    c = client_for(school.slug)
    res = await c.post(
        "/api/auth/staff/login",
        json={"email": "x@example.com", "password": "x"},
        headers={"x-dl360-proxy-key": "wrong"},
    )
    assert res.status_code == 403


async def test_unknown_school_is_404(client_for: ClientFactory) -> None:
    res = await client_for("no-such-school").post(
        "/api/auth/parent/code", json={"email": "p@example.com"}
    )
    assert res.status_code == 404


async def test_app_role_cannot_bypass_rls_but_owner_is_flagged() -> None:
    """The API refuses to start in staging/production on an unsafe role (main.lifespan)."""
    import os

    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db.session import database_role_problems

    assert await database_role_problems() == []  # tests connect as dl360_app, like prod
    owner = create_async_engine(os.environ["DL360_MIGRATION_DATABASE_URL"])
    try:
        problems = await database_role_problems(owner)
    finally:
        await owner.dispose()
    assert any("superuser" in p for p in problems) and any("owns" in p for p in problems)
