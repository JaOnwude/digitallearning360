"""Score entry (subject teachers), ratings/comments/promotion (form teacher, counsellor, head)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select

from app.academics.models import Subject
from app.auth.deps import CurrentPrincipal
from app.auth.models import Role
from app.db.helpers import get_or_404
from app.results.access import (
    ArmContext,
    arm_context,
    can_view_arm,
    enrolled_students,
    forbidden,
    heads_section,
    is_form_teacher,
    require_draft,
    sheet_for,
    teaches,
)
from app.results.models import (
    CommentAuthor,
    CommentSlot,
    PromotionDecision,
    ReportComment,
    Score,
    SheetStatus,
    SubjectCompletion,
    Trait,
    TraitGroup,
    TraitRating,
)
from app.results.schemas import (
    BandIO,
    CommentIn,
    CompletionIn,
    ComponentOut,
    PromotionIn,
    RatingsIn,
    ReportEntryOut,
    SavedOut,
    ScoreRow,
    ScoreSheetOut,
    ScoresIn,
    SlotOut,
    StudentReportEntry,
    TraitGroupOut,
    TraitOut,
)
from app.results.service import bands_for, components_for, subjects_for_level, term_label
from app.students.models import Enrollment
from app.tenancy.deps import TenantDB

router = APIRouter(prefix="/api/results", tags=["results"])


async def _may_enter_scores(
    db: TenantDB, p: CurrentPrincipal, ctx: ArmContext, subject_id: uuid.UUID
) -> bool:
    return await teaches(db, p, ctx.arm.id, subject_id) or await heads_section(
        db, p, ctx.section.id
    )


async def _subject_in_level(db: TenantDB, ctx: ArmContext, subject_id: uuid.UUID) -> Subject:
    subject = await get_or_404(db, Subject, subject_id, "Subject")
    if subject.id not in {s.id for s in await subjects_for_level(db, ctx.level.id)}:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"{ctx.level.name} doesn't offer {subject.name}"
        )
    return subject


async def _enrollment_in_arm(db: TenantDB, ctx: ArmContext, enrollment_id: uuid.UUID) -> Enrollment:
    enrollment = await get_or_404(db, Enrollment, enrollment_id, "Student")
    if enrollment.arm_id != ctx.arm.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found in this class")
    return enrollment


# ---------------------------------------------------------------- scores


@router.get("/scores", response_model=ScoreSheetOut)
async def get_scores(
    arm_id: Annotated[uuid.UUID, Query()],
    subject_id: Annotated[uuid.UUID, Query()],
    p: CurrentPrincipal,
    db: TenantDB,
) -> ScoreSheetOut:
    ctx = await arm_context(db, arm_id)
    subject = await _subject_in_level(db, ctx, subject_id)
    may_edit = await _may_enter_scores(db, p, ctx, subject.id)
    if not (may_edit or await can_view_arm(db, p, ctx)):
        raise forbidden()
    sheet = await sheet_for(db, ctx, create=False)
    components = await components_for(db, ctx.section.id)
    students = await enrolled_students(db, ctx)
    values: dict[uuid.UUID, dict[str, object]] = {e.id: {} for e, _ in students}
    if students:
        for sc in await db.scalars(
            select(Score).where(
                Score.enrollment_id.in_(values),
                Score.subject_id == subject.id,
                Score.term_id == ctx.term.id,
            )
        ):
            values[sc.enrollment_id][str(sc.component_id)] = sc.value
    complete = bool(
        await db.scalar(
            select(SubjectCompletion.id).where(
                SubjectCompletion.arm_id == ctx.arm.id,
                SubjectCompletion.term_id == ctx.term.id,
                SubjectCompletion.subject_id == subject.id,
            )
        )
    )
    return ScoreSheetOut(
        arm_label=ctx.label,
        subject_name=subject.name,
        term_label=term_label(ctx.term, ctx.session.name),
        status=sheet.status,
        editable=may_edit and sheet.status == SheetStatus.DRAFT and not complete,
        complete=complete,
        components=[
            ComponentOut(id=c.id, name=c.name, short_name=c.short_name, max_score=c.max_score)
            for c in components
        ],
        bands=[
            BandIO(
                letter=b.letter,
                descriptor=b.descriptor,
                min_score=b.min_score,
                max_score=b.max_score,
            )
            for b in await bands_for(db, ctx.section.id)
        ],
        rows=[
            ScoreRow(
                enrollment_id=e.id,
                admission_no=s.admission_no,
                full_name=s.full_name,
                values={str(c.id): values[e.id].get(str(c.id)) for c in components},  # type: ignore[misc]
            )
            for e, s in students
        ],
    )


@router.put("/scores", response_model=SavedOut)
async def save_scores(body: ScoresIn, p: CurrentPrincipal, db: TenantDB) -> SavedOut:
    """Batch upsert (autosave). A null value clears the cell."""
    ctx = await arm_context(db, body.arm_id)
    subject = await _subject_in_level(db, ctx, body.subject_id)
    if not await _may_enter_scores(db, p, ctx, subject.id):
        raise forbidden("Only this subject's teacher can enter its scores.")
    require_draft(await sheet_for(db, ctx))
    if await db.scalar(
        select(SubjectCompletion.id).where(
            SubjectCompletion.arm_id == ctx.arm.id,
            SubjectCompletion.term_id == ctx.term.id,
            SubjectCompletion.subject_id == subject.id,
        )
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Unmark the subject as complete to edit scores."
        )
    components = {c.id: c for c in await components_for(db, ctx.section.id)}
    enrollments = {e.id for e, _ in await enrolled_students(db, ctx)}
    for cell in body.cells:
        component = components.get(cell.component_id)
        if component is None or cell.enrollment_id not in enrollments:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown student or column")
        if cell.value is not None and cell.value > component.max_score:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{component.name} is out of {component.max_score}.",
            )
    existing = {
        (s.enrollment_id, s.component_id): s
        for s in await db.scalars(
            select(Score).where(
                Score.enrollment_id.in_({c.enrollment_id for c in body.cells}),
                Score.subject_id == subject.id,
                Score.term_id == ctx.term.id,
            )
        )
    }
    for cell in body.cells:
        row = existing.get((cell.enrollment_id, cell.component_id))
        if cell.value is None:
            if row is not None:
                await db.delete(row)
        elif row is None:
            db.add(
                Score(
                    school_id=ctx.arm.school_id,
                    enrollment_id=cell.enrollment_id,
                    subject_id=subject.id,
                    term_id=ctx.term.id,
                    component_id=cell.component_id,
                    value=cell.value,
                    entered_by=p.session.user_uuid,
                )
            )
        else:
            row.value, row.entered_by = cell.value, p.session.user_uuid
    return SavedOut(saved=len(body.cells))


@router.put("/completion", response_model=SavedOut)
async def set_completion(body: CompletionIn, p: CurrentPrincipal, db: TenantDB) -> SavedOut:
    ctx = await arm_context(db, body.arm_id)
    subject = await _subject_in_level(db, ctx, body.subject_id)
    if not await _may_enter_scores(db, p, ctx, subject.id):
        raise forbidden("Only this subject's teacher can mark it complete.")
    require_draft(await sheet_for(db, ctx))
    await db.execute(
        delete(SubjectCompletion).where(
            SubjectCompletion.arm_id == ctx.arm.id,
            SubjectCompletion.term_id == ctx.term.id,
            SubjectCompletion.subject_id == subject.id,
        )
    )
    if body.complete:
        db.add(
            SubjectCompletion(
                school_id=ctx.arm.school_id,
                arm_id=ctx.arm.id,
                term_id=ctx.term.id,
                subject_id=subject.id,
                completed_by=p.session.user_uuid,
            )
        )
    return SavedOut(saved=1)


# ---------------------------------------------------------------- ratings, comments, promotion


async def _slot_editable(
    db: TenantDB, p: CurrentPrincipal, ctx: ArmContext, slot: CommentSlot
) -> bool:
    if slot.author_role == CommentAuthor.FORM_TEACHER:
        return is_form_teacher(p, ctx) or await heads_section(db, p, ctx.section.id)
    if slot.author_role == CommentAuthor.COUNSELLOR:
        return Role.COUNSELLOR in p.roles or await heads_section(db, p, ctx.section.id)
    return await heads_section(db, p, ctx.section.id)


@router.get("/report-entry", response_model=ReportEntryOut)
async def report_entry(
    arm_id: Annotated[uuid.UUID, Query()], p: CurrentPrincipal, db: TenantDB
) -> ReportEntryOut:
    ctx = await arm_context(db, arm_id)
    if not await can_view_arm(db, p, ctx):
        raise forbidden()
    sheet = await sheet_for(db, ctx, create=False)
    groups = []
    trait_ids: list[uuid.UUID] = []
    for g in await db.scalars(
        select(TraitGroup).where(TraitGroup.section_id == ctx.section.id).order_by(TraitGroup.sort)
    ):
        traits = list(
            await db.scalars(select(Trait).where(Trait.trait_group_id == g.id).order_by(Trait.sort))
        )
        trait_ids += [t.id for t in traits]
        groups.append(
            TraitGroupOut(name=g.name, traits=[TraitOut(id=t.id, name=t.name) for t in traits])
        )
    slots = list(
        await db.scalars(
            select(CommentSlot)
            .where(CommentSlot.section_id == ctx.section.id)
            .order_by(CommentSlot.sort)
        )
    )
    draft = sheet.status == SheetStatus.DRAFT
    students = await enrolled_students(db, ctx)
    ids = [e.id for e, _ in students]
    ratings: dict[uuid.UUID, dict[str, int]] = {i: {} for i in ids}
    comments: dict[uuid.UUID, dict[str, str]] = {i: {} for i in ids}
    promotions: dict[uuid.UUID, bool] = {}
    if ids:
        for r in await db.scalars(
            select(TraitRating).where(
                TraitRating.enrollment_id.in_(ids), TraitRating.term_id == ctx.term.id
            )
        ):
            ratings[r.enrollment_id][str(r.trait_id)] = r.value
        for c in await db.scalars(
            select(ReportComment).where(
                ReportComment.enrollment_id.in_(ids), ReportComment.term_id == ctx.term.id
            )
        ):
            comments[c.enrollment_id][str(c.comment_slot_id)] = c.text
        for d in await db.scalars(
            select(PromotionDecision).where(
                PromotionDecision.enrollment_id.in_(ids), PromotionDecision.term_id == ctx.term.id
            )
        ):
            promotions[d.enrollment_id] = d.promoted
    head = await heads_section(db, p, ctx.section.id)
    # Comments and ratings stay editable until approval (the principal comments last).
    open_for_notes = sheet.status in (SheetStatus.DRAFT, SheetStatus.SUBMITTED)
    return ReportEntryOut(
        arm_label=ctx.label,
        term_number=ctx.term.number,
        status=sheet.status,
        can_rate=draft and (is_form_teacher(p, ctx) or head),
        can_decide_promotion=open_for_notes and head and ctx.term.number == 3,
        trait_groups=groups,
        slots=[
            SlotOut(
                id=s.id,
                label=s.label,
                author_role=s.author_role,
                editable=open_for_notes and await _slot_editable(db, p, ctx, s),
            )
            for s in slots
        ],
        students=[
            StudentReportEntry(
                enrollment_id=e.id,
                full_name=s.full_name,
                admission_no=s.admission_no,
                ratings=ratings[e.id],
                comments=comments[e.id],
                promoted=promotions.get(e.id),
            )
            for e, s in students
        ],
    )


@router.put("/ratings", response_model=SavedOut)
async def save_ratings(body: RatingsIn, p: CurrentPrincipal, db: TenantDB) -> SavedOut:
    enrollment = await get_or_404(db, Enrollment, body.enrollment_id, "Student")
    ctx = await arm_context(db, enrollment.arm_id)
    if not (is_form_teacher(p, ctx) or await heads_section(db, p, ctx.section.id)):
        raise forbidden("Only the form teacher rates traits.")
    require_draft(await sheet_for(db, ctx), "Ratings")
    valid = set(
        await db.scalars(
            select(Trait.id)
            .join(TraitGroup, TraitGroup.id == Trait.trait_group_id)
            .where(TraitGroup.section_id == ctx.section.id)
        )
    )
    existing = {
        r.trait_id: r
        for r in await db.scalars(
            select(TraitRating).where(
                TraitRating.enrollment_id == enrollment.id, TraitRating.term_id == ctx.term.id
            )
        )
    }
    for item in body.ratings:
        if item.trait_id not in valid:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown trait")
        row = existing.get(item.trait_id)
        if item.value is None:
            if row is not None:
                await db.delete(row)
        elif row is None:
            db.add(
                TraitRating(
                    school_id=ctx.arm.school_id,
                    enrollment_id=enrollment.id,
                    term_id=ctx.term.id,
                    trait_id=item.trait_id,
                    value=item.value,
                )
            )
        else:
            row.value = item.value
    return SavedOut(saved=len(body.ratings))


@router.put("/comments", response_model=SavedOut)
async def save_comment(body: CommentIn, p: CurrentPrincipal, db: TenantDB) -> SavedOut:
    enrollment = await get_or_404(db, Enrollment, body.enrollment_id, "Student")
    ctx = await arm_context(db, enrollment.arm_id)
    slot = await get_or_404(db, CommentSlot, body.slot_id, "Comment box")
    if slot.section_id != ctx.section.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment box not found")
    if not await _slot_editable(db, p, ctx, slot):
        raise forbidden(f"You can't write the “{slot.label}”.")
    sheet = await sheet_for(db, ctx)
    if sheet.status not in (SheetStatus.DRAFT, SheetStatus.SUBMITTED):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Comments are closed once results are approved."
        )
    row = await db.scalar(
        select(ReportComment).where(
            ReportComment.enrollment_id == enrollment.id,
            ReportComment.term_id == ctx.term.id,
            ReportComment.comment_slot_id == slot.id,
        )
    )
    text = body.text.strip()
    if not text:
        if row is not None:
            await db.delete(row)
    elif row is None:
        db.add(
            ReportComment(
                school_id=ctx.arm.school_id,
                enrollment_id=enrollment.id,
                term_id=ctx.term.id,
                comment_slot_id=slot.id,
                text=text,
                author_user_id=p.session.user_uuid,
            )
        )
    else:
        row.text, row.author_user_id = text, p.session.user_uuid
    return SavedOut(saved=1)


@router.put("/promotion", response_model=SavedOut)
async def save_promotion(body: PromotionIn, p: CurrentPrincipal, db: TenantDB) -> SavedOut:
    enrollment = await get_or_404(db, Enrollment, body.enrollment_id, "Student")
    ctx = await arm_context(db, enrollment.arm_id)
    if not await heads_section(db, p, ctx.section.id):
        raise forbidden("Only the principal decides promotion.")
    if ctx.term.number != 3:
        raise HTTPException(status.HTTP_409_CONFLICT, "Promotion is decided in the third term.")
    sheet = await sheet_for(db, ctx)
    if sheet.status not in (SheetStatus.DRAFT, SheetStatus.SUBMITTED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Results are already approved.")
    await db.execute(
        delete(PromotionDecision).where(
            PromotionDecision.enrollment_id == enrollment.id,
            PromotionDecision.term_id == ctx.term.id,
        )
    )
    if body.promoted is not None:
        db.add(
            PromotionDecision(
                school_id=ctx.arm.school_id,
                enrollment_id=enrollment.id,
                term_id=ctx.term.id,
                promoted=body.promoted,
                decided_by=p.session.user_uuid,
            )
        )
    return SavedOut(saved=1)
