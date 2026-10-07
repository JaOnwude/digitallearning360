from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.auth.models import Role
from app.auth.sessions import SessionKind


class NextStep(StrEnum):
    """What the web app should show after a login step."""

    DONE = "done"
    TOTP_ENROLL = "totp_enroll"
    TOTP_VERIFY = "totp_verify"
    CHANGE_PASSWORD = "change_password"  # noqa: S105 - a step name, not a password


class StaffLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class StudentLoginIn(BaseModel):
    admission_no: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=1, max_length=256)


class ParentCodeIn(BaseModel):
    email: EmailStr


class ParentVerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class TotpCodeIn(BaseModel):
    # A 6-digit app code or a recovery code like "a1b2-c3d4".
    code: str = Field(min_length=6, max_length=12)


class PasswordChangeIn(BaseModel):
    current_password: str | None = Field(default=None, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class LoginOut(BaseModel):
    next: NextStep


class TotpEnrollOut(BaseModel):
    otpauth_uri: str
    qr_svg_data_uri: str


class TotpVerifyOut(BaseModel):
    next: NextStep
    # Shown once, only right after enrollment.
    recovery_codes: list[str] | None = None


class MeOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str | None
    kind: SessionKind
    roles: list[Role]
    next: NextStep


class MessageOut(BaseModel):
    message: str
