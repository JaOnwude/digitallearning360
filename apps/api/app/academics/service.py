"""School structure queries and changes (spec R8–R10). Callers pass a tenant session."""

import uuid
from collections import defaultdict

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import (
    AcademicSession,
    Arm,
    ClassLevel,
    House,
    LevelSubject,
    Section,
    Subject,
    Term,
)
from app.academics.schemas import (
    ArmOut,
    HouseOut,
    LevelOut,
    SectionOut,
    SessionOut,
    SetupOverviewOut,
    SubjectOut,
    TermOut,
)
from app.students.models import Enrollment


async def active_session(db: AsyncSession) -> AcademicSession | None:
    """The current term's session, else the most recent one."""
    current = await db.scalar(
        select(AcademicSession)
        .join(Term, Term.academic_session_id == AcademicSession.id)
        .where(Term.is_current)
    )
    if current is not None:
        return current
    return await db.scalar(select(AcademicSession).order_by(AcademicSession.name.desc()).limit(1))


async def overview(db: AsyncSession) -> SetupOverviewOut:
    session = await active_session(db)
    sections = list(await db.scalars(select(Section).order_by(Section.sort, Section.name)))
    levels = list(await db.scalars(select(ClassLevel).order_by(ClassLevel.sort, ClassLevel.name)))
    arms = (
        list(
            await db.scalars(
                select(Arm).where(Arm.academic_session_id == session.id).order_by(Arm.name)
            )
        )
        if session
        else []
    )
    counts = {
        arm_id: n
        for arm_id, n in await db.execute(
            select(Enrollment.arm_id, func.count()).group_by(Enrollment.arm_id)
        )
    }
    level_subjects = await db.execute(
        select(LevelSubject.class_level_id, LevelSubject.subject_id).order_by(LevelSubject.sort)
    )

    arms_by_level: dict[uuid.UUID, list[ArmOut]] = defaultdict(list)
    for a in arms:
        arms_by_level[a.class_level_id].append(
            ArmOut(id=a.id, name=a.name, student_count=counts.get(a.id, 0))
        )
    subjects_by_level: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for level_id, subject_id in level_subjects:
        subjects_by_level[level_id].append(subject_id)
    levels_by_section: dict[uuid.UUID, list[LevelOut]] = defaultdict(list)
    for lv in levels:
        levels_by_section[lv.section_id].append(
            LevelOut(
                id=lv.id,
                name=lv.name,
                sort=lv.sort,
                next_level_id=lv.next_level_id,
                arms=arms_by_level[lv.id],
                subject_ids=subjects_by_level[lv.id],
            )
        )

    sessions = list(await db.scalars(select(AcademicSession).order_by(AcademicSession.name.desc())))
    terms = list(await db.scalars(select(Term).order_by(Term.number)))
    terms_by_session: dict[uuid.UUID, list[TermOut]] = defaultdict(list)
    for t in terms:
        terms_by_session[t.academic_session_id].append(
            TermOut(
                id=t.id,
                number=t.number,
                starts_on=t.starts_on,
                ends_on=t.ends_on,
                next_term_begins=t.next_term_begins,
                is_current=t.is_current,
            )
        )

    return SetupOverviewOut(
        sections=[
            SectionOut(
                id=s.id,
                name=s.name,
                display_name=s.display_name,
                kind=s.kind,
                assessment_mode=s.assessment_mode,
                student_login_enabled=s.student_login_enabled,
                levels=levels_by_section[s.id],
            )
            for s in sections
        ],
        sessions=[SessionOut(id=s.id, name=s.name, terms=terms_by_session[s.id]) for s in sessions],
        active_session_id=session.id if session else None,
        houses=[
            HouseOut(id=h.id, name=h.name)
            for h in await db.scalars(select(House).order_by(House.name))
        ],
        subjects=[
            SubjectOut(id=s.id, name=s.name, code=s.code)
            for s in await db.scalars(select(Subject).order_by(Subject.name))
        ],
    )


async def make_term_current(db: AsyncSession, term: Term) -> None:
    # Clear first: a partial unique index allows only one current term per school.
    await db.execute(update(Term).where(Term.is_current).values(is_current=False))
    await db.flush()
    term.is_current = True


async def set_level_subjects(
    db: AsyncSession, school_id: uuid.UUID, subject: Subject, level_ids: list[uuid.UUID]
) -> None:
    """Replace the levels a subject is offered at. Unknown/other-school ids fail the FK."""
    await db.execute(delete(LevelSubject).where(LevelSubject.subject_id == subject.id))
    for level_id in dict.fromkeys(level_ids):
        db.add(LevelSubject(school_id=school_id, class_level_id=level_id, subject_id=subject.id))
    await db.flush()


async def arm_has_students(db: AsyncSession, arm_id: uuid.UUID) -> bool:
    return bool(
        await db.scalar(
            select(func.count()).select_from(Enrollment).where(Enrollment.arm_id == arm_id)
        )
    )
