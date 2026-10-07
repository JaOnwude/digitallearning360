"""School structure: sections → class levels → arms; sessions/terms; subjects (R8–R10)."""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Boolean, Date, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, tenant_fk
from app.db.types import str_enum


class SectionKind(StrEnum):
    CRECHE = "creche"
    NURSERY = "nursery"
    PRIMARY = "primary"
    JUNIOR_SECONDARY = "junior_secondary"
    SENIOR_SECONDARY = "senior_secondary"
    OTHER = "other"


class AssessmentMode(StrEnum):
    SCORED = "scored"
    DEVELOPMENTAL = "developmental"
    MIXED = "mixed"


class Section(Base, TenantMixin):
    __tablename__ = "sections"
    __extra_args__ = (UniqueConstraint("school_id", "name", name="uq_sections_name"),)

    name: Mapped[str] = mapped_column(String(100))
    # Printed on documents, e.g. "Progress Junior Secondary School".
    display_name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[SectionKind] = mapped_column(str_enum(SectionKind))
    assessment_mode: Mapped[AssessmentMode] = mapped_column(
        str_enum(AssessmentMode), default=AssessmentMode.SCORED
    )
    student_login_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    head_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)


class ClassLevel(Base, TenantMixin):
    __tablename__ = "class_levels"
    __extra_args__ = (
        tenant_fk("section_id", "sections", ondelete="CASCADE"),
        tenant_fk("next_level_id", "class_levels"),
        UniqueConstraint("school_id", "section_id", "name", name="uq_class_levels_name"),
    )

    section_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(50))
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)
    # Promotion target, may cross sections (Primary 6 → JSS1). R16c.
    next_level_id: Mapped[uuid.UUID | None]


class Stream(Base, TenantMixin):
    """SS streams (Science, Arts, Commercial, ...)."""

    __tablename__ = "streams"
    __extra_args__ = (UniqueConstraint("school_id", "name", name="uq_streams_name"),)

    name: Mapped[str] = mapped_column(String(50))


class AcademicSession(Base, TenantMixin):
    __tablename__ = "academic_sessions"
    __extra_args__ = (UniqueConstraint("school_id", "name", name="uq_academic_sessions_name"),)

    name: Mapped[str] = mapped_column(String(20))  # "2026/2027"


class Term(Base, TenantMixin):
    __tablename__ = "terms"
    __extra_args__ = (
        tenant_fk("academic_session_id", "academic_sessions", ondelete="CASCADE"),
        UniqueConstraint("school_id", "academic_session_id", "number", name="uq_terms_number"),
        # Exactly one current term per school (R8).
        Index(
            "uq_terms_one_current",
            "school_id",
            unique=True,
            postgresql_where=sql_text("is_current"),
        ),
    )

    academic_session_id: Mapped[uuid.UUID]
    number: Mapped[int] = mapped_column(SmallInteger)  # 1..3
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    next_term_begins: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)


class Arm(Base, TenantMixin):
    __tablename__ = "arms"
    __extra_args__ = (
        tenant_fk("class_level_id", "class_levels", ondelete="CASCADE"),
        tenant_fk("academic_session_id", "academic_sessions", ondelete="CASCADE"),
        UniqueConstraint(
            "school_id", "class_level_id", "academic_session_id", "name", name="uq_arms_name"
        ),
    )

    class_level_id: Mapped[uuid.UUID]
    academic_session_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(30))  # "A", "Gold", ...


class House(Base, TenantMixin):
    __tablename__ = "houses"
    __extra_args__ = (UniqueConstraint("school_id", "name", name="uq_houses_name"),)

    name: Mapped[str] = mapped_column(String(50))


class Subject(Base, TenantMixin):
    __tablename__ = "subjects"
    __extra_args__ = (UniqueConstraint("school_id", "name", name="uq_subjects_name"),)

    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str | None] = mapped_column(String(20))


class LevelSubject(Base, TenantMixin):
    """A subject offered at a class level (R10)."""

    __tablename__ = "level_subjects"
    __extra_args__ = (
        tenant_fk("class_level_id", "class_levels", ondelete="CASCADE"),
        tenant_fk("subject_id", "subjects", ondelete="CASCADE"),
        UniqueConstraint(
            "school_id", "class_level_id", "subject_id", name="uq_level_subjects_pair"
        ),
    )

    class_level_id: Mapped[uuid.UUID]
    subject_id: Mapped[uuid.UUID]
    is_compulsory: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)
