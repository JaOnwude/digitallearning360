from contextlib import suppress
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.auth.deps import SchoolAdmin
from app.core.redis import get_redis
from app.db.session import get_sessionmaker

router = APIRouter(tags=["health"])


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"


class Readiness(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    redis: bool


@router.get("/healthz", response_model=Liveness)
async def liveness() -> Liveness:
    """The process is up. Used by the uptime monitor."""
    return Liveness()


@router.get("/readyz", response_model=Readiness)
async def readiness(response: Response) -> Readiness:
    """The API can reach its dependencies. Used by the load balancer."""
    # Report failures in the response rather than raising.
    db_ok = redis_ok = False
    with suppress(Exception):
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    with suppress(Exception):
        redis_ok = bool(await get_redis().ping())  # type: ignore[misc]
    ok = db_ok and redis_ok
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Readiness(status="ok" if ok else "degraded", database=db_ok, redis=redis_ok)


class SentryTestError(RuntimeError):
    """Deliberately unhandled, so Sentry records it (spec AC12)."""


@router.post("/api/health/sentry-test", include_in_schema=False)
async def sentry_test(_: SchoolAdmin) -> None:
    """AC12: an admin triggers one backend error to prove Sentry receives it."""
    raise SentryTestError("DigitalLearning360 Sentry test error (backend)")
