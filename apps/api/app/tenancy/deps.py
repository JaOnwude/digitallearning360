"""Request-scoped tenancy.

Every school-scoped endpoint depends on `TenantDB`: a session inside a transaction whose
`app.school_id` setting makes Postgres RLS (spec R1) hide every other school's rows.
"""

import hmac
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.tenancy.models import School
from app.tenancy.service import get_active_school, slug_from_host

PROXY_KEY_HEADER = "x-dl360-proxy-key"
HOST_HEADER = "x-dl360-host"


def _school_host(request: Request) -> str:
    """The school host, trusted only when the request came through our Next.js proxy."""
    key = request.headers.get(PROXY_KEY_HEADER, "")
    expected = get_settings().proxy_key.get_secret_value()
    if not hmac.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requests must come through the web app")
    host = request.headers.get(HOST_HEADER)
    if not host:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing school host")
    return host


async def get_school(request: Request) -> School:
    cached: School | None = getattr(request.state, "school", None)
    if cached is not None:
        return cached
    slug = slug_from_host(_school_host(request), get_settings())
    if slug is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "School not found")
    async with get_sessionmaker()() as db:
        school = await get_active_school(db, slug)
    if school is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "School not found")
    request.state.school = school
    return school


CurrentSchool = Annotated[School, Depends(get_school)]


async def tenant_db(school: CurrentSchool) -> AsyncIterator[AsyncSession]:
    """Per-request transaction scoped to the school; commits on success, rolls back on error.

    Work queued with `after_commit` (e.g. live-update notifications) runs only once the
    transaction has committed, so nobody is told about a change that then rolled back.
    """
    async with get_sessionmaker()() as db:
        async with db.begin():
            await set_tenant(db, school)
            yield db
        await run_after_commit(db)


def after_commit(db: AsyncSession, callback: Callable[[], Awaitable[None]]) -> None:
    db.info.setdefault("after_commit", []).append(callback)


async def run_after_commit(db: AsyncSession) -> None:
    for callback in db.info.pop("after_commit", []):
        await callback()


async def set_tenant(db: AsyncSession, school: School) -> None:
    """Scope the current transaction to a school. Must run inside a transaction."""
    await db.execute(text("SELECT set_config('app.school_id', :id, true)"), {"id": str(school.id)})


TenantDB = Annotated[AsyncSession, Depends(tenant_db)]
