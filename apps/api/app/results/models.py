"""Results: per-section assessment configuration, scores, workflow and published snapshots.

Spec R12–R17. Everything a report card shows is either configured per section here or
derived from scores; nothing about a school's format is hard-coded.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, tenant_fk
from app.db.types import str_enum

# ---------------------------------------------------------------- configuration (per section)


class AssessmentComponent(Base, TenantMixin):
    """A score column, e.g. "1st Assessment" out of 10. A section's components sum to 100."""

    __tablename__ = "assessment_components"
    __extra_args__ = (
        tenant_fk("section_id", "sections", ondelete="CASCADE"),
        UniqueConstraint("school_id", "section_id", "name", name="uq_assessment_components_name"),
        CheckConstraint("max_score > 0 AND max_score <= 100", name="max_score_range"),
    )

    section_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(50))
    short_name: Mapped[str] = mapped_column(String(12))
    max_score: Mapped[int] = mapped_column(SmallInteger)
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)


class GradingBand(Base, TenantMixin):
    """A grade, e.g. A "Distinction" for 70–100. A section's bands cover 0–100 exactly."""

    __tablename__ = "grading_bands"
    __extra_args__ = (
        tenant_fk("section_id", "sections", ondelete="CASCADE"),
        UniqueConstraint("school_id", "section_id", "letter", name="uq_grading_bands_letter"),
        CheckConstraint(
            "min_score >= 0 AND max_score <= 100 AND min_score <= max_score", name="range_valid"
        ),
    )

    section_id: Mapped[uuid.UUID]
    letter: Mapped[str] = mapped_column(String(4))
    descriptor: Mapped[str] = mapped_column(String(40))
    min_score: Mapped[int] = mapped_column(SmallInteger)
    max_score: Mapped[int] = mapped_column(SmallInteger)
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)


class TraitGroup(Base, TenantMixin):
    """e.g. "A. Social Behaviour". Traits in it are rated 1–5 (R16a)."""

    __tablename__ = "trait_groups"
    __extra_args__ = (
        tenant_fk("section_id", "sections", ondelete="CASCADE"),
        UniqueConstraint("school_id", "section_id", "name", name="uq_trait_groups_name"),
    )

    section_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(60))
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)


class Trait(Base, TenantMixin):
    __tablename__ = "traits"
    __extra_args__ = (
        tenant_fk("trait_group_id", "trait_groups", ondelete="CASCADE"),
        UniqueConstraint("school_id", "trait_group_id", "name", name="uq_traits_name"),
    )

    trait_group_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(60))
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)


class CommentAuthor(StrEnum):
    FORM_TEACHER = "form_teacher"
    COUNSELLOR = "counsellor"
    SECTION_HEAD = "section_head"


class CommentSlot(Base, TenantMixin):
    """A comment box on the report card and who writes it (R16b)."""

    __tablename__ = "comment_slots"
    __extra_args__ = (
        tenant_fk("section_id", "sections", ondelete="CASCADE"),
        UniqueConstraint("school_id", "section_id", "label", name="uq_comment_slots_label"),
    )

    section_id: Mapped[uuid.UUID]
    label: Mapped[str] = mapped_column(String(80))
    author_role: Mapped[CommentAuthor] = mapped_column(str_enum(CommentAuthor))
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)


# ---------------------------------------------------------------- who teaches what


class TeachingAssignment(Base, TenantMixin):
    """One teacher per arm + subject."""

    __tablename__ = "teaching_assignments"
    __extra_args__ = (
        tenant_fk("arm_id", "arms", ondelete="CASCADE"),
        tenant_fk("subject_id", "subjects", ondelete="CASCADE"),
        UniqueConstraint("school_id", "arm_id", "subject_id", name="uq_teaching_assignments"),
    )

    arm_id: Mapped[uuid.UUID]
    subject_id: Mapped[uuid.UUID]
    teacher_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


# ---------------------------------------------------------------- per term data


