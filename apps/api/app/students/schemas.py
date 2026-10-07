from datetime import date
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.students.models import Gender, StudentStatus


class GuardianOut(BaseModel):
    id: UUID
    full_name: str
    email: str | None
    phone: str | None
    relationship: str | None
    has_account: bool


class StudentRow(BaseModel):
    id: UUID
    admission_no: str
    full_name: str
    gender: Gender | None
    class_name: str | None
    arm_name: str | None
    arm_id: UUID | None
    house: str | None
    has_login: bool
    status: StudentStatus


class StudentPage(BaseModel):
    items: list[StudentRow]
    total: int
    page: int
    page_size: int


class StudentDetail(StudentRow):
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: date | None
    house_id: UUID | None
    guardians: list[GuardianOut]


class GuardianIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    relationship: str | None = Field(default=None, max_length=30)


class StudentIn(BaseModel):
    admission_no: str = Field(min_length=1, max_length=30)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    gender: Gender | None = None
    date_of_birth: date | None = None
    arm_id: UUID
    house_id: UUID | None = None
    guardian: GuardianIn | None = None


class StudentUpdateIn(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    gender: Gender | None = None
    date_of_birth: date | None = None
    arm_id: UUID | None = None
    house_id: UUID | None = None
    status: StudentStatus | None = None


class ImportError_(BaseModel):
    row: int  # spreadsheet row number (the header is row 1)
    column: str | None
    message: str


class ImportResultOut(BaseModel):
    dry_run: bool
    total_rows: int
    valid_rows: int
    errors: list[ImportError_]
    students_created: int
    guardians_created: int
    guardians_linked: int


class LoginSlipsIn(BaseModel):
    student_ids: list[UUID] = Field(min_length=1, max_length=1000)


class LoginSlip(BaseModel):
    student_id: UUID
    admission_no: str
    full_name: str
    class_name: str | None
    temporary_password: str
