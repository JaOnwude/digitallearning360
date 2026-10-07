from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.results.models import CommentAuthor, SheetStatus

# ---------------------------------------------------------------- configuration


class ComponentIO(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=50)
    short_name: str = Field(min_length=1, max_length=12)
    max_score: int = Field(ge=1, le=100)


class BandIO(BaseModel):
    letter: str = Field(min_length=1, max_length=4)
    descriptor: str = Field(min_length=1, max_length=40)
    min_score: int = Field(ge=0, le=100)
    max_score: int = Field(ge=0, le=100)


class TraitGroupIO(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    traits: list[str] = Field(max_length=40)


class CommentSlotIO(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    author_role: CommentAuthor


class ReportConfigIO(BaseModel):
    template: str = Field(default="standard", pattern=r"^(standard|ebonyi_jss)$")
    header_lines: list[str] = Field(default=[], max_length=3)
    title: str = Field(default="Termly Report", max_length=120)
    subtitle: str | None = Field(default=None, max_length=120)
    show_positions: bool = False


class SectionResultsConfigOut(BaseModel):
    section_id: UUID
    section_name: str
    components: list[ComponentIO]
    bands: list[BandIO]
    trait_groups: list[TraitGroupIO]
    comment_slots: list[CommentSlotIO]
    report: ReportConfigIO


# ---------------------------------------------------------------- assignments


class PersonOut(BaseModel):
    user_id: UUID
    full_name: str


class SubjectAssignmentOut(BaseModel):
    subject_id: UUID
    subject_name: str
    teacher_user_id: UUID | None


class ArmAssignmentsOut(BaseModel):
    arm_id: UUID
    label: str
    section_id: UUID
    form_teacher_user_id: UUID | None
    subjects: list[SubjectAssignmentOut]


class AssignmentsOut(BaseModel):
    arms: list[ArmAssignmentsOut]
    teachers: list[PersonOut]


class FormTeacherIn(BaseModel):
    arm_id: UUID
    teacher_user_id: UUID | None


class SubjectTeacherIn(BaseModel):
    arm_id: UUID
    subject_id: UUID
    teacher_user_id: UUID | None


# ---------------------------------------------------------------- my classes


class SubjectClassOut(BaseModel):
    arm_id: UUID
    arm_label: str
    subject_id: UUID
    subject_name: str
    complete: bool
    status: SheetStatus


class ArmClassOut(BaseModel):
    arm_id: UUID
    arm_label: str
    section_id: UUID
    status: SheetStatus
    student_count: int
    is_form_teacher: bool
    can_approve: bool


class MyClassesOut(BaseModel):
    term_label: str
    subject_classes: list[SubjectClassOut]
    arm_classes: list[ArmClassOut]


# ---------------------------------------------------------------- score entry


class ComponentOut(BaseModel):
    id: UUID
    name: str
    short_name: str
    max_score: int


class ScoreRow(BaseModel):
    enrollment_id: UUID
    admission_no: str
    full_name: str
    values: dict[str, Decimal | None]  # component id → score


class ScoreSheetOut(BaseModel):
    arm_label: str
    subject_name: str
    term_label: str
    status: SheetStatus
    editable: bool
    complete: bool
    components: list[ComponentOut]
    bands: list[BandIO]
    rows: list[ScoreRow]


class ScoreCellIn(BaseModel):
    enrollment_id: UUID
    component_id: UUID
    value: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)


class ScoresIn(BaseModel):
    arm_id: UUID
    subject_id: UUID
    cells: list[ScoreCellIn] = Field(min_length=1, max_length=2000)


class SavedOut(BaseModel):
    saved: int


class CompletionIn(BaseModel):
    arm_id: UUID
    subject_id: UUID
    complete: bool


# ---------------------------------------------------------------- ratings, comments, promotion


class TraitOut(BaseModel):
    id: UUID
    name: str


class TraitGroupOut(BaseModel):
    name: str
    traits: list[TraitOut]


class SlotOut(BaseModel):
    id: UUID
    label: str
    author_role: CommentAuthor
    editable: bool


class StudentReportEntry(BaseModel):
    enrollment_id: UUID
    full_name: str
    admission_no: str
    ratings: dict[str, int]  # trait id → 1..5
    comments: dict[str, str]  # slot id → text
    promoted: bool | None


class ReportEntryOut(BaseModel):
    arm_label: str
    term_number: int
    status: SheetStatus
    can_rate: bool
    can_decide_promotion: bool
    trait_groups: list[TraitGroupOut]
    slots: list[SlotOut]
    students: list[StudentReportEntry]


class RatingIn(BaseModel):
    trait_id: UUID
    value: int | None = Field(default=None, ge=1, le=5)


class RatingsIn(BaseModel):
    enrollment_id: UUID
    ratings: list[RatingIn] = Field(max_length=100)


class CommentIn(BaseModel):
    enrollment_id: UUID
    slot_id: UUID
    text: str = Field(max_length=600)


class PromotionIn(BaseModel):
    enrollment_id: UUID
    promoted: bool | None


# ---------------------------------------------------------------- broadsheet + workflow


class BroadsheetSubject(BaseModel):
    subject_id: UUID
    name: str
    teacher: str | None
    complete: bool


class BroadsheetCell(BaseModel):
    total: Decimal
    grade: str
    position: int


class BroadsheetRow(BaseModel):
    enrollment_id: UUID
    full_name: str
    admission_no: str
    cells: dict[str, BroadsheetCell]  # subject id → result
    total: Decimal
    subjects_taken: int
    average: Decimal
    position: int | None


class BroadsheetOut(BaseModel):
    arm_label: str
    term_label: str
    status: SheetStatus
    show_positions_on_cards: bool
    subjects: list[BroadsheetSubject]
    rows: list[BroadsheetRow]
    number_in_class: int
    class_average: Decimal
    missing: list[str]  # human-readable reasons submission is blocked
    allowed_actions: list[str]


class UnpublishIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class SheetStateOut(BaseModel):
    status: SheetStatus
    published_at: datetime | None


# ---------------------------------------------------------------- portal (parents, students)


class PublishedTermOut(BaseModel):
    snapshot_id: UUID
    term_label: str
    session: str
    average: Decimal
    published_at: datetime
    withheld: bool


class ChildResultsOut(BaseModel):
    student_id: UUID
    full_name: str
    class_label: str | None
    results: list[PublishedTermOut]


class SnapshotOut(BaseModel):
    snapshot_id: UUID
    data: dict[str, Any]


class VerifyOut(BaseModel):
    valid: bool
    school: str
    student: str | None = None
    class_label: str | None = None
    term_label: str | None = None
    published_at: datetime | None = None
