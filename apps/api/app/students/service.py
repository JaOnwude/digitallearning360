"""Student and guardian records (spec R11)."""

import re
import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import Arm, ClassLevel, House
from app.academics.service import active_session
from app.students.models import Enrollment, Guardian, Student, StudentGuardian
from app.students.schemas import GuardianOut, StudentDetail, StudentRow

_NG_LOCAL = re.compile(r"^0[789][01]\d{8}$")
_NG_INTL = re.compile(r"^\+234[789][01]\d{8}$")


def normalise_phone(raw: str) -> str | None:
    """Nigerian mobile numbers → +234XXXXXXXXXX. Returns None if it isn't one."""
    digits = re.sub(r"[\s\-().]", "", raw)
    if digits.startswith("234"):
        digits = "+" + digits
    if _NG_LOCAL.match(digits):
        return "+234" + digits[1:]
    if _NG_INTL.match(digits):
        return digits
    return None


async def _row_query(db: AsyncSession):
    """Students with their class/arm in the active session (if enrolled in it)."""
    session = await active_session(db)
    return (
        select(Student, ClassLevel.name, Arm.name, Arm.id, House.name)
        .outerjoin(House, House.id == Student.house_id)
        .outerjoin(
            Enrollment,
            and_(
                Enrollment.student_id == Student.id,
                Enrollment.academic_session_id == (session.id if session else None),
            ),
        )
        .outerjoin(Arm, Arm.id == Enrollment.arm_id)
        .outerjoin(ClassLevel, ClassLevel.id == Arm.class_level_id)
    )


def _row(
    s: Student, level: str | None, arm: str | None, arm_id: uuid.UUID | None, house: str | None
) -> StudentRow:
    return StudentRow(
        id=s.id,
        admission_no=s.admission_no,
        full_name=s.full_name,
        gender=s.gender,
        class_name=f"{level} {arm}" if level and arm else None,
        arm_name=arm,
        arm_id=arm_id,
        house=house,
        has_login=s.user_id is not None,
        status=s.status,
    )


async def list_students(
    db: AsyncSession, *, q: str | None, arm_id: uuid.UUID | None, page: int, page_size: int
) -> tuple[list[StudentRow], int]:
    query = await _row_query(db)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Student.admission_no.ilike(like),
                Student.first_name.ilike(like),
                Student.last_name.ilike(like),
                Student.middle_name.ilike(like),
            )
        )
    if arm_id:
        query = query.where(Arm.id == arm_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.execute(
        query.order_by(ClassLevel.sort, Arm.name, Student.last_name, Student.first_name)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return [_row(*r) for r in rows], total


async def student_detail(db: AsyncSession, student_id: uuid.UUID) -> StudentDetail | None:
    query = (await _row_query(db)).where(Student.id == student_id)
    found = (await db.execute(query)).first()
    if found is None:
        return None
    student = found[0]
    guardians = await db.execute(
        select(Guardian, StudentGuardian.relationship)
        .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
        .where(StudentGuardian.student_id == student_id)
        .order_by(StudentGuardian.is_primary.desc(), Guardian.full_name)
    )
    return StudentDetail(
        **_row(*found).model_dump(),
        first_name=student.first_name,
        middle_name=student.middle_name,
        last_name=student.last_name,
        date_of_birth=student.date_of_birth,
        house_id=student.house_id,
        guardians=[
            GuardianOut(
                id=g.id,
                full_name=g.full_name,
                email=g.email,
                phone=g.phone,
                relationship=rel,
                has_account=g.user_id is not None,
            )
            for g, rel in guardians
        ],
    )


async def set_arm(db: AsyncSession, school_id: uuid.UUID, student: Student, arm: Arm) -> None:
    """Enroll (or move) the student into `arm` for that arm's session."""
    enrollment = await db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student.id,
            Enrollment.academic_session_id == arm.academic_session_id,
        )
    )
    if enrollment is None:
        db.add(
            Enrollment(
                school_id=school_id,
                student_id=student.id,
                arm_id=arm.id,
                academic_session_id=arm.academic_session_id,
            )
        )
    else:
        enrollment.arm_id = arm.id


class GuardianIndex:
    """Find-or-create guardians by email or phone, so siblings share one parent record."""

    def __init__(self, school_id: uuid.UUID) -> None:
        self.school_id = school_id
        self.by_email: dict[str, Guardian] = {}
        self.by_phone: dict[str, Guardian] = {}
        self.created = 0

    async def load(self, db: AsyncSession) -> "GuardianIndex":
        for g in await db.scalars(select(Guardian)):
            if g.email:
                self.by_email[g.email.lower()] = g
            if g.phone:
                self.by_phone[g.phone] = g
        return self

    def get_or_create(
        self, db: AsyncSession, name: str, email: str | None, phone: str | None
    ) -> Guardian:
        g = (email and self.by_email.get(email.lower())) or (phone and self.by_phone.get(phone))
        if not g:
            g = Guardian(school_id=self.school_id, full_name=name, email=email, phone=phone)
            db.add(g)
            self.created += 1
        if email:
            self.by_email[email.lower()] = g
            g.email = g.email or email
        if phone:
            self.by_phone[phone] = g
            g.phone = g.phone or phone
        return g


async def link_guardian(
    db: AsyncSession,
    school_id: uuid.UUID,
    student: Student,
    guardian: Guardian,
    relationship: str | None,
) -> bool:
    """Link if not already linked. Returns True when a new link was made."""
    await db.flush()
    exists = await db.scalar(
        select(func.count())
        .select_from(StudentGuardian)
        .where(StudentGuardian.student_id == student.id, StudentGuardian.guardian_id == guardian.id)
    )
    if exists:
        return False
    first = not await db.scalar(
        select(func.count())
        .select_from(StudentGuardian)
        .where(StudentGuardian.student_id == student.id)
    )
    db.add(
        StudentGuardian(
            school_id=school_id,
            student_id=student.id,
            guardian_id=guardian.id,
            relationship=relationship,
            is_primary=first,
        )
    )
    return True


async def arms_by_label(db: AsyncSession) -> dict[tuple[str, str], Arm]:
    """Active-session arms keyed by (class name, arm name), case-insensitive."""
    session = await active_session(db)
    if session is None:
        return {}
    rows = await db.execute(
        select(Arm, ClassLevel.name)
        .join(ClassLevel, ClassLevel.id == Arm.class_level_id)
        .where(Arm.academic_session_id == session.id)
    )
    return {(level.lower().replace(" ", ""), arm.name.lower()): arm for arm, level in rows}
