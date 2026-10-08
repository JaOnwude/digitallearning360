import pytest
from fastapi import FastAPI

from app.auth.models import Role
from app.health.router import SentryTestError
from tests.conftest import ClientFactory
from tests.factories import make_school
from tests.helpers import signed_in


async def test_schema_names_are_unique(app_instance: FastAPI) -> None:
    """Two Pydantic models with the same name get mangled names (e.g. `app__fees__...`) in
    OpenAPI, which silently renames types in the generated web client. Give them distinct names."""
    names = app_instance.openapi()["components"]["schemas"]
    mangled = sorted(n for n in names if "__" in n)
    assert not mangled, f"rename these duplicated schema names: {mangled}"


async def test_sentry_test_route_is_admin_only(client_for: ClientFactory) -> None:
    """AC12: admins can trigger one deliberate backend error; nobody else can."""
    school = await make_school()
    assert (await client_for(school.slug).post("/api/health/sentry-test")).status_code == 401
    teacher = await signed_in(client_for, school, Role.TEACHER)
    assert (await teacher.post("/api/health/sentry-test")).status_code == 403
    admin = await signed_in(client_for, school, Role.SCHOOL_ADMIN)
    with pytest.raises(SentryTestError):  # unhandled → 500 in production, captured by Sentry
        await admin.post("/api/health/sentry-test")
