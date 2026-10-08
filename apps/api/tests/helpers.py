"""Sign test clients in, the same way a browser would."""

import pyotp
from httpx import AsyncClient

from app.auth.models import MFA_REQUIRED_ROLES, Role
from app.tenancy.models import School
from tests.conftest import ClientFactory
from tests.factories import PASSWORD, make_staff, totp_now


async def signed_in(
    client_for: ClientFactory, school: School, role: Role = Role.SCHOOL_ADMIN
) -> AsyncClient:
    """A client signed in as a new staff member with `role`, CSRF header pre-set."""
    secret = pyotp.random_base32() if role in MFA_REQUIRED_ROLES else None
    user = await make_staff(school, role, totp_secret=secret)
    c = client_for(school.slug)
    res = await c.post("/api/auth/staff/login", json={"email": user.email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    c.headers["x-csrf-token"] = c.cookies.get("dl360_csrf") or ""
    if secret:
        res = await c.post("/api/auth/totp/verify", json={"code": totp_now(secret)})
        assert res.json()["next"] == "done", res.text
    return c


async def signed_in_parent(client_for: ClientFactory, school: School, email: str) -> AsyncClient:
    """A client signed in as the parent with this email (via the emailed one-time code)."""
    import re

    from app.notifications.service import sent_messages

    c = client_for(school.slug)
    await c.post("/api/auth/parent/code", json={"email": email})
    match = re.search(r"\b(\d{6})\b", sent_messages[-1]["text"])
    assert match, "no code was emailed"
    res = await c.post("/api/auth/parent/verify", json={"email": email, "code": match.group(1)})
    assert res.status_code == 200, res.text
    c.headers["x-csrf-token"] = c.cookies.get("dl360_csrf") or ""
    return c
