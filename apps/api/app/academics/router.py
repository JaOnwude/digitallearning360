"""School setup (admin only): sections, levels, sessions/terms, arms, houses, subjects."""

import uuid
from typing import Any

from fastapi import APIRouter, Request, status

from app.academics import service
from app.academics.models import AcademicSession, Arm, ClassLevel, House, Section, Subject, Term
from app.academics.schemas import (
    ArmCreateIn,
    HouseCreateIn,
    LevelUpdateIn,
    SectionUpdateIn,
    SessionCreateIn,
    SetupOverviewOut,
    SubjectIn,
    TermUpdateIn,
)
from app.audit import service as audit
from app.auth.deps import SchoolAdmin
from app.core.http import client_ip
from app.db.helpers import conflict, ensure_all_exist, flush_or_conflict, get_or_404
from app.tenancy.deps import CurrentSchool, TenantDB

router = APIRouter(prefix="/api/setup", tags=["setup"])


async def _audit(
    db: TenantDB,
    school: CurrentSchool,
    admin: SchoolAdmin,
    request: Request,
    action: str,
    entity: object,
    after: dict[str, Any] | None = None,
) -> None:
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=admin.session.user_uuid,
        action=action,
        entity_type=type(entity).__name__,
        entity_id=getattr(entity, "id", None),
        after=after,
        ip=client_ip(request),
    )


@router.get("/overview", response_model=SetupOverviewOut)
async def setup_overview(_: SchoolAdmin, db: TenantDB) -> SetupOverviewOut:
    return await service.overview(db)


