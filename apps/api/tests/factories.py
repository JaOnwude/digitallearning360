"""Create test data through the app's own tenant-scoped sessions (so RLS applies)."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pyotp
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import (
    AcademicSession,
    Arm,
    ClassLevel,
    Section,
    SectionKind,
)
from app.auth.models import Membership, Role, User
from app.auth.passwords import hash_password
from app.core.crypto import encrypt
from app.db.session import get_sessionmaker
from app.students.models import Enrollment, Guardian, Student, StudentGuardian
from app.tenancy.deps import set_tenant
from app.tenancy.models import School

PASSWORD = "correct-horse-1"


def unique(prefix: str = "") -> str:
    """Unique-per-test values: tests share one database and must never collide."""
    return f"{prefix}{uuid.uuid4().hex[:8]}"


@asynccontextmanager
async def tenant_session(school: School) -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as db, db.begin():
        await set_tenant(db, school)
        yield db


async def make_school(slug: str | None = None) -> School:
    async with get_sessionmaker()() as db, db.begin():
        school = School(slug=slug or unique("s"), name="Test School")
        db.add(school)
    return school


async def make_staff(
    school: School, role: Role = Role.TEACHER, *, totp_secret: str | None = None
) -> User:
    async with tenant_session(school) as db:
        user = User(
            email=f"{unique('staff')}@example.com",
            full_name="Staff Member",
            password_hash=hash_password(PASSWORD),
        )
        if totp_secret:
            user.totp_secret_enc = encrypt(totp_secret)
            user.totp_enabled = True
        db.add(user)
        await db.flush()
        db.add(Membership(school_id=school.id, user_id=user.id, role=role))
    return user


def totp_now(secret: str) -> str:
    return pyotp.TOTP(secret).now()


@dataclass
class Structure:
    section: Section
    level: ClassLevel
    session: AcademicSession
    arm: Arm


async def make_structure(school: School, *, student_login: bool = True) -> Structure:
    async with tenant_session(school) as db:
        section = Section(
            school_id=school.id,
            name="Junior Secondary",
            display_name="Test Junior Secondary School",
            kind=SectionKind.JUNIOR_SECONDARY,
            student_login_enabled=student_login,
        )
        db.add(section)
        await db.flush()
        level = ClassLevel(school_id=school.id, section_id=section.id, name="JSS1", sort=1)
        session = AcademicSession(school_id=school.id, name="2026/2027")
        db.add_all([level, session])
        await db.flush()
        arm = Arm(
            school_id=school.id, class_level_id=level.id, academic_session_id=session.id, name="A"
        )
        db.add(arm)
    return Structure(section, level, session, arm)


async def make_student(
    school: School,
    structure: Structure,
    *,
    with_login: bool = True,
    must_change_password: bool = False,
    guardian_email: str | None = None,
) -> Student:
    async with tenant_session(school) as db:
        user = None
        if with_login:
            user = User(
                full_name="Test Student",
                password_hash=hash_password(PASSWORD),
                must_change_password=must_change_password,
            )
            db.add(user)
            await db.flush()
        student = Student(
            school_id=school.id,
            admission_no=unique("ADM").upper(),
            first_name="Ada",
            last_name="Okafor",
            user_id=user.id if user else None,
        )
        db.add(student)
        await db.flush()
        db.add(
            Enrollment(
                school_id=school.id,
                student_id=student.id,
                arm_id=structure.arm.id,
                academic_session_id=structure.session.id,
            )
        )
        if guardian_email:
            guardian = Guardian(school_id=school.id, full_name="Mrs Okafor", email=guardian_email)
            db.add(guardian)
            await db.flush()
            db.add(
                StudentGuardian(school_id=school.id, student_id=student.id, guardian_id=guardian.id)
            )
    return student
