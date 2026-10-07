"""Load an arm's data, run the engine, and build report-card snapshots."""

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import House, LevelSubject, Subject, Term
from app.results.access import ArmContext, enrolled_students
from app.results.compute import ArmResult, Band, StudentInput, compute_arm
from app.results.models import (
    AssessmentComponent,
    CommentSlot,
    GradingBand,
    PromotionDecision,
    ReportComment,
    Score,
    SubjectCompletion,
    Trait,
    TraitGroup,
    TraitRating,
)
from app.students.models import Enrollment, Student
from app.tenancy.models import School

TERM_NAMES = {1: "First Term", 2: "Second Term", 3: "Third Term"}


def term_label(term: Term, session_name: str) -> str:
    return f"{TERM_NAMES.get(term.number, f'Term {term.number}')} {session_name}"


async def components_for(db: AsyncSession, section_id: uuid.UUID) -> list[AssessmentComponent]:
    return list(
        await db.scalars(
            select(AssessmentComponent)
            .where(AssessmentComponent.section_id == section_id)
            .order_by(AssessmentComponent.sort)
        )
    )


async def bands_for(db: AsyncSession, section_id: uuid.UUID) -> list[GradingBand]:
    return list(
        await db.scalars(
            select(GradingBand)
            .where(GradingBand.section_id == section_id)
            .order_by(GradingBand.min_score.desc())
        )
    )


async def subjects_for_level(db: AsyncSession, level_id: uuid.UUID) -> list[Subject]:
    return list(
        await db.scalars(
            select(Subject)
            .join(LevelSubject, LevelSubject.subject_id == Subject.id)
            .where(LevelSubject.class_level_id == level_id)
            .order_by(LevelSubject.sort, Subject.name)
        )
    )


@dataclass
class ArmData:
    students: list[tuple[Enrollment, Student]]
    subjects: list[Subject]
    components: list[AssessmentComponent]
    bands: list[GradingBand]
    result: ArmResult
    completions: set[uuid.UUID]
    # (enrollment, subject) → component → value, for the current term
    scores: dict[tuple[uuid.UUID, uuid.UUID], dict[uuid.UUID, Decimal]]


async def load_arm(db: AsyncSession, ctx: ArmContext) -> ArmData:
    students = await enrolled_students(db, ctx)
    subjects = await subjects_for_level(db, ctx.level.id)
    components = await components_for(db, ctx.section.id)
    bands = await bands_for(db, ctx.section.id)
    enrollment_ids = [e.id for e, _ in students]
    subject_ids = {s.id for s in subjects}

    scores: dict[tuple[uuid.UUID, uuid.UUID], dict[uuid.UUID, Decimal]] = defaultdict(dict)
    earlier: dict[uuid.UUID, dict[uuid.UUID, list[Decimal]]] = defaultdict(
        lambda: defaultdict(list)
    )
    earlier_terms = {
        t.id: t.number
        for t in await db.scalars(
            select(Term).where(
                Term.academic_session_id == ctx.session.id, Term.number < ctx.term.number
            )
        )
    }
    if enrollment_ids:
        rows = await db.scalars(
            select(Score).where(
                Score.enrollment_id.in_(enrollment_ids),
                Score.term_id.in_([ctx.term.id, *earlier_terms]),
            )
        )
        earlier_sums: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], Decimal] = defaultdict(Decimal)
        for sc in rows:
            if sc.subject_id not in subject_ids:
                continue
            if sc.term_id == ctx.term.id:
                scores[(sc.enrollment_id, sc.subject_id)][sc.component_id] = sc.value
            else:
                earlier_sums[(sc.enrollment_id, sc.subject_id, sc.term_id)] += sc.value
        for (e, subj, _term), total in sorted(
            earlier_sums.items(), key=lambda kv: earlier_terms[kv[0][2]]
        ):
            earlier[e][subj].append(total)

    inputs = [
        StudentInput(
            enrollment_id=e.id,
            scores={subj: cells for (eid, subj), cells in scores.items() if eid == e.id},
            earlier_totals=dict(earlier.get(e.id, {})),
        )
        for e, _ in students
    ]
    engine_bands = [Band(b.letter, b.descriptor, b.min_score, b.max_score) for b in bands]
    completions = set(
        await db.scalars(
            select(SubjectCompletion.subject_id).where(
                SubjectCompletion.arm_id == ctx.arm.id, SubjectCompletion.term_id == ctx.term.id
            )
        )
    )
    return ArmData(
        students=students,
        subjects=subjects,
        components=components,
        bands=bands,
        result=compute_arm(inputs, engine_bands),
        completions=completions,
        scores=dict(scores),
    )


