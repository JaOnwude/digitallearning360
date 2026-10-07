from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.academics.models import AssessmentMode, SectionKind

Name = Field(min_length=1, max_length=100)


class ArmOut(BaseModel):
    id: UUID
    name: str
    student_count: int


class LevelOut(BaseModel):
    id: UUID
    name: str
    sort: int
    next_level_id: UUID | None
    arms: list[ArmOut]
    subject_ids: list[UUID]


class SectionOut(BaseModel):
    id: UUID
    name: str
    display_name: str
    kind: SectionKind
    assessment_mode: AssessmentMode
    student_login_enabled: bool
    levels: list[LevelOut]


class TermOut(BaseModel):
    id: UUID
    number: int
    starts_on: date | None
    ends_on: date | None
    next_term_begins: date | None
    is_current: bool


class SessionOut(BaseModel):
    id: UUID
    name: str
    terms: list[TermOut]


class HouseOut(BaseModel):
    id: UUID
    name: str


class SubjectOut(BaseModel):
    id: UUID
    name: str
    code: str | None


class SetupOverviewOut(BaseModel):
    """Everything the setup screens need in one request."""

    sections: list[SectionOut]
    sessions: list[SessionOut]
    # Arms in `sections` belong to this session (the current term's, else the latest).
    active_session_id: UUID | None
    houses: list[HouseOut]
    subjects: list[SubjectOut]


class SectionUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    student_login_enabled: bool | None = None


class LevelUpdateIn(BaseModel):
    name: str = Name


class SessionCreateIn(BaseModel):
    name: str = Field(pattern=r"^\d{4}/\d{4}$", examples=["2027/2028"])


class TermUpdateIn(BaseModel):
    starts_on: date | None = None
    ends_on: date | None = None
    next_term_begins: date | None = None


class ArmCreateIn(BaseModel):
    class_level_id: UUID
    name: str = Field(min_length=1, max_length=30)


class HouseCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class SubjectIn(BaseModel):
    name: str = Name
    code: str | None = Field(default=None, max_length=20)
    level_ids: list[UUID] = []
