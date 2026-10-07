import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import IdMixin, TenantMixin, TimestampMixin, tenant_fk
from app.db.types import str_enum


class User(Base, IdMixin, TimestampMixin):
    """A login identity. Global (no RLS): one person = one row, even across schools."""

    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email_lower", func.lower(text("email")), unique=True),
        UniqueConstraint("phone", name="uq_users_phone"),
    )

    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(20))
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    totp_secret_enc: Mapped[str | None] = mapped_column(String(255))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # sha256 hashes of one-time recovery codes
    recovery_code_hashes: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(StrEnum):
    SCHOOL_ADMIN = "school_admin"
    SECTION_HEAD = "section_head"
    BURSAR = "bursar"
    TEACHER = "teacher"
    COUNSELLOR = "counsellor"
    PARENT = "parent"
    STUDENT = "student"


STAFF_ROLES = frozenset(
    {Role.SCHOOL_ADMIN, Role.SECTION_HEAD, Role.BURSAR, Role.TEACHER, Role.COUNSELLOR}
)
MFA_REQUIRED_ROLES = frozenset({Role.SCHOOL_ADMIN, Role.BURSAR})


class Membership(Base, TenantMixin):
    """What a user may do in one school. A section_head is scoped to section_id."""

    __tablename__ = "memberships"
    __extra_args__ = (
        tenant_fk("section_id", "sections", ondelete="CASCADE"),
        UniqueConstraint(
            "school_id",
            "user_id",
            "role",
            "section_id",
            name="uq_memberships_user_role_section",
            postgresql_nulls_not_distinct=True,
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(str_enum(Role))
    section_id: Mapped[uuid.UUID | None]