class Score(Base, TenantMixin):
    __tablename__ = "scores"
    __extra_args__ = (
        tenant_fk("enrollment_id", "enrollments", ondelete="CASCADE"),
        tenant_fk("subject_id", "subjects", ondelete="CASCADE"),
        tenant_fk("term_id", "terms", ondelete="CASCADE"),
        tenant_fk("component_id", "assessment_components", ondelete="CASCADE"),
        UniqueConstraint(
            "school_id",
            "enrollment_id",
            "subject_id",
            "term_id",
            "component_id",
            name="uq_scores_cell",
        ),
        CheckConstraint("value >= 0", name="value_non_negative"),
    )

    enrollment_id: Mapped[uuid.UUID]
    subject_id: Mapped[uuid.UUID]
    term_id: Mapped[uuid.UUID]
    component_id: Mapped[uuid.UUID]
    value: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    entered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class SubjectCompletion(Base, TenantMixin):
    """A subject teacher's "all scores entered" mark for one arm and term."""

    __tablename__ = "subject_completions"
    __extra_args__ = (
        tenant_fk("arm_id", "arms", ondelete="CASCADE"),
        tenant_fk("term_id", "terms", ondelete="CASCADE"),
        tenant_fk("subject_id", "subjects", ondelete="CASCADE"),
        UniqueConstraint(
            "school_id", "arm_id", "term_id", "subject_id", name="uq_subject_completions"
        ),
    )

    arm_id: Mapped[uuid.UUID]
    term_id: Mapped[uuid.UUID]
    subject_id: Mapped[uuid.UUID]
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class SheetStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PUBLISHED = "published"


class ResultSheet(Base, TenantMixin):
    """Workflow state of one arm's results for one term (R15)."""

    __tablename__ = "result_sheets"
    __extra_args__ = (
        tenant_fk("arm_id", "arms", ondelete="CASCADE"),
        tenant_fk("term_id", "terms", ondelete="CASCADE"),
        UniqueConstraint("school_id", "arm_id", "term_id", name="uq_result_sheets"),
    )

    arm_id: Mapped[uuid.UUID]
    term_id: Mapped[uuid.UUID]
    status: Mapped[SheetStatus] = mapped_column(str_enum(SheetStatus), default=SheetStatus.DRAFT)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TraitRating(Base, TenantMixin):
    __tablename__ = "trait_ratings"
    __extra_args__ = (
        tenant_fk("enrollment_id", "enrollments", ondelete="CASCADE"),
        tenant_fk("term_id", "terms", ondelete="CASCADE"),
        tenant_fk("trait_id", "traits", ondelete="CASCADE"),
        UniqueConstraint(
            "school_id", "enrollment_id", "term_id", "trait_id", name="uq_trait_ratings"
        ),
        CheckConstraint("value BETWEEN 1 AND 5", name="value_1_to_5"),
    )

    enrollment_id: Mapped[uuid.UUID]
    term_id: Mapped[uuid.UUID]
    trait_id: Mapped[uuid.UUID]
    value: Mapped[int] = mapped_column(SmallInteger)


class ReportComment(Base, TenantMixin):
    __tablename__ = "report_comments"
    __extra_args__ = (
        tenant_fk("enrollment_id", "enrollments", ondelete="CASCADE"),
        tenant_fk("term_id", "terms", ondelete="CASCADE"),
        tenant_fk("comment_slot_id", "comment_slots", ondelete="CASCADE"),
        UniqueConstraint(
            "school_id", "enrollment_id", "term_id", "comment_slot_id", name="uq_report_comments"
        ),
    )

    enrollment_id: Mapped[uuid.UUID]
    term_id: Mapped[uuid.UUID]
    comment_slot_id: Mapped[uuid.UUID]
    text: Mapped[str] = mapped_column(Text)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class PromotionDecision(Base, TenantMixin):
    """Promoted / not promoted, recorded on the third-term card (R16c)."""

    __tablename__ = "promotion_decisions"
    __extra_args__ = (
        tenant_fk("enrollment_id", "enrollments", ondelete="CASCADE"),
        tenant_fk("term_id", "terms", ondelete="CASCADE"),
        UniqueConstraint("school_id", "enrollment_id", "term_id", name="uq_promotion_decisions"),
    )

    enrollment_id: Mapped[uuid.UUID]
    term_id: Mapped[uuid.UUID]
    promoted: Mapped[bool] = mapped_column(Boolean)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class ReportSnapshot(Base, TenantMixin):
    """A published report card, frozen. Cards, parent views and QR checks read only this."""

    __tablename__ = "report_snapshots"
    __extra_args__ = (
        tenant_fk("enrollment_id", "enrollments", ondelete="CASCADE"),
        tenant_fk("term_id", "terms", ondelete="CASCADE"),
        tenant_fk("result_sheet_id", "result_sheets", ondelete="CASCADE"),
        UniqueConstraint(
            "school_id", "enrollment_id", "term_id", "version", name="uq_report_snapshots_version"
        ),
    )

    enrollment_id: Mapped[uuid.UUID]
    term_id: Mapped[uuid.UUID]
    result_sheet_id: Mapped[uuid.UUID]
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    # Superseded snapshots (after an unpublish + republish) stay for the audit trail.
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sha256: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
