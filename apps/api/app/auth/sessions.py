"""Server-side sessions in Redis, referenced by an opaque httpOnly cookie (R7).

The cookie is host-only on the school's own origin (the browser reaches the API through the
Next.js proxy), and the session records its school, so it can't be replayed elsewhere.
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from fastapi import Response

from app.core.config import get_settings
from app.core.crypto import new_token, sha256_hex
from app.core.redis import get_redis


class SessionKind(StrEnum):
    STAFF = "staff"
    PARENT = "parent"
    STUDENT = "student"


IDLE_SECONDS = {
    SessionKind.STAFF: 12 * 3600,
    SessionKind.PARENT: 7 * 24 * 3600,
    SessionKind.STUDENT: 7 * 24 * 3600,
}
ABSOLUTE_SECONDS = {
    SessionKind.STAFF: 7 * 24 * 3600,
    SessionKind.PARENT: 30 * 24 * 3600,
    SessionKind.STUDENT: 30 * 24 * 3600,
}


@dataclass
class SessionData:
    user_id: str
    school_id: str
    kind: SessionKind
    roles: list[str]
    mfa_ok: bool
    must_change_password: bool
    csrf: str = field(default_factory=new_token)
    created_at: float = field(default_factory=time.time)
    # TOTP secret awaiting confirmation during enrollment (encrypted).
    pending_totp_enc: str | None = None

    @property
    def user_uuid(self) -> uuid.UUID:
        return uuid.UUID(self.user_id)

    @property
    def fully_authenticated(self) -> bool:
        return self.mfa_ok and not self.must_change_password


def session_cookie_name() -> str:
    # __Host- prefix: browser enforces Secure, Path=/ and no Domain (host-only).
    return "__Host-dl360_session" if get_settings().is_deployed else "dl360_session"


def csrf_cookie_name() -> str:
    return "__Host-dl360_csrf" if get_settings().is_deployed else "dl360_csrf"


def _key(token: str) -> str:
    return f"sess:{sha256_hex(token)}"


async def create(response: Response, data: SessionData) -> str:
    token = new_token()
    await _save(token, data)
    _set_cookies(response, token, data)
    return token


async def load(token: str) -> SessionData | None:
    raw = await get_redis().get(_key(token))
    if raw is None:
        return None
    payload = json.loads(raw)
    payload["kind"] = SessionKind(payload["kind"])
    data = SessionData(**payload)
    if time.time() - data.created_at > ABSOLUTE_SECONDS[data.kind]:
        await destroy(token)
        return None
    await get_redis().expire(_key(token), IDLE_SECONDS[data.kind])  # sliding idle timeout
    return data


async def save(token: str, data: SessionData) -> None:
    await _save(token, data)


async def _save(token: str, data: SessionData) -> None:
    await get_redis().set(_key(token), json.dumps(asdict(data)), ex=IDLE_SECONDS[data.kind])


async def destroy(token: str) -> None:
    await get_redis().delete(_key(token))


def _set_cookies(response: Response, token: str, data: SessionData) -> None:
    secure = get_settings().is_deployed
    max_age = ABSOLUTE_SECONDS[data.kind]
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    # Readable by JS on purpose: the web client echoes it in X-CSRF-Token (double submit).
    response.set_cookie(
        csrf_cookie_name(),
        data.csrf,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_cookies(response: Response) -> None:
    response.delete_cookie(session_cookie_name(), path="/")
    response.delete_cookie(csrf_cookie_name(), path="/")
