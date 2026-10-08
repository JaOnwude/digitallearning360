"""Issuing term invoices from the fee schedule (R19, R20)."""

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import AcademicSession, Arm, Term
from app.fees.models import (
    FeeItem,
    FeeScheduleEntry,
    Invoice,
    InvoiceCounter,
    InvoiceLine,
    StudentDiscount,
)
from app.students.models import Enrollment, Student, StudentStatus
from app.tenancy.models import School


def school_code(school: School) -> str:
    code = (school.settings or {}).get("invoice_prefix") or school.slug
    return "".join(ch for ch in code.upper() if ch.isalnum())[:12] or "SCH"


def session_code(name: str) -> str:
    """ "2026/2027" → "2627"."""
    parts = name.split("/")
    return "".join(p[-2:] for p in parts) if len(parts) == 2 else name.replace("/", "")


async def next_reference(
    db: AsyncSession, school: School, term: Term, session: AcademicSession
) -> str:
    """`PROGRESS-2627-T1-00042`: per-term sequence taken under a row lock (no duplicates)."""
    await db.execute(
        insert(InvoiceCounter)
        .values(id=uuid.uuid4(), school_id=school.id, term_id=term.id, last_seq=0)
        .on_conflict_do_nothing(constraint="uq_invoice_counters_term")
    )
    counter = await db.scalar(
        select(InvoiceCounter).where(InvoiceCounter.term_id == term.id).with_for_update()
    )
    assert counter is not None
    counter.last_seq += 1
    await db.flush()
    return (
        f"{school_code(school)}-{session_code(session.name)}-T{term.number}-{counter.last_seq:05d}"
    )


@dataclass
class GenerationResult:
    created: int
    already_invoiced: int
    no_schedule: int


def _discount_lines(
    discounts: list[StudentDiscount], lines: list[InvoiceLine]
) -> list[tuple[str, int]]:
    """Negative lines for each discount, never taking an item (or the invoice) below zero."""
    out: list[tuple[str, int]] = []
    for d in discounts:
        base = (
            sum(line.amount_kobo for line in lines if line.fee_item_id == d.fee_item_id)
            if d.fee_item_id
            else sum(line.amount_kobo for line in lines)
        )
        if base <= 0:
            continue
        amount = base * d.percent // 100 if d.percent is not None else min(d.fixed_kobo or 0, base)
        if amount > 0:
            out.append((f"Discount: {d.reason}", -amount))
    return out


async def generate(
    db: AsyncSession,
    school: School,
    term: Term,
    *,
    issued_by: uuid.UUID | None,
    class_level_ids: list[uuid.UUID] | None = None,
) -> GenerationResult:
    """One invoice per active, enrolled student whose class has fees this term.

    Idempotent: students who already have an invoice for the term are skipped.
    """
    session = await db.get(AcademicSession, term.academic_session_id)
    assert session is not None
    schedule: dict[uuid.UUID, list[tuple[FeeItem, int]]] = defaultdict(list)
    for entry, item in await db.execute(
        select(FeeScheduleEntry, FeeItem)
        .join(FeeItem, FeeItem.id == FeeScheduleEntry.fee_item_id)
        .where(FeeScheduleEntry.term_id == term.id, FeeItem.is_optional.is_(False))
        .order_by(FeeItem.sort, FeeItem.name)
    ):
        schedule[entry.class_level_id].append((item, entry.amount_kobo))

    query = (
        select(Enrollment, Arm.class_level_id)
        .join(Arm, Arm.id == Enrollment.arm_id)
        .join(Student, Student.id == Enrollment.student_id)
        .where(
            Enrollment.academic_session_id == session.id,
            Student.status == StudentStatus.ACTIVE,
        )
        .order_by(Arm.class_level_id, Student.last_name, Student.first_name)
    )
    if class_level_ids:
        query = query.where(Arm.class_level_id.in_(class_level_ids))
    enrollments = (await db.execute(query)).all()

    invoiced = set(await db.scalars(select(Invoice.student_id).where(Invoice.term_id == term.id)))
    discounts: dict[uuid.UUID, list[StudentDiscount]] = defaultdict(list)
    for d in await db.scalars(select(StudentDiscount)):
        discounts[d.student_id].append(d)

    result = GenerationResult(0, 0, 0)
    for enrollment, level_id in enrollments:
        if enrollment.student_id in invoiced:
            result.already_invoiced += 1
            continue
        items = schedule.get(level_id)
        if not items:
            result.no_schedule += 1
            continue
        lines = [
            InvoiceLine(
                school_id=school.id,
                fee_item_id=item.id,
                description=item.name,
                amount_kobo=amount,
                sort=i,
            )
            for i, (item, amount) in enumerate(items)
        ]
        for j, (desc, amount) in enumerate(
            _discount_lines(discounts[enrollment.student_id], lines)
        ):
            lines.append(
                InvoiceLine(
                    school_id=school.id,
                    fee_item_id=None,
                    description=desc,
                    amount_kobo=amount,
                    sort=100 + j,
                )
            )
        invoice = Invoice(
            school_id=school.id,
            student_id=enrollment.student_id,
            enrollment_id=enrollment.id,
            term_id=term.id,
            reference=await next_reference(db, school, term, session),
            total_kobo=max(0, sum(line.amount_kobo for line in lines)),
            due_on=term.starts_on,
            issued_by=issued_by,
        )
        db.add(invoice)
        await db.flush()
        for line in lines:
            line.invoice_id = invoice.id
            db.add(line)
        result.created += 1
    await db.flush()
    return result
