"""CSV import of students and their guardians (spec R11, AC10).

Rows are validated first; a dry run reports every problem by spreadsheet row number
without saving anything. A real run saves the valid rows and reports the rest.
"""

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import Arm, House
from app.students import service
from app.students.models import Gender, Student
from app.students.schemas import ImportError_, ImportResultOut

MAX_ROWS = 5000
REQUIRED = ("admission_no", "first_name", "last_name", "class", "arm")
KNOWN = (
    *REQUIRED,
    "middle_name",
    "gender",
    "date_of_birth",
    "house",
    "guardian_name",
    "guardian_email",
    "guardian_phone",
    "guardian_relationship",
)
# Friendly header spellings people use in spreadsheets.
ALIASES = {
    "admission number": "admission_no",
    "admission no": "admission_no",
    "reg no": "admission_no",
    "surname": "last_name",
    "first name": "first_name",
    "other names": "middle_name",
    "middle name": "middle_name",
    "last name": "last_name",
    "sex": "gender",
    "dob": "date_of_birth",
    "date of birth": "date_of_birth",
    "parent name": "guardian_name",
    "parent email": "guardian_email",
    "parent phone": "guardian_phone",
}
TEMPLATE_HEADER = ",".join(KNOWN)


@dataclass
class ParsedRow:
    row: int
    admission_no: str
    first_name: str
    middle_name: str | None
    last_name: str
    gender: Gender | None
    date_of_birth: date | None
    arm: Arm
    house: House | None
    guardian_name: str | None
    guardian_email: str | None
    guardian_phone: str | None
    guardian_relationship: str | None


@dataclass
class Validation:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[ImportError_] = field(default_factory=list)
    total: int = 0


def _header(name: str) -> str:
    key = name.strip().lower().lstrip("﻿")
    return ALIASES.get(key, key.replace(" ", "_"))


def _parse_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("Use a date like 2014-05-21 or 21/05/2014")


def _parse_gender(value: str) -> Gender:
    v = value.strip().lower()
    if v in ("m", "male", "boy"):
        return Gender.MALE
    if v in ("f", "female", "girl"):
        return Gender.FEMALE
    raise ValueError("Use Male or Female")


async def validate(db: AsyncSession, content: bytes) -> Validation:
    result = Validation()

    def err(row: int, column: str | None, message: str) -> None:
        result.errors.append(ImportError_(row=row, column=column, message=message))

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")  # Excel "CSV" on some PCs
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        err(1, None, "The file is empty.")
        return result
    reader.fieldnames = [_header(h) for h in reader.fieldnames]
    missing = [c for c in REQUIRED if c not in reader.fieldnames]
    if missing:
        err(1, None, f"Missing column(s): {', '.join(missing)}. Download the template.")
        return result

    arms = await service.arms_by_label(db)
    houses = {h.name.lower(): h for h in await db.scalars(select(House))}
    existing = {
        a.upper()
        for a in await db.scalars(select(func.upper(Student.admission_no)))  # type: ignore[arg-type]
    }
    seen: dict[str, int] = {}

    for index, raw in enumerate(reader):
        row_no = index + 2  # header is row 1
        result.total += 1
        if result.total > MAX_ROWS:
            err(row_no, None, f"Import at most {MAX_ROWS} rows at a time.")
            break
        r = {k: (v or "").strip() for k, v in raw.items() if k}
        if not any(r.values()):
            result.total -= 1  # ignore blank lines
            continue
        before = len(result.errors)

        for col in REQUIRED:
            if not r.get(col):
                err(row_no, col, "Required")
        adm = r.get("admission_no", "").upper()
        if adm:
            if adm in existing:
                err(row_no, "admission_no", f"{adm} is already in the system")
            elif adm in seen:
                err(row_no, "admission_no", f"Same admission number as row {seen[adm]}")
            seen.setdefault(adm, row_no)

        arm = None
        if r.get("class") and r.get("arm"):
            arm = arms.get((r["class"].lower().replace(" ", ""), r["arm"].lower()))
            if arm is None:
                err(row_no, "arm", f"No arm {r['class']} {r['arm']} this session. Add it in Setup.")

        house = None
        if r.get("house"):
            house = houses.get(r["house"].lower())
            if house is None:
                err(row_no, "house", f"No house called {r['house']}")

        gender = dob = None
        if r.get("gender"):
            try:
                gender = _parse_gender(r["gender"])
            except ValueError as e:
                err(row_no, "gender", str(e))
        if r.get("date_of_birth"):
            try:
                dob = _parse_date(r["date_of_birth"])
            except ValueError as e:
                err(row_no, "date_of_birth", str(e))

        g_email = g_phone = None
        if r.get("guardian_email"):
            try:
                g_email = validate_email(r["guardian_email"], check_deliverability=False).normalized
            except EmailNotValidError:
                err(row_no, "guardian_email", "Not a valid email address")
        if r.get("guardian_phone"):
            g_phone = service.normalise_phone(r["guardian_phone"])
            if g_phone is None:
                err(row_no, "guardian_phone", "Use a Nigerian mobile number, e.g. 08031234567")
        if (g_email or g_phone) and not r.get("guardian_name"):
            err(row_no, "guardian_name", "Required when a parent email or phone is given")

        if len(result.errors) == before and arm is not None:
            result.rows.append(
                ParsedRow(
                    row=row_no,
                    admission_no=adm,
                    first_name=r["first_name"],
                    middle_name=r.get("middle_name") or None,
                    last_name=r["last_name"],
                    gender=gender,
                    date_of_birth=dob,
                    arm=arm,
                    house=house,
                    guardian_name=r.get("guardian_name") or None,
                    guardian_email=g_email,
                    guardian_phone=g_phone,
                    guardian_relationship=r.get("guardian_relationship") or None,
                )
            )
    return result


async def run(
    db: AsyncSession, school_id: uuid.UUID, content: bytes, *, dry_run: bool
) -> ImportResultOut:
    v = await validate(db, content)
    created = linked = 0
    guardians = service.GuardianIndex(school_id)
    if not dry_run and v.rows:
        await guardians.load(db)
        for p in v.rows:
            student = Student(
                school_id=school_id,
                admission_no=p.admission_no,
                first_name=p.first_name,
                middle_name=p.middle_name,
                last_name=p.last_name,
                gender=p.gender,
                date_of_birth=p.date_of_birth,
                house_id=p.house.id if p.house else None,
            )
            db.add(student)
            await db.flush()
            await service.set_arm(db, school_id, student, p.arm)
            if p.guardian_name and (p.guardian_email or p.guardian_phone):
                g = guardians.get_or_create(db, p.guardian_name, p.guardian_email, p.guardian_phone)
                if await service.link_guardian(db, school_id, student, g, p.guardian_relationship):
                    linked += 1
            created += 1
    return ImportResultOut(
        dry_run=dry_run,
        total_rows=v.total,
        valid_rows=len(v.rows),
        errors=v.errors,
        students_created=created,
        guardians_created=guardians.created,
        guardians_linked=linked,
    )