@router.patch("/sections/{section_id}", response_model=SetupOverviewOut)
async def update_section(
    section_id: uuid.UUID,
    body: SectionUpdateIn,
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SetupOverviewOut:
    section = await get_or_404(db, Section, section_id, "Section")
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(section, field, value)
    await _audit(db, school, admin, request, "setup.section_updated", section, changes)
    return await service.overview(db)


@router.patch("/levels/{level_id}", response_model=SetupOverviewOut)
async def rename_level(
    level_id: uuid.UUID,
    body: LevelUpdateIn,
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SetupOverviewOut:
    level = await get_or_404(db, ClassLevel, level_id, "Class")
    level.name = body.name.strip()
    await flush_or_conflict(db, f"There is already a class called {level.name} in this section.")
    await _audit(db, school, admin, request, "setup.level_renamed", level, {"name": level.name})
    return await service.overview(db)


@router.post("/sessions", response_model=SetupOverviewOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreateIn,
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SetupOverviewOut:
    start, end = (int(y) for y in body.name.split("/"))
    if end != start + 1:
        raise conflict("A session runs over two consecutive years, e.g. 2027/2028.")
    session = AcademicSession(school_id=school.id, name=body.name)
    db.add(session)
    await flush_or_conflict(db, f"Session {body.name} already exists.")
    for number in (1, 2, 3):
        db.add(Term(school_id=school.id, academic_session_id=session.id, number=number))
    await _audit(db, school, admin, request, "setup.session_created", session, {"name": body.name})
    return await service.overview(db)


@router.patch("/terms/{term_id}", response_model=SetupOverviewOut)
async def update_term(
    term_id: uuid.UUID,
    body: TermUpdateIn,
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SetupOverviewOut:
    term = await get_or_404(db, Term, term_id, "Term")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(term, field, value)
    if term.starts_on and term.ends_on and term.ends_on <= term.starts_on:
        raise conflict("A term must end after it starts.")
    await _audit(
        db, school, admin, request, "setup.term_updated", term,
        {k: v.isoformat() if v else None for k, v in changes.items()},
    )  # fmt: skip
    return await service.overview(db)


@router.post("/terms/{term_id}/make-current", response_model=SetupOverviewOut)
async def make_term_current(
    term_id: uuid.UUID, request: Request, admin: SchoolAdmin, school: CurrentSchool, db: TenantDB
) -> SetupOverviewOut:
    term = await get_or_404(db, Term, term_id, "Term")
    await service.make_term_current(db, term)
    await _audit(db, school, admin, request, "setup.current_term_set", term)
    return await service.overview(db)


@router.post("/arms", response_model=SetupOverviewOut, status_code=status.HTTP_201_CREATED)
async def create_arm(
    body: ArmCreateIn, request: Request, admin: SchoolAdmin, school: CurrentSchool, db: TenantDB
) -> SetupOverviewOut:
    level = await get_or_404(db, ClassLevel, body.class_level_id, "Class")
    session = await service.active_session(db)
    if session is None:
        raise conflict("Create an academic session first.")
    arm = Arm(
        school_id=school.id,
        class_level_id=level.id,
        academic_session_id=session.id,
        name=body.name.strip(),
    )
    db.add(arm)
    await flush_or_conflict(db, f"{level.name} already has an arm called {arm.name}.")
    await _audit(db, school, admin, request, "setup.arm_created", arm, {"name": arm.name})
    return await service.overview(db)


@router.delete("/arms/{arm_id}", response_model=SetupOverviewOut)
async def delete_arm(
    arm_id: uuid.UUID, request: Request, admin: SchoolAdmin, school: CurrentSchool, db: TenantDB
) -> SetupOverviewOut:
    arm = await get_or_404(db, Arm, arm_id, "Arm")
    if await service.arm_has_students(db, arm.id):
        raise conflict("Move the students in this arm to another arm first.")
    await _audit(db, school, admin, request, "setup.arm_deleted", arm, {"name": arm.name})
    await db.delete(arm)
    return await service.overview(db)


@router.post("/houses", response_model=SetupOverviewOut, status_code=status.HTTP_201_CREATED)
async def create_house(
    body: HouseCreateIn, request: Request, admin: SchoolAdmin, school: CurrentSchool, db: TenantDB
) -> SetupOverviewOut:
    house = House(school_id=school.id, name=body.name.strip())
    db.add(house)
    await flush_or_conflict(db, f"House {house.name} already exists.")
    await _audit(db, school, admin, request, "setup.house_created", house, {"name": house.name})
    return await service.overview(db)


@router.delete("/houses/{house_id}", response_model=SetupOverviewOut)
async def delete_house(
    house_id: uuid.UUID, request: Request, admin: SchoolAdmin, school: CurrentSchool, db: TenantDB
) -> SetupOverviewOut:
    house = await get_or_404(db, House, house_id, "House")
    await _audit(db, school, admin, request, "setup.house_deleted", house, {"name": house.name})
    await db.delete(house)
    await flush_or_conflict(db, "Students are still in this house. Move them first.")
    return await service.overview(db)


@router.post("/subjects", response_model=SetupOverviewOut, status_code=status.HTTP_201_CREATED)
async def create_subject(
    body: SubjectIn, request: Request, admin: SchoolAdmin, school: CurrentSchool, db: TenantDB
) -> SetupOverviewOut:
    await ensure_all_exist(db, ClassLevel, body.level_ids, "class")
    subject = Subject(school_id=school.id, name=body.name.strip(), code=body.code)
    db.add(subject)
    await flush_or_conflict(db, f"Subject {subject.name} already exists.")
    await service.set_level_subjects(db, school.id, subject, body.level_ids)
    await _audit(
        db, school, admin, request, "setup.subject_created", subject, {"name": subject.name}
    )
    return await service.overview(db)


@router.put("/subjects/{subject_id}", response_model=SetupOverviewOut)
async def update_subject(
    subject_id: uuid.UUID,
    body: SubjectIn,
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SetupOverviewOut:
    subject = await get_or_404(db, Subject, subject_id, "Subject")
    await ensure_all_exist(db, ClassLevel, body.level_ids, "class")
    subject.name, subject.code = body.name.strip(), body.code
    await flush_or_conflict(db, f"Subject {subject.name} already exists.")
    await service.set_level_subjects(db, school.id, subject, body.level_ids)
    await _audit(
        db, school, admin, request, "setup.subject_updated", subject,
        {"name": subject.name, "levels": [str(i) for i in body.level_ids]},
    )  # fmt: skip
    return await service.overview(db)


@router.delete("/subjects/{subject_id}", response_model=SetupOverviewOut)
async def delete_subject(
    subject_id: uuid.UUID,
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> SetupOverviewOut:
    subject = await get_or_404(db, Subject, subject_id, "Subject")
    await _audit(
        db, school, admin, request, "setup.subject_deleted", subject, {"name": subject.name}
    )
    await db.delete(subject)  # level_subjects cascade; scores (M2) will block this
    await flush_or_conflict(db, "This subject already has scores and can't be deleted.")
    return await service.overview(db)
