"""Broadsheet and the draft → submitted → approved → published workflow (R15, AC4)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select, update

from app.audit import service as audit
from app.auth.deps import CurrentPrincipal
from app.auth.models import User
from app.core.http import client_ip
from app.results.access import (
    ArmContext,
    arm_context,
    can_view_arm,
    forbidden,
    heads_section,
    is_admin,
    is_form_teacher,
    sheet_for,
)
from app.results.models import ReportSnapshot, ResultSheet, SheetStatus, TeachingAssignment
from app.results.schemas import (
    BroadsheetCell,
    BroadsheetOut,
    BroadsheetRow,
    BroadsheetSubject,
    SheetStateOut,
    UnpublishIn,
)
from app.results.service import (
    build_snapshot,
    load_arm,
    missing_for_submission,
    snapshot_hash,
    term_label,
)
from app.tenancy.deps import CurrentSchool, TenantDB

router = APIRouter(prefix="/api/results", tags=["results"])


async def _allowed_actions(
    db: TenantDB, p: CurrentPrincipal, ctx: ArmContext, sheet: ResultSheet
) -> list[str]:
    head = await heads_section(db, p, ctx.section.id)
    form = is_form_teacher(p, ctx)
    actions = []
    if sheet.status == SheetStatus.DRAFT and (form or head):
        actions.append("submit")
    if sheet.status == SheetStatus.SUBMITTED and (form or head):
        actions.append("return")
    if sheet.status == SheetStatus.SUBMITTED and head:
        actions.append("approve")
    if sheet.status == SheetStatus.APPROVED and head:
        actions += ["publish", "return"]
    if sheet.status == SheetStatus.PUBLISHED and is_admin(p):
        actions.append("unpublish")
    return actions


@router.get("/broadsheet", response_model=BroadsheetOut)
async def broadsheet(
    arm_id: Annotated[uuid.UUID, Query()], p: CurrentPrincipal, db: TenantDB
) -> BroadsheetOut:
    ctx = await arm_context(db, arm_id)
    if not await can_view_arm(db, p, ctx):
        raise forbidden()
    sheet = await sheet_for(db, ctx, create=False)
    data = await load_arm(db, ctx)
    teachers = {
        a.subject_id: name
        for a, name in await db.execute(
            select(TeachingAssignment, User.full_name)
            .join(User, User.id == TeachingAssignment.teacher_user_id)
            .where(TeachingAssignment.arm_id == ctx.arm.id)
        )
    }
    rows = []
    for e, s in data.students:
        r = data.result.students[e.id]
        rows.append(
            BroadsheetRow(
                enrollment_id=e.id,
                full_name=s.full_name,
                admission_no=s.admission_no,
                cells={
                    str(subj): BroadsheetCell(total=sr.total, grade=sr.grade, position=sr.position)
                    for subj, sr in r.subjects.items()
                },
                total=r.total,
                subjects_taken=r.subjects_taken,
                average=r.average,
                position=r.position,
            )
        )
    rows.sort(key=lambda r: (r.position is None, r.position or 0, r.full_name))
    return BroadsheetOut(
        arm_label=ctx.label,
        term_label=term_label(ctx.term, ctx.session.name),
        status=sheet.status,
        show_positions_on_cards=bool((ctx.section.report_config or {}).get("show_positions")),
        subjects=[
            BroadsheetSubject(
                subject_id=s.id,
                name=s.name,
                teacher=teachers.get(s.id),
                complete=s.id in data.completions,
            )
            for s in data.subjects
        ],
        rows=rows,
        number_in_class=data.result.number_in_class,
        class_average=data.result.class_average,
        missing=missing_for_submission(data) if sheet.status == SheetStatus.DRAFT else [],
        allowed_actions=await _allowed_actions(db, p, ctx, sheet),
    )


async def _transition(
    db: TenantDB,
    p: CurrentPrincipal,
    school: CurrentSchool,
    request: Request,
    arm_id: uuid.UUID,
    action: str,
    reason: str | None = None,
) -> SheetStateOut:
    ctx = await arm_context(db, arm_id)
    sheet = await sheet_for(db, ctx)  # row-locked: concurrent clicks can't double-publish
    if action not in await _allowed_actions(db, p, ctx, sheet):
        raise HTTPException(
            status.HTTP_409_CONFLICT
            if await can_view_arm(db, p, ctx)
            else status.HTTP_403_FORBIDDEN,
            f"You can't {action} results that are {sheet.status.value}.",
        )
    before = sheet.status
    now = datetime.now(UTC)
    me = p.session.user_uuid
    if action == "submit":
        missing = missing_for_submission(await load_arm(db, ctx))
        if missing:
            raise HTTPException(status.HTTP_409_CONFLICT, " ".join(missing))
        sheet.status, sheet.submitted_by, sheet.submitted_at = SheetStatus.SUBMITTED, me, now
    elif action == "return":
        sheet.status = SheetStatus.DRAFT
    elif action == "approve":
        sheet.status, sheet.approved_by, sheet.approved_at = SheetStatus.APPROVED, me, now
    elif action == "publish":
        await _publish(db, school, ctx, sheet, now)
        sheet.status, sheet.published_by, sheet.published_at = SheetStatus.PUBLISHED, me, now
    elif action == "unpublish":
        # Admin override (R15): snapshots stay for the record but stop being current.
        await db.execute(
            update(ReportSnapshot)
            .where(ReportSnapshot.result_sheet_id == sheet.id, ReportSnapshot.is_current)
            .values(is_current=False)
        )
        sheet.status, sheet.published_at = SheetStatus.DRAFT, None
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=me,
        action=f"results.{action}",
        entity_type="ResultSheet",
        entity_id=sheet.id,
        before={"status": before.value},
        after={"status": sheet.status.value, "arm": ctx.label, "reason": reason},
        ip=client_ip(request),
    )
    return SheetStateOut(status=sheet.status, published_at=sheet.published_at)


async def _publish(
    db: TenantDB, school: CurrentSchool, ctx: ArmContext, sheet: ResultSheet, now: datetime
) -> None:
    data = await load_arm(db, ctx)
    for enrollment, student in data.students:
        if not data.result.students[enrollment.id].subjects_taken:
            continue  # no scores at all: no card
        version = (
            await db.scalar(
                select(func.coalesce(func.max(ReportSnapshot.version), 0)).where(
                    ReportSnapshot.enrollment_id == enrollment.id,
                    ReportSnapshot.term_id == ctx.term.id,
                )
            )
            or 0
        ) + 1
        snapshot_data = await build_snapshot(db, school, ctx, data, enrollment, student, now)
        db.add(
            ReportSnapshot(
                school_id=school.id,
                enrollment_id=enrollment.id,
                term_id=ctx.term.id,
                result_sheet_id=sheet.id,
                version=version,
                is_current=True,
                data=snapshot_data,
                sha256=snapshot_hash(snapshot_data),
                published_at=now,
            )
        )
    await db.flush()


@router.post("/sheets/{arm_id}/submit", response_model=SheetStateOut)
async def submit(
    arm_id: uuid.UUID, request: Request, p: CurrentPrincipal, school: CurrentSchool, db: TenantDB
) -> SheetStateOut:
    return await _transition(db, p, school, request, arm_id, "submit")


@router.post("/sheets/{arm_id}/return", response_model=SheetStateOut)
async def return_for_corrections(
    arm_id: uuid.UUID, request: Request, p: CurrentPrincipal, school: CurrentSchool, db: TenantDB
) -> SheetStateOut:
    return await _transition(db, p, school, request, arm_id, "return")


@router.post("/sheets/{arm_id}/approve", response_model=SheetStateOut)
async def approve(
    arm_id: uuid.UUID, request: Request, p: CurrentPrincipal, school: CurrentSchool, db: TenantDB
) -> SheetStateOut:
    return await _transition(db, p, school, request, arm_id, "approve")


@router.post("/sheets/{arm_id}/publish", response_model=SheetStateOut)
async def publish(
    arm_id: uuid.UUID, request: Request, p: CurrentPrincipal, school: CurrentSchool, db: TenantDB
) -> SheetStateOut:
    return await _transition(db, p, school, request, arm_id, "publish")


@router.post("/sheets/{arm_id}/unpublish", response_model=SheetStateOut)
async def unpublish(
    arm_id: uuid.UUID,
    body: UnpublishIn,
    request: Request,
    p: CurrentPrincipal,
    school: CurrentSchool,
    db: TenantDB,
) -> SheetStateOut:
    """Admin override: reopens published results for correction. The reason is audited."""
    return await _transition(db, p, school, request, arm_id, "unpublish", body.reason.strip())
