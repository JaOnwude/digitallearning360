"""Per-section results setup: score columns, grade bands, traits, comment slots (R12–R17)."""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import Section
from app.results.models import (
    AssessmentComponent,
    CommentAuthor,
    CommentSlot,
    GradingBand,
    Score,
    Trait,
    TraitGroup,
)


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    short_name: str
    max_score: int
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class BandSpec:
    letter: str
    descriptor: str
    min_score: int
    max_score: int


def _invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def validate_components(components: list[ComponentSpec]) -> None:
    if not components:
        raise _invalid("Add at least one score column.")
    names = [c.name.strip().lower() for c in components]
    if len(set(names)) != len(names):
        raise _invalid("Each score column needs a different name.")
    total = sum(c.max_score for c in components)
    if total != 100:
        raise _invalid(f"Score columns must add up to 100 (they add up to {total}).")


def validate_bands(bands: list[BandSpec]) -> None:
    """Bands must cover every whole mark from 0 to 100 exactly once."""
    if not bands:
        raise _invalid("Add at least one grade.")
    letters = [b.letter.strip().upper() for b in bands]
    if len(set(letters)) != len(letters):
        raise _invalid("Each grade needs a different letter.")
    expected = 0
    for b in sorted(bands, key=lambda b: b.min_score):
        if b.min_score > b.max_score:
            raise _invalid(f"Grade {b.letter}: the lowest mark is above the highest.")
        if b.min_score != expected:
            gap_or_overlap = "gap" if b.min_score > expected else "overlap"
            raise _invalid(f"Grades have a {gap_or_overlap} at {expected}. Bands must cover 0–100.")
        expected = b.max_score + 1
    if expected != 101:
        raise _invalid(f"Grades stop at {expected - 1}. The top grade must reach 100.")


async def set_components(
    db: AsyncSession, school_id: uuid.UUID, section: Section, specs: list[ComponentSpec]
) -> None:
    """Replace a section's score columns, keeping ids (and scores) for columns that stay."""
    validate_components(specs)
    existing = {
        c.id: c
        for c in await db.scalars(
            select(AssessmentComponent).where(AssessmentComponent.section_id == section.id)
        )
    }
    by_name = {c.name.lower(): c for c in existing.values()}
    keep: set[uuid.UUID] = set()
    for sort, spec in enumerate(specs):
        row = (spec.id and existing.get(spec.id)) or by_name.get(spec.name.strip().lower())
        if row is None:
            row = AssessmentComponent(school_id=school_id, section_id=section.id)
            db.add(row)
        row.name, row.short_name = spec.name.strip(), spec.short_name.strip()
        row.max_score, row.sort = spec.max_score, sort
        await db.flush()
        keep.add(row.id)
    for row in existing.values():
        if row.id in keep:
            continue
        used = await db.scalar(
            select(func.count()).select_from(Score).where(Score.component_id == row.id)
        )
        if used:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"“{row.name}” already has scores, so it can't be removed.",
            )
        await db.delete(row)
    await db.flush()


async def set_bands(
    db: AsyncSession, school_id: uuid.UUID, section: Section, specs: list[BandSpec]
) -> None:
    """Replace a section's grade bands. Grades are recomputed from scores, so this is safe."""
    validate_bands(specs)
    for row in await db.scalars(select(GradingBand).where(GradingBand.section_id == section.id)):
        await db.delete(row)
    await db.flush()
    for sort, b in enumerate(sorted(specs, key=lambda b: -b.min_score)):
        db.add(
            GradingBand(
                school_id=school_id,
                section_id=section.id,
                letter=b.letter.strip().upper(),
                descriptor=b.descriptor.strip(),
                min_score=b.min_score,
                max_score=b.max_score,
                sort=sort,
            )
        )
    await db.flush()


async def set_traits(
    db: AsyncSession, school_id: uuid.UUID, section: Section, groups: list[tuple[str, list[str]]]
) -> None:
    """Upsert trait groups and traits by name. Traits not listed are removed (with ratings)."""
    groups_existing = {
        g.name: g
        for g in await db.scalars(select(TraitGroup).where(TraitGroup.section_id == section.id))
    }
    keep_groups: set[uuid.UUID] = set()
    for g_sort, (g_name, trait_names) in enumerate(groups):
        group = groups_existing.get(g_name)
        if group is None:
            group = TraitGroup(school_id=school_id, section_id=section.id, name=g_name)
            db.add(group)
            await db.flush()
        group.sort = g_sort
        keep_groups.add(group.id)
        traits_existing = {
            t.name: t
            for t in await db.scalars(select(Trait).where(Trait.trait_group_id == group.id))
        }
        for t_sort, t_name in enumerate(trait_names):
            trait = traits_existing.pop(t_name, None)
            if trait is None:
                db.add(
                    Trait(school_id=school_id, trait_group_id=group.id, name=t_name, sort=t_sort)
                )
            else:
                trait.sort = t_sort
        for leftover in traits_existing.values():
            await db.delete(leftover)
    for group in groups_existing.values():
        if group.id not in keep_groups:
            await db.delete(group)
    await db.flush()


async def set_comment_slots(
    db: AsyncSession,
    school_id: uuid.UUID,
    section: Section,
    slots: list[tuple[str, CommentAuthor]],
) -> None:
    existing = {
        s.label: s
        for s in await db.scalars(select(CommentSlot).where(CommentSlot.section_id == section.id))
    }
    for sort, (label, author) in enumerate(slots):
        slot = existing.pop(label, None)
        if slot is None:
            slot = CommentSlot(school_id=school_id, section_id=section.id, label=label)
            db.add(slot)
        slot.author_role, slot.sort = author, sort
    for leftover in existing.values():
        await db.delete(leftover)
    await db.flush()


# ---------------------------------------------------------------- platform defaults (spec R12–R13)

DEFAULT_COMPONENTS = [
    ComponentSpec("1st Continuous Assessment", "CA1", 20),
    ComponentSpec("2nd Continuous Assessment", "CA2", 20),
    ComponentSpec("Examination", "Exam", 60),
]
WAEC_BANDS = [
    BandSpec("A1", "Excellent", 75, 100),
    BandSpec("B2", "Very Good", 70, 74),
    BandSpec("B3", "Good", 65, 69),
    BandSpec("C4", "Credit", 60, 64),
    BandSpec("C5", "Credit", 55, 59),
    BandSpec("C6", "Credit", 50, 54),
    BandSpec("D7", "Pass", 45, 49),
    BandSpec("E8", "Pass", 40, 44),
    BandSpec("F9", "Fail", 0, 39),
]
BASIC_BANDS = [
    BandSpec("A", "Excellent", 70, 100),
    BandSpec("B", "Very Good", 60, 69),
    BandSpec("C", "Good", 50, 59),
    BandSpec("D", "Fair", 45, 49),
    BandSpec("E", "Pass", 40, 44),
    BandSpec("F", "Fail", 0, 39),
]
DEFAULT_SLOTS = [
    ("Class Teacher's Comment", CommentAuthor.FORM_TEACHER),
    ("Head's Comment", CommentAuthor.SECTION_HEAD),
]


def default_bands(kind: str) -> list[BandSpec]:
    return WAEC_BANDS if kind == "senior_secondary" else BASIC_BANDS
