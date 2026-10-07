"""Results configuration and teaching assignments (admin), and each staff member's classes."""

import uuid
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from app.academics.models import Arm, ClassLevel, LevelSubject, Section, Subject
from app.academics.service import active_session
from app.audit import service as audit
from app.auth.deps import CurrentPrincipal, SchoolAdmin
from app.auth.models import STAFF_ROLES, Membership, Role, User
from app.core.http import client_ip
from app.db.helpers import get_or_404
from app.results import config as rconfig
from app.results.access import current_term, forbidden, heads_section
from app.results.config import BandSpec, ComponentSpec
from app.results.models import (
    CommentSlot,
    ResultSheet,
    SheetStatus,
    SubjectCompletion,
    TeachingAssignment,
    Trait,
    TraitGroup,
)
from app.results.schemas import (
    ArmAssignmentsOut,
    ArmClassOut,
    AssignmentsOut,
    BandIO,
    CommentSlotIO,
    ComponentIO,
    FormTeacherIn,
    MyClassesOut,
    PersonOut,
    ReportConfigIO,
    SectionResultsConfigOut,
    SubjectAssignmentOut,
    SubjectClassOut,
    SubjectTeacherIn,
    TraitGroupIO,
)
from app.results.service import bands_for, components_for, term_label
from app.students.models import Enrollment
from app.tenancy.deps import CurrentSchool, TenantDB

router = APIRouter(prefix="/api/results", tags=["results"])


# ---------------------------------------------------------------- configuration


async def _config_out(db: TenantDB, section: Section) -> SectionResultsConfigOut:
    groups = []
    for g in await db.scalars(
        select(TraitGroup).where(TraitGroup.section_id == section.id).order_by(TraitGroup.sort)
    ):
        traits = await db.scalars(
            select(Trait.name).where(Trait.trait_group_id == g.id).order_by(Trait.sort)
        )
        groups.append(TraitGroupIO(name=g.name, traits=list(traits)))
    slots = await db.scalars(
        select(CommentSlot).where(CommentSlot.section_id == section.id).order_by(CommentSlot.sort)
    )
    return SectionResultsConfigOut(
        section_id=section.id,
        section_name=section.display_name,
        components=[
            ComponentIO(id=c.id, name=c.name, short_name=c.short_name, max_score=c.max_score)
            for c in await components_for(db, section.id)
        ],
        bands=[
            BandIO(
                letter=b.letter,
                descriptor=b.descriptor,
                min_score=b.min_score,
                max_score=b.max_score,
            )
            for b in await bands_for(db, section.id)
        ],
        trait_groups=groups,
        comment_slots=[CommentSlotIO(label=s.label, author_role=s.author_role) for s in slots],
        report=ReportConfigIO.model_validate(section.report_config or {}),
    )


async def _audit_config(
    db: TenantDB,
    school: CurrentSchool,
    admin: SchoolAdmin,
    request: Request,
    section: Section,
    what: str,
) -> None:
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=admin.session.user_uuid,
        action=f"results.config_{what}",
        entity_type="Section",
        entity_id=section.id,
        ip=client_ip(request),
    )


@router.get("/config/{section_id}", response_model=SectionResultsConfigOut)
async def get_config(
    section_id: uuid.UUID, _: SchoolAdmin, db: TenantDB
) -> SectionResultsConfigOut:
    return await _config_out(db, await get_or_404(db, Section, section_id, "Section"))


