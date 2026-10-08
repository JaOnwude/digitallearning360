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
    Subject,
    Term,
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


# ---------------------------------------------------------------- results (M2)


@dataclass
class ResultsWorld:
    school: School
    structure: Structure
    term: Term
    subjects: list[Subject]
    students: list[Student]
    enrollments: list[Enrollment]
    component_ids: list[uuid.UUID]
    slot_ids: dict[str, uuid.UUID]  # author role → slot id
    trait_ids: list[uuid.UUID]


async def make_results_world(
    n_students: int = 3, term_number: int = 1, slug: str | None = None
) -> ResultsWorld:
    """A JSS1 A class configured like Progress JSS, with the current term set."""
    from sqlalchemy import select

    from app.academics.models import LevelSubject
    from app.results import config as rconfig
    from app.results.config import BandSpec, ComponentSpec
    from app.results.models import AssessmentComponent, CommentAuthor, CommentSlot, Trait

    school = await make_school(slug)
    st = await make_structure(school)
    async with tenant_session(school) as db:
        section = await db.get(Section, st.section.id)
        assert section is not None
        await rconfig.set_components(db, school.id, section, [
            ComponentSpec("1st Assessment", "1st", 10), ComponentSpec("2nd Assessment", "2nd", 10),
            ComponentSpec("Project", "Proj", 10), ComponentSpec("Examination", "Exam", 70),
        ])  # fmt: skip
        await rconfig.set_bands(db, school.id, section, [
            BandSpec("A", "Distinction", 70, 100), BandSpec("B", "Excellent", 61, 69),
            BandSpec("C", "Credit", 55, 60), BandSpec("P", "Pass", 40, 54), BandSpec("F", "Fail", 0, 39),
        ])  # fmt: skip
        await rconfig.set_comment_slots(db, school.id, section, [
            ("Guidance Counsellor's Comment", CommentAuthor.COUNSELLOR),
            ("Form Master's Comment", CommentAuthor.FORM_TEACHER),
            ("Principal's Comment", CommentAuthor.SECTION_HEAD),
        ])  # fmt: skip
        await rconfig.set_traits(
            db, school.id, section, [("A. Social Behaviour", ["Punctuality", "Neatness"])]
        )
        section.report_config = {"template": "ebonyi_jss", "header_lines": ["EBONYI STATE SCHOOL SYSTEM"],
                                 "title": "Result Sheet", "show_positions": False}  # fmt: skip
        terms = [
            Term(school_id=school.id, academic_session_id=st.session.id, number=n,
                 is_current=(n == term_number))
            for n in (1, 2, 3)
        ]  # fmt: skip
        subjects = [Subject(school_id=school.id, name=n) for n in ("English", "Mathematics")]
        db.add_all([*terms, *subjects])
        await db.flush()
        for i, s in enumerate(subjects):
            db.add(
                LevelSubject(
                    school_id=school.id, class_level_id=st.level.id, subject_id=s.id, sort=i
                )
            )
        components = list(
            await db.scalars(select(AssessmentComponent).order_by(AssessmentComponent.sort))
        )
        slots = {s.author_role.value: s.id for s in await db.scalars(select(CommentSlot))}
        traits = list(await db.scalars(select(Trait.id).order_by(Trait.sort)))
        term = terms[term_number - 1]
    students = [
        await make_student(school, st, guardian_email=f"{unique('parent')}@example.com")
        for _ in range(n_students)
    ]
    async with tenant_session(school) as db:
        enrollments = [
            e
            for s in students
            for e in await db.scalars(select(Enrollment).where(Enrollment.student_id == s.id))
        ]
    return ResultsWorld(
        school=school, structure=st, term=term, subjects=subjects, students=students,
        enrollments=enrollments, component_ids=[c.id for c in components],
        slot_ids=slots, trait_ids=traits,
    )  # fmt: skip