def missing_for_submission(data: ArmData) -> list[str]:
    """Why the form teacher can't submit yet (empty list = ready)."""
    reasons = [
        f"{s.name} isn't marked complete by its teacher."
        for s in data.subjects
        if s.id not in data.completions
    ]
    needed = {c.id for c in data.components}
    gaps = 0
    for e, _ in data.students:
        for s in data.subjects:
            cells = data.scores.get((e.id, s.id), {})
            if cells and set(cells) != needed:
                gaps += 1
    if gaps:
        reasons.append(f"{gaps} subject score(s) are only partly filled in.")
    if not data.students:
        reasons.append("This class has no students.")
    return reasons


# ---------------------------------------------------------------- snapshot (what a card shows)


def _num(value: Decimal) -> str:
    """40.50 → "40.5", 70.00 → "70": marks print the way teachers write them."""
    return format(value.normalize(), "f")


async def build_snapshot(
    db: AsyncSession,
    school: School,
    ctx: ArmContext,
    data: ArmData,
    enrollment: Enrollment,
    student: Student,
    published_at: datetime,
) -> dict[str, Any]:
    res = data.result.students[enrollment.id]
    cfg = ctx.section.report_config or {}
    house = await db.get(House, student.house_id) if student.house_id else None

    groups = list(
        await db.scalars(
            select(TraitGroup)
            .where(TraitGroup.section_id == ctx.section.id)
            .order_by(TraitGroup.sort)
        )
    )
    ratings = {
        r.trait_id: r.value
        for r in await db.scalars(
            select(TraitRating).where(
                TraitRating.enrollment_id == enrollment.id, TraitRating.term_id == ctx.term.id
            )
        )
    }
    trait_groups = []
    for g in groups:
        traits = await db.scalars(
            select(Trait).where(Trait.trait_group_id == g.id).order_by(Trait.sort)
        )
        trait_groups.append(
            {
                "name": g.name,
                "traits": [{"name": t.name, "value": ratings.get(t.id)} for t in traits],
            }
        )
    slots = list(
        await db.scalars(
            select(CommentSlot)
            .where(CommentSlot.section_id == ctx.section.id)
            .order_by(CommentSlot.sort)
        )
    )
    texts = {
        c.comment_slot_id: c.text
        for c in await db.scalars(
            select(ReportComment).where(
                ReportComment.enrollment_id == enrollment.id, ReportComment.term_id == ctx.term.id
            )
        )
    }
    promotion = await db.scalar(
        select(PromotionDecision.promoted).where(
            PromotionDecision.enrollment_id == enrollment.id,
            PromotionDecision.term_id == ctx.term.id,
        )
    )
    subjects = []
    for s in data.subjects:
        r = res.subjects.get(s.id)
        subjects.append(
            {
                "name": s.name,
                "scores": [
                    _num(r.component_scores[c.id]) if r and c.id in r.component_scores else None
                    for c in data.components
                ],
                "total": _num(r.total) if r else None,
                "grade": r.grade if r else None,
                "descriptor": r.descriptor if r else None,
                "cumulative_average": _num(r.cumulative_average) if r else None,
                "position": r.position if r else None,
            }
        )
    return {
        "school": {
            "name": school.name,
            "motto": school.motto,
            "address": school.address,
            "has_logo": school.logo_content_type is not None,
        },
        "report": {
            "template": cfg.get("template", "standard"),
            "header_lines": cfg.get("header_lines", []),
            "title": cfg.get("title", "Termly Report"),
            "subtitle": cfg.get("subtitle"),
            "show_positions": bool(cfg.get("show_positions", False)),
            "section_name": ctx.section.display_name,
        },
        "student": {
            "name": student.full_name,
            "admission_no": student.admission_no,
            "gender": student.gender.value if student.gender else None,
            "house": house.name if house else None,
            "class_label": ctx.label,
        },
        "term": {
            "number": ctx.term.number,
            "label": term_label(ctx.term, ctx.session.name),
            "name": TERM_NAMES.get(ctx.term.number),
            "session": ctx.session.name,
            "next_term_begins": ctx.term.next_term_begins.isoformat()
            if ctx.term.next_term_begins
            else None,
        },
        "components": [
            {"name": c.name, "short_name": c.short_name, "max_score": c.max_score}
            for c in data.components
        ],
        "subjects": subjects,
        "summary": {
            "total": _num(res.total),
            "subjects_taken": res.subjects_taken,
            "average": f"{res.average:.2f}",
            "position": res.position,
            "number_in_class": data.result.number_in_class,
            "class_average": f"{data.result.class_average:.2f}",
        },
        "grade_key": [
            {"letter": b.letter, "descriptor": b.descriptor, "min": b.min_score, "max": b.max_score}
            for b in data.bands
        ],
        "trait_groups": trait_groups,
        "comments": [{"label": sl.label, "text": texts.get(sl.id, "")} for sl in slots],
        "promotion": promotion if ctx.term.number == 3 else None,
        "published_at": published_at.isoformat(),
    }


def snapshot_hash(data: dict[str, Any]) -> str:
    """Stable SHA-256 of a snapshot; printed (shortened) in the QR verification link."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
