from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.auth.models import Role

StaffRole = Role  # only staff roles are accepted (validated in the router)


class StaffRoleOut(BaseModel):
    role: Role
    section_id: UUID | None


class StaffOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str | None
    roles: list[StaffRoleOut]
    two_factor_enabled: bool
    is_active: bool


class StaffCreateIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    role: StaffRole
    # Required for section_head; optional scope for others.
    section_id: UUID | None = None


class StaffCreatedOut(BaseModel):
    staff: StaffOut
    # Present only when a new account was created. Shown once; give it to the person.
    temporary_password: str | None
