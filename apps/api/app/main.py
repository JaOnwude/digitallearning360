from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.academics.router import router as setup_router
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.redis import close_redis
from app.db.session import dispose_engine
from app.fees import reconcile
from app.fees.router import router as fees_router
from app.fees.router_family import router as fees_family_router
from app.fees.webhook import router as webhook_router
from app.health.router import router as health_router
from app.notifications.router import router as events_router
from app.reports.router import router as reports_router
from app.results.router_entry import router as results_entry_router
from app.results.router_setup import router as results_setup_router
from app.results.router_workflow import router as results_workflow_router
from app.staff.router import router as staff_router
from app.students.router import router as students_router
from app.tenancy.router import router as school_router


def _operation_id(route: APIRoute) -> str:
    """Readable operationIds (e.g. `health_liveness`) so generated client hooks have good names."""
    prefix = route.tags[0] if route.tags else "default"
    return f"{prefix}_{route.name}"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if get_settings().env == "test":
        yield  # tests call reconcile() directly
    else:
        async with reconcile.background():
            yield
    await dispose_engine()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(json=settings.is_deployed)
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, send_default_pii=False)

    # No CORS: browsers reach the API only through the Next.js proxy on the school's own
    # origin (apps/web/src/proxy.ts), so every API call is same-origin.
    app = FastAPI(
        title="DigitalLearning360 API",
        version="0.1.0",
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url=None,
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(school_router)
    app.include_router(setup_router)
    app.include_router(staff_router)
    app.include_router(students_router)
    app.include_router(results_setup_router)
    app.include_router(results_entry_router)
    app.include_router(results_workflow_router)
    app.include_router(reports_router)
    app.include_router(fees_family_router)  # before fees_router: /fees/mine vs /fees/invoices/{id}
    app.include_router(fees_router)
    app.include_router(webhook_router)
    app.include_router(events_router)
    return app


app = create_app()
