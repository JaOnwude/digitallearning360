"""Students, guardians and enrollment (R11)."""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Boolean, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, tenant_fk
from app.db.types import str_enum


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"


class StudentStatus(StrEnum):
    ACTIVE = "active"
    GRADUATED = "graduated"
    WITHDRAWN = "withdrawn"


class Student(Base, TenantMixin):
    __tablename__ = "students"
    __extra_args__ = (
        tenant_fk("house_id", "houses"),
        UniqueConstraint("school_id", "admission_no", name="uq_students_admission_no"),
    )

    admission_no: Mapped[str] = mapped_column(String(30))
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    gender: Mapped[Gender | None] = mapped_column(str_enum(Gender))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    photo_key: Mapped[str | None] = mapped_column(String(255))
    house_id: Mapped[uuid.UUID | None]
    # Set when the student can log in (R5a).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[StudentStatus] = mapped_column(
        str_enum(StudentStatus), default=StudentStatus.ACTIVE
    )

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.middle_name, self.last_name) if p)


class Enrollment(Base, TenantMixin):
    """A student's arm for one academic session."""

    __tablename__ = "enrollments"
    __extra_args__ = (
        tenant_fk("student_id", "students", ondelete="CASCADE"),
        tenant_fk("arm_id", "arms"),
        tenant_fk("academic_session_id", "academic_sessions"),
        tenant_fk("stream_id", "streams"),
        UniqueConstraint(
            "school_id", "student_id", "academic_session_id", name="uq_enrollments_per_session"
        ),
    )

    student_id: Mapped[uuid.UUID]
    arm_id: Mapped[uuid.UUID]
    academic_session_id: Mapped[uuid.UUID]
    stream_id: Mapped[uuid.UUID | None]


class Guardian(Base, TenantMixin):
    __tablename__ = "guardians"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    # Encrypted at the application level (spec: security baseline).
    address_enc: Mapped[str | None] = mapped_column(String(2000))


class StudentGuardian(Base, TenantMixin):
    __tablename__ = "student_guardians"
    __extra_args__ = (
        tenant_fk("student_id", "students", ondelete="CASCADE"),
        tenant_fk("guardian_id", "guardians", ondelete="CASCADE"),
        UniqueConstraint("school_id", "student_id", "guardian_id", name="uq_student_guardians"),
    )

    student_id: Mapped[uuid.UUID]
    guardian_id: Mapped[uuid.UUID]
    relationship: Mapped[str | None] = mapped_column(String(30))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