@router.put("/config/{section_id}/components", response_model=SectionResultsConfigOut)
async def put_components(
    section_id: uuid.UUID,
    body: list[ComponentIO],
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SectionResultsConfigOut:
    section = await get_or_404(db, Section, section_id, "Section")
    specs = [ComponentSpec(c.name, c.short_name, c.max_score, c.id) for c in body]
    await rconfig.set_components(db, school.id, section, specs)
    await _audit_config(db, school, admin, request, section, "components")
    return await _config_out(db, section)


@router.put("/config/{section_id}/bands", response_model=SectionResultsConfigOut)
async def put_bands(
    section_id: uuid.UUID,
    body: list[BandIO],
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SectionResultsConfigOut:
    section = await get_or_404(db, Section, section_id, "Section")
    specs = [BandSpec(b.letter, b.descriptor, b.min_score, b.max_score) for b in body]
    await rconfig.set_bands(db, school.id, section, specs)
    await _audit_config(db, school, admin, request, section, "bands")
    return await _config_out(db, section)


@router.put("/config/{section_id}/traits", response_model=SectionResultsConfigOut)
async def put_traits(
    section_id: uuid.UUID,
    body: list[TraitGroupIO],
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SectionResultsConfigOut:
    section = await get_or_404(db, Section, section_id, "Section")
    groups = [(g.name.strip(), [t.strip() for t in g.traits if t.strip()]) for g in body]
    await rconfig.set_traits(db, school.id, section, groups)
    await _audit_config(db, school, admin, request, section, "traits")
    return await _config_out(db, section)


@router.put("/config/{section_id}/comment-slots", response_model=SectionResultsConfigOut)
async def put_comment_slots(
    section_id: uuid.UUID,
    body: list[CommentSlotIO],
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SectionResultsConfigOut:
    section = await get_or_404(db, Section, section_id, "Section")
    await rconfig.set_comment_slots(
        db, school.id, section, [(s.label.strip(), s.author_role) for s in body]
    )
    await _audit_config(db, school, admin, request, section, "comment_slots")
    return await _config_out(db, section)


@router.put("/config/{section_id}/report", response_model=SectionResultsConfigOut)
async def put_report_config(
    section_id: uuid.UUID,
    body: ReportConfigIO,
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SectionResultsConfigOut:
    section = await get_or_404(db, Section, section_id, "Section")
    section.report_config = body.model_dump()
    await _audit_config(db, school, admin, request, section, "report")
    return await _config_out(db, section)


# ---------------------------------------------------------------- teaching assignments


async def _staff_people(db: TenantDB) -> dict[uuid.UUID, str]:
    rows = await db.execute(
        select(User.id, User.full_name)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.role.in_(STAFF_ROLES))
        .distinct()
    )
    return dict(sorted(((uid, name) for uid, name in rows), key=lambda r: r[1]))


@router.get("/assignments", response_model=AssignmentsOut)
async def get_assignments(_: SchoolAdmin, db: TenantDB) -> AssignmentsOut:
    session = await active_session(db)
    if session is None:
        return AssignmentsOut(arms=[], teachers=[])
    arms = (
        await db.execute(
            select(Arm, ClassLevel)
            .join(ClassLevel, ClassLevel.id == Arm.class_level_id)
            .where(Arm.academic_session_id == session.id)
            .order_by(ClassLevel.sort, Arm.name)
        )
    ).all()
    level_subjects: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    for level_id, subject_id, name in await db.execute(
        select(LevelSubject.class_level_id, Subject.id, Subject.name)
        .join(Subject, Subject.id == LevelSubject.subject_id)
        .order_by(LevelSubject.sort, Subject.name)
    ):
        level_subjects[level_id].append((subject_id, name))
    assigned = {
        (a.arm_id, a.subject_id): a.teacher_user_id
        for a in await db.scalars(select(TeachingAssignment))
    }
    return AssignmentsOut(
        arms=[
            ArmAssignmentsOut(
                arm_id=arm.id,
                label=f"{level.name} {arm.name}",
                section_id=level.section_id,
                form_teacher_user_id=arm.form_teacher_user_id,
                subjects=[
                    SubjectAssignmentOut(
                        subject_id=sid,
                        subject_name=name,
                        teacher_user_id=assigned.get((arm.id, sid)),
                    )
                    for sid, name in level_subjects[level.id]
                ],
            )
            for arm, level in arms
        ],
        teachers=[PersonOut(user_id=u, full_name=n) for u, n in (await _staff_people(db)).items()],
    )


async def _ensure_staff(db: TenantDB, user_id: uuid.UUID | None) -> None:
    if user_id is not None and user_id not in await _staff_people(db):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a staff member")


@router.put("/assignments/form-teacher", response_model=AssignmentsOut)
async def set_form_teacher(
    body: FormTeacherIn, request: Request, admin: SchoolAdmin, school: CurrentSchool, db: TenantDB
) -> AssignmentsOut:
    arm = await get_or_404(db, Arm, body.arm_id, "Class")
    await _ensure_staff(db, body.teacher_user_id)
    arm.form_teacher_user_id = body.teacher_user_id
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=admin.session.user_uuid,
        action="results.form_teacher_set",
        entity_type="Arm",
        entity_id=arm.id,
        after={"teacher_user_id": str(body.teacher_user_id) if body.teacher_user_id else None},
        ip=client_ip(request),
    )
    await db.flush()
    return await get_assignments(admin, db)


@router.put("/assignments/subject", response_model=AssignmentsOut)
async def set_subject_teacher(
    body: SubjectTeacherIn,
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> AssignmentsOut:
    await get_or_404(db, Arm, body.arm_id, "Class")
    await get_or_404(db, Subject, body.subject_id, "Subject")
    await _ensure_staff(db, body.teacher_user_id)
    existing = await db.scalar(
        select(TeachingAssignment).where(
            TeachingAssignment.arm_id == body.arm_id,
            TeachingAssignment.subject_id == body.subject_id,
        )
    )
    if body.teacher_user_id is None:
        if existing is not None:
            await db.delete(existing)
    elif existing is None:
        db.add(
            TeachingAssignment(
                school_id=school.id,
                arm_id=body.arm_id,
                subject_id=body.subject_id,
                teacher_user_id=body.teacher_user_id,
            )
        )
    else:
        existing.teacher_user_id = body.teacher_user_id
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=admin.session.user_uuid,
        action="results.subject_teacher_set",
        entity_type="Arm",
        entity_id=body.arm_id,
        after={
            "subject_id": str(body.subject_id),
            "teacher_user_id": str(body.teacher_user_id) if body.teacher_user_id else None,
        },
        ip=client_ip(request),
    )
    await db.flush()
    return await get_assignments(admin, db)


# ---------------------------------------------------------------- my classes


@router.get("/my-classes", response_model=MyClassesOut)
async def my_classes(p: CurrentPrincipal, db: TenantDB) -> MyClassesOut:
    """Everything the signed-in staff member works on this term."""
    if not (p.roles & STAFF_ROLES):
        raise forbidden()
    term = await current_term(db)
    session = await active_session(db)
    assert session is not None
    me = p.session.user_uuid
    statuses = {
        s.arm_id: s.status
        for s in await db.scalars(select(ResultSheet).where(ResultSheet.term_id == term.id))
    }
    done = {
        (c.arm_id, c.subject_id)
        for c in await db.scalars(
            select(SubjectCompletion).where(SubjectCompletion.term_id == term.id)
        )
    }
    arms = {
        arm.id: (arm, level)
        for arm, level in (
            await db.execute(
                select(Arm, ClassLevel)
                .join(ClassLevel, ClassLevel.id == Arm.class_level_id)
                .where(Arm.academic_session_id == session.id)
                .order_by(ClassLevel.sort, Arm.name)
            )
        ).all()
    }
    subject_classes = []
    for a, subject in await db.execute(
        select(TeachingAssignment, Subject)
        .join(Subject, Subject.id == TeachingAssignment.subject_id)
        .where(TeachingAssignment.teacher_user_id == me)
    ):
        if a.arm_id not in arms:
            continue
        arm, level = arms[a.arm_id]
        subject_classes.append(
            SubjectClassOut(
                arm_id=arm.id,
                arm_label=f"{level.name} {arm.name}",
                subject_id=subject.id,
                subject_name=subject.name,
                complete=(arm.id, subject.id) in done,
                status=statuses.get(arm.id, SheetStatus.DRAFT),
            )
        )
    counts = dict(
        (arm_id, n)
        for arm_id, n in await db.execute(
            select(Enrollment.arm_id, func.count()).group_by(Enrollment.arm_id)
        )
    )
    arm_classes = []
    for arm, level in arms.values():
        head = await heads_section(db, p, level.section_id)
        form = arm.form_teacher_user_id == me
        if not (head or form or Role.COUNSELLOR in p.roles):
            continue
        arm_classes.append(
            ArmClassOut(
                arm_id=arm.id,
                arm_label=f"{level.name} {arm.name}",
                section_id=level.section_id,
                status=statuses.get(arm.id, SheetStatus.DRAFT),
                student_count=counts.get(arm.id, 0),
                is_form_teacher=form,
                can_approve=head,
            )
        )
    return MyClassesOut(
        term_label=term_label(term, session.name),
        subject_classes=sorted(subject_classes, key=lambda c: (c.arm_label, c.subject_name)),
        arm_classes=arm_classes,
    )
