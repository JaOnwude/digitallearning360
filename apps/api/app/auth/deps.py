"""Who is calling, and may they? Use these on every school-scoped endpoint."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.auth import sessions
from app.auth.models import Role
from app.auth.sessions import SessionData
from app.core.crypto import constant_time_equals
from app.tenancy.deps import CurrentSchool

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "x-csrf-token"


@dataclass
class Principal:
    token: str
    session: SessionData

    @property
    def roles(self) -> frozenset[Role]:
        return frozenset(Role(r) for r in self.session.roles)


async def _partial_principal(request: Request, school: CurrentSchool) -> Principal:
    """Logged in to *this* school, possibly with steps outstanding (2FA, password change)."""
    token = request.cookies.get(sessions.session_cookie_name())
    data = await sessions.load(token) if token else None
    if token is None or data is None or data.school_id != str(school.id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not constant_time_equals(sent, data.csrf):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")
    return Principal(token=token, session=data)


PartialPrincipal = Annotated[Principal, Depends(_partial_principal)]


async def _principal(p: PartialPrincipal) -> Principal:
    if not p.session.mfa_ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "two_factor_required")
    if p.session.must_change_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "password_change_required")
    return p


CurrentPrincipal = Annotated[Principal, Depends(_principal)]


def require_roles(*allowed: Role) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency: the caller is fully signed in and holds at least one of `allowed`."""
    allowed_set = frozenset(allowed)

    async def check(p: CurrentPrincipal) -> Principal:
        if not (p.roles & allowed_set):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this")
        return p

    return check


SchoolAdmin = Annotated[Principal, Depends(require_roles(Role.SCHOOL_ADMIN))]
