"""Who may do what with an arm's results this term (see the M2 plan's permission table)."""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import AcademicSession, Arm, ClassLevel, Section, Term
from app.auth.deps import Principal
from app.auth.models import Membership, Role
from app.db.helpers import get_or_404
from app.results.models import ResultSheet, SheetStatus, TeachingAssignment
from app.students.models import Enrollment, Student


def forbidden(message: str = "You don't have access to this class.") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, message)


async def current_term(db: AsyncSession) -> Term:
    term = await db.scalar(select(Term).where(Term.is_current))
    if term is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Set the current term in School setup first.")
    return term


@dataclass
class ArmContext:
    arm: Arm
    level: ClassLevel
    section: Section
    session: AcademicSession
    term: Term

    @property
    def label(self) -> str:
        return f"{self.level.name} {self.arm.name}"


async def arm_context(db: AsyncSession, arm_id: uuid.UUID) -> ArmContext:
    arm = await get_or_404(db, Arm, arm_id, "Class")
    level = await get_or_404(db, ClassLevel, arm.class_level_id, "Class")
    section = await get_or_404(db, Section, level.section_id, "Section")
    session = await get_or_404(db, AcademicSession, arm.academic_session_id, "Session")
    term = await current_term(db)
    if term.academic_session_id != arm.academic_session_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This class isn't in the current session.")
    return ArmContext(arm, level, section, session, term)


def is_admin(p: Principal) -> bool:
    return Role.SCHOOL_ADMIN in p.roles


async def heads_section(db: AsyncSession, p: Principal, section_id: uuid.UUID) -> bool:
    if is_admin(p):
        return True
    return bool(
        await db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.user_id == p.session.user_uuid,
                Membership.role == Role.SECTION_HEAD,
                Membership.section_id == section_id,
            )
        )
    )


def is_form_teacher(p: Principal, ctx: ArmContext) -> bool:
    return ctx.arm.form_teacher_user_id == p.session.user_uuid


async def teaches(db: AsyncSession, p: Principal, arm_id: uuid.UUID, subject_id: uuid.UUID) -> bool:
    return bool(
        await db.scalar(
            select(func.count())
            .select_from(TeachingAssignment)
            .where(
                TeachingAssignment.arm_id == arm_id,
                TeachingAssignment.subject_id == subject_id,
                TeachingAssignment.teacher_user_id == p.session.user_uuid,
            )
        )
    )


async def can_view_arm(db: AsyncSession, p: Principal, ctx: ArmContext) -> bool:
    """Staff connected to the class: admin, its section head, form teacher, its teachers,
    and counsellors (who comment on every student)."""
    if is_form_teacher(p, ctx) or Role.COUNSELLOR in p.roles:
        return True
    if await heads_section(db, p, ctx.section.id):
        return True
    return bool(
        await db.scalar(
            select(func.count())
            .select_from(TeachingAssignment)
            .where(
                TeachingAssignment.arm_id == ctx.arm.id,
                TeachingAssignment.teacher_user_id == p.session.user_uuid,
            )
        )
    )


async def sheet_for(db: AsyncSession, ctx: ArmContext, *, create: bool = True) -> ResultSheet:
    sheet = await db.scalar(
        select(ResultSheet)
        .where(ResultSheet.arm_id == ctx.arm.id, ResultSheet.term_id == ctx.term.id)
        .with_for_update()
    )
    if sheet is None:
        sheet = ResultSheet(
            school_id=ctx.arm.school_id,
            arm_id=ctx.arm.id,
            term_id=ctx.term.id,
            status=SheetStatus.DRAFT,  # set explicitly: column defaults only apply on insert
        )
        if create:
            db.add(sheet)
            await db.flush()
    return sheet


def require_draft(sheet: ResultSheet, what: str = "Scores") -> None:
    if sheet.status != SheetStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{what} can't be changed: this class's results are {sheet.status.value}. "
            "Ask the form teacher or principal to return them for corrections.",
        )


async def enrolled_students(db: AsyncSession, ctx: ArmContext) -> list[tuple[Enrollment, Student]]:
    rows = await db.execute(
        select(Enrollment, Student)
        .join(Student, Student.id == Enrollment.student_id)
        .where(Enrollment.arm_id == ctx.arm.id)
        .order_by(Student.last_name, Student.first_name)
    )
    return [(e, s) for e, s in rows]


# ---------------------------------------------------------------- R18 withholding


async def is_withheld(db: AsyncSession, student_id: uuid.UUID, term_id: uuid.UUID) -> bool:
    """R18: hide published results while fees are outstanding (when the school enables it).

    Fees and invoices arrive in M3; until then nothing is ever withheld. M3 replaces this
    body with: setting enabled AND invoice balance for (student, term) > 0.
    """
    del db, student_id, term_id
    return False
