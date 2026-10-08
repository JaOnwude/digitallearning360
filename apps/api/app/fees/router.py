"""Bursar / admin fee management (R19–R24)."""

import asyncio
import csv
import io
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import or_, select

from app.academics.models import AcademicSession, ClassLevel, Term
from app.academics.service import active_session
from app.audit import service as audit
from app.auth.deps import CurrentPrincipal
from app.core.http import client_ip
from app.db.helpers import conflict, get_or_404
from app.fees import invoicing, ledger
from app.fees import service as fees
from app.fees.access import FeeManager, readable_invoice
from app.fees.models import (
    EntryKind,
    EntrySource,
    FeeItem,
    FeeScheduleEntry,
    Invoice,
    LedgerEntry,
    ProofStatus,
    StudentDiscount,
    TransferProof,
)
from app.fees.pdf import invoice_pdf, receipt_pdf
from app.fees.schemas import (
    AdjustmentIn,
    DiscountIn,
    DiscountOut,
    ExemptIn,
    FeeItemIO,
    FeeLevelOut,
    FeeSettingsIO,
    FeeSetupOut,
    FeeSummaryOut,
    FeeTermOut,
    GenerateIn,
    GenerateOut,
    InvoiceDetail,
    InvoicePage,
    OfficePaymentIn,
    ProofOut,
    ProofRejectIn,
    ProofReviewIn,
    ScheduleCell,
)
from app.results.access import current_term
from app.results.service import term_label
from app.students.models import Enrollment, Student
from app.tenancy.deps import CurrentSchool, TenantDB
from app.tenancy.models import School

router = APIRouter(prefix="/api/fees", tags=["fees"])


async def _audit(
    db: TenantDB,
    school: School,
    p: FeeManager,
    request: Request,
    action: str,
    entity: object,
    after: dict | None = None,
) -> None:
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=p.session.user_uuid,
        action=f"fees.{action}",
        entity_type=type(entity).__name__,
        entity_id=getattr(entity, "id", None),
        after=after,
        ip=client_ip(request),
    )


async def _term(db: TenantDB, term_id: uuid.UUID | None) -> Term:
    return await get_or_404(db, Term, term_id, "Term") if term_id else await current_term(db)


# ---------------------------------------------------------------- setup


async def _setup(db: TenantDB, school: School) -> FeeSetupOut:
    session = await active_session(db)
    terms = (
        list(
            await db.scalars(
                select(Term).where(Term.academic_session_id == session.id).order_by(Term.number)
            )
        )
        if session
        else []
    )
    term_ids = [t.id for t in terms]
    return FeeSetupOut(
        items=[
            FeeItemIO(id=i.id, name=i.name, is_optional=i.is_optional)
            for i in await db.scalars(select(FeeItem).order_by(FeeItem.sort, FeeItem.name))
        ],
        levels=[
            FeeLevelOut(id=lv.id, name=lv.name)
            for lv in await db.scalars(
                select(ClassLevel).order_by(ClassLevel.sort, ClassLevel.name)
            )
        ],
        terms=[
            FeeTermOut(id=t.id, label=term_label(t, session.name), is_current=t.is_current)
            for t in terms
        ]
        if session
        else [],
        schedule=[
            ScheduleCell(
                fee_item_id=e.fee_item_id,
                class_level_id=e.class_level_id,
                term_id=e.term_id,
                amount_kobo=e.amount_kobo,
            )
            for e in await db.scalars(
                select(FeeScheduleEntry).where(FeeScheduleEntry.term_id.in_(term_ids))
            )
        ],
        settings=fees.fee_settings(school),
        paystack_configured=fees.online_payment_ready(fees.fee_settings(school)),
    )


@router.get("/setup", response_model=FeeSetupOut)
async def get_setup(_: FeeManager, school: CurrentSchool, db: TenantDB) -> FeeSetupOut:
    return await _setup(db, school)


@router.put("/items", response_model=FeeSetupOut)
async def put_items(
    body: list[FeeItemIO], request: Request, p: FeeManager, school: CurrentSchool, db: TenantDB
) -> FeeSetupOut:
    existing = {i.id: i for i in await db.scalars(select(FeeItem))}
    keep: set[uuid.UUID] = set()
    for sort, item in enumerate(body):
        row = existing.get(item.id) if item.id else None
        if row is None:
            row = FeeItem(school_id=school.id)
            db.add(row)
        row.name, row.is_optional, row.sort = item.name.strip(), item.is_optional, sort
        await db.flush()
        keep.add(row.id)
    for row in existing.values():
        if row.id not in keep:
            await db.delete(row)  # schedule rows cascade; invoice lines keep their text
    await _audit(db, school, p, request, "items_updated", school, {"items": [i.name for i in body]})
    return await _setup(db, school)


@router.put("/schedule", response_model=FeeSetupOut)
async def put_schedule(
    body: list[ScheduleCell], request: Request, p: FeeManager, school: CurrentSchool, db: TenantDB
) -> FeeSetupOut:
    for cell in body:
        await get_or_404(db, FeeItem, cell.fee_item_id, "Fee item")
        await get_or_404(db, ClassLevel, cell.class_level_id, "Class")
        await get_or_404(db, Term, cell.term_id, "Term")
        row = await db.scalar(
            select(FeeScheduleEntry).where(
                FeeScheduleEntry.fee_item_id == cell.fee_item_id,
                FeeScheduleEntry.class_level_id == cell.class_level_id,
                FeeScheduleEntry.term_id == cell.term_id,
            )
        )
        if cell.amount_kobo is None:
            if row is not None:
                await db.delete(row)
        elif row is None:
            db.add(
                FeeScheduleEntry(
                    school_id=school.id,
                    fee_item_id=cell.fee_item_id,
                    class_level_id=cell.class_level_id,
                    term_id=cell.term_id,
                    amount_kobo=cell.amount_kobo,
                )
            )
        else:
            row.amount_kobo = cell.amount_kobo
    await db.flush()
    await _audit(db, school, p, request, "schedule_updated", school, {"cells": len(body)})
    return await _setup(db, school)


@router.put("/settings", response_model=FeeSetupOut)
async def put_settings(
    body: FeeSettingsIO, request: Request, p: FeeManager, school: CurrentSchool, db: TenantDB
) -> FeeSetupOut:
    row = await db.get(School, school.id)
    assert row is not None
    row.settings = {**(row.settings or {}), "fees": body.model_dump()}
    school.settings = row.settings
    await _audit(db, school, p, request, "settings_updated", school, body.model_dump())
    return await _setup(db, school)


# ---------------------------------------------------------------- discounts


async def _discount_outs(db: TenantDB) -> list[DiscountOut]:
    rows = await db.execute(
        select(StudentDiscount, Student, FeeItem.name)
        .join(Student, Student.id == StudentDiscount.student_id)
        .outerjoin(FeeItem, FeeItem.id == StudentDiscount.fee_item_id)
        .order_by(Student.last_name)
    )
    return [
        DiscountOut(
            id=d.id,
            student_id=d.student_id,
            fee_item_id=d.fee_item_id,
            percent=d.percent,
            fixed_kobo=d.fixed_kobo,
            reason=d.reason,
            student_name=s.full_name,
            fee_item_name=name,
        )
        for d, s, name in rows
    ]


@router.get("/discounts", response_model=list[DiscountOut])
async def list_discounts(_: FeeManager, db: TenantDB) -> list[DiscountOut]:
    return await _discount_outs(db)


@router.post("/discounts", response_model=list[DiscountOut], status_code=status.HTTP_201_CREATED)
async def add_discount(
    body: DiscountIn, request: Request, p: FeeManager, school: CurrentSchool, db: TenantDB
) -> list[DiscountOut]:
    if (body.percent is None) == (body.fixed_kobo is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Give either a percentage or a fixed amount."
        )
    await get_or_404(db, Student, body.student_id, "Student")
    if body.fee_item_id:
        await get_or_404(db, FeeItem, body.fee_item_id, "Fee item")
    discount = StudentDiscount(school_id=school.id, **body.model_dump())
    db.add(discount)
    await db.flush()
    await _audit(db, school, p, request, "discount_added", discount, body.model_dump(mode="json"))
    return await _discount_outs(db)


@router.delete("/discounts/{discount_id}", response_model=list[DiscountOut])
async def remove_discount(
    discount_id: uuid.UUID, request: Request, p: FeeManager, school: CurrentSchool, db: TenantDB
) -> list[DiscountOut]:
    discount = await get_or_404(db, StudentDiscount, discount_id, "Discount")
    await _audit(db, school, p, request, "discount_removed", discount)
    await db.delete(discount)
    await db.flush()
    return await _discount_outs(db)


# ---------------------------------------------------------------- invoices


@router.post("/invoices/generate", response_model=GenerateOut)
async def generate_invoices(
    body: GenerateIn, request: Request, p: FeeManager, school: CurrentSchool, db: TenantDB
) -> GenerateOut:
    term = await _term(db, body.term_id)
    if body.class_level_ids:
        for level_id in body.class_level_ids:
            await get_or_404(db, ClassLevel, level_id, "Class")
    result = await invoicing.generate(
        db, school, term, issued_by=p.session.user_uuid, class_level_ids=body.class_level_ids
    )
    await _audit(db, school, p, request, "invoices_generated", term, {"created": result.created})
    return GenerateOut(**result.__dict__)


@router.get("/invoices", response_model=InvoicePage)
async def list_invoices(
    _: FeeManager,
    db: TenantDB,
    term_id: uuid.UUID | None = None,
    arm_id: uuid.UUID | None = None,
    owing: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> InvoicePage:
    term = await _term(db, term_id)
    query = (
        select(Invoice)
        .join(Student, Student.id == Invoice.student_id)
        .join(Enrollment, Enrollment.id == Invoice.enrollment_id)
        .where(Invoice.term_id == term.id)
        .order_by(Student.last_name, Student.first_name)
    )
    if arm_id:
        query = query.where(Enrollment.arm_id == arm_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Student.first_name.ilike(like),
                Student.last_name.ilike(like),
                Student.admission_no.ilike(like),
                Invoice.reference.ilike(like),
            )
        )
    invoices = list(await db.scalars(query))
    rows = await fees.invoice_rows(db, invoices)
    if owing is not None:
        rows = [r for r in rows if (r.balance_kobo > 0) == owing]
    start = (page - 1) * page_size
    return InvoicePage(
        items=rows[start : start + page_size], total=len(rows), page=page, page_size=page_size
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
async def get_invoice(
    invoice_id: uuid.UUID, p: CurrentPrincipal, school: CurrentSchool, db: TenantDB
) -> InvoiceDetail:
    """Fee managers see any invoice; parents/students their own."""
    return await fees.invoice_detail(db, school, await readable_invoice(db, p, invoice_id))


@router.post("/invoices/{invoice_id}/adjustments", response_model=InvoiceDetail)
async def add_adjustment(
    invoice_id: uuid.UUID,
    body: AdjustmentIn,
    request: Request,
    p: FeeManager,
    school: CurrentSchool,
    db: TenantDB,
) -> InvoiceDetail:
    """A waiver (negative) or extra charge (positive), with a reason. Lines never change."""
    if body.amount_kobo == 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter an amount other than zero."
        )
    invoice = await ledger.lock_invoice(db, invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    entry = await ledger.record(
        db,
        invoice,
        kind=EntryKind.ADJUSTMENT,
        source=EntrySource.MANUAL,
        amount_kobo=body.amount_kobo,
        recorded_by=p.session.user_uuid,
        note=body.note,
    )
    await _audit(
        db,
        school,
        p,
        request,
        "adjustment",
        entry,
        {"invoice": invoice.reference, **body.model_dump()},
    )
    await fees.notify_invoice(db, invoice)
    return await fees.invoice_detail(db, school, invoice)


@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceDetail)
async def record_office_payment(
    invoice_id: uuid.UUID,
    body: OfficePaymentIn,
    request: Request,
    p: FeeManager,
    school: CurrentSchool,
    db: TenantDB,
) -> InvoiceDetail:
    """Cash (or other) money received at the school office, with a receipt."""
    if body.source in (EntrySource.PAYSTACK, EntrySource.TRANSFER):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Online and transfer payments are recorded automatically.",
        )
    invoice = await ledger.lock_invoice(db, invoice_id)
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    entry = await ledger.record(
        db,
        invoice,
        kind=EntryKind.PAYMENT,
        source=body.source,
        amount_kobo=body.amount_kobo,
        recorded_by=p.session.user_uuid,
        note=body.note or "Paid at the school office",
    )
    await _audit(
        db,
        school,
        p,
        request,
        "office_payment",
        entry,
        {"invoice": invoice.reference, **body.model_dump(mode="json")},
    )
    await fees.notify_invoice(db, invoice)
    return await fees.invoice_detail(db, school, invoice)


@router.put("/invoices/{invoice_id}/results-exempt", response_model=InvoiceDetail)
async def set_results_exempt(
    invoice_id: uuid.UUID,
    body: ExemptIn,
    request: Request,
    p: FeeManager,
    school: CurrentSchool,
    db: TenantDB,
) -> InvoiceDetail:
    """R18: let a student's results show despite a balance (e.g. agreed payment plan)."""
    invoice = await get_or_404(db, Invoice, invoice_id, "Invoice")
    invoice.results_exempt = body.exempt
    await _audit(db, school, p, request, "results_exempt", invoice, body.model_dump())
    await fees.notify_invoice(db, invoice)
    return await fees.invoice_detail(db, school, invoice)


# ---------------------------------------------------------------- PDFs


async def _logo(db: TenantDB, school: School) -> bytes | None:
    return await db.scalar(select(School.logo).where(School.id == school.id))


def _pdf(content: bytes, name: str) -> Response:
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/invoices/{invoice_id}/document.pdf", response_class=Response)
async def invoice_document(
    invoice_id: uuid.UUID, p: CurrentPrincipal, school: CurrentSchool, db: TenantDB
) -> Response:
    detail = await fees.invoice_detail(db, school, await readable_invoice(db, p, invoice_id))
    logo = await _logo(db, school)
    content = await asyncio.to_thread(  # CPU-bound: keep the event loop free
        invoice_pdf, detail, school_name=school.name, address=school.address, logo=logo
    )
    return _pdf(content, f"invoice-{detail.reference}.pdf")


@router.get("/receipts/{entry_id}.pdf", response_class=Response)
async def receipt_document(
    entry_id: uuid.UUID, p: CurrentPrincipal, school: CurrentSchool, db: TenantDB
) -> Response:
    entry = await get_or_404(db, LedgerEntry, entry_id, "Receipt")
    detail = await fees.invoice_detail(db, school, await readable_invoice(db, p, entry.invoice_id))
    if entry.kind != EntryKind.PAYMENT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found")
    [out] = [e for e in detail.entries if e.id == entry.id]
    logo = await _logo(db, school)
    content = await asyncio.to_thread(
        receipt_pdf, detail, out, school_name=school.name, address=school.address, logo=logo
    )
    return _pdf(content, f"receipt-{entry.receipt_no}.pdf")


# ---------------------------------------------------------------- transfer proofs (bursar side)


@router.get("/proofs", response_model=list[ProofOut])
async def list_proofs(
    _: FeeManager,
    db: TenantDB,
    status_: Annotated[ProofStatus | None, Query(alias="status")] = ProofStatus.PENDING,
) -> list[ProofOut]:
    query = select(TransferProof).order_by(TransferProof.created_at)
    if status_ is not None:
        query = query.where(TransferProof.status == status_)
    return await fees.proof_outs(db, list(await db.scalars(query.limit(500))))


@router.get("/proofs/{proof_id}/file", response_class=Response)
async def proof_file(proof_id: uuid.UUID, p: CurrentPrincipal, db: TenantDB) -> Response:
    proof = await get_or_404(db, TransferProof, proof_id, "Proof")
    await readable_invoice(db, p, proof.invoice_id)  # bursar, or the family that uploaded it
    content = await db.scalar(select(TransferProof.file).where(TransferProof.id == proof.id))
    if not content:  # deleted under the retention policy (fees/retention.py)
        raise HTTPException(status.HTTP_410_GONE, "This receipt image was deleted after a year.")
    return Response(
        content,
        media_type=proof.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            # A parent's upload must never run script on the school's origin.
            "Content-Security-Policy": "sandbox; default-src 'none'; img-src 'self'",
        },
    )


async def _reviewable(db: TenantDB, proof_id: uuid.UUID) -> TransferProof:
    proof = await db.scalar(
        select(TransferProof).where(TransferProof.id == proof_id).with_for_update()
    )
    if proof is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proof not found")
    if proof.status != ProofStatus.PENDING:
        raise conflict(f"This proof was already {proof.status.value}.")
    return proof


@router.post("/proofs/{proof_id}/confirm", response_model=ProofOut)
async def confirm_proof(
    proof_id: uuid.UUID,
    body: ProofReviewIn,
    request: Request,
    p: FeeManager,
    school: CurrentSchool,
    db: TenantDB,
) -> ProofOut:
    """Record the amount that actually reached the school's account (AC9)."""
    proof = await _reviewable(db, proof_id)
    entry = await fees.confirm_proof(
        db, proof, amount_kobo=body.amount_kobo, note=body.note, reviewer=p.session.user_uuid
    )
    await _audit(
        db,
        school,
        p,
        request,
        "proof_confirmed",
        proof,
        {"amount_kobo": body.amount_kobo, "entry": str(entry.id)},
    )
    return (await fees.proof_outs(db, [proof]))[0]


@router.post("/proofs/{proof_id}/reject", response_model=ProofOut)
async def reject_proof(
    proof_id: uuid.UUID,
    body: ProofRejectIn,
    request: Request,
    p: FeeManager,
    school: CurrentSchool,
    db: TenantDB,
) -> ProofOut:
    proof = await _reviewable(db, proof_id)
    proof.status, proof.review_note = ProofStatus.REJECTED, body.reason
    proof.reviewed_by, proof.reviewed_at = p.session.user_uuid, datetime.now(UTC)
    await _audit(db, school, p, request, "proof_rejected", proof, {"reason": body.reason})
    invoice = await db.get(Invoice, proof.invoice_id)
    assert invoice is not None
    await fees.notify_invoice(db, invoice, "proof.reviewed")
    return (await fees.proof_outs(db, [proof]))[0]


# ---------------------------------------------------------------- dashboard + exports (R24)


@router.get("/summary", response_model=FeeSummaryOut)
async def fee_summary(
    _: FeeManager, db: TenantDB, term_id: uuid.UUID | None = None
) -> FeeSummaryOut:
    term = await _term(db, term_id)
    session = await db.get(AcademicSession, term.academic_session_id)
    assert session is not None
    return await fees.summary(db, term, session.name)


def _ngn(kobo: int) -> Decimal:
    """Exact naira for spreadsheets: 4500000 → 45000.00 (never a float)."""
    return (Decimal(kobo) / 100).quantize(Decimal("0.01"))


def _safe_cell(value: object) -> object:
    """Stop spreadsheet formula injection: a name like `=HYPERLINK(...)` is text, not a formula."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _csv(rows: Sequence[Sequence[object]], name: str) -> Response:
    buf = io.StringIO()
    csv.writer(buf).writerows([_safe_cell(v) for v in row] for row in rows)
    return Response(
        "﻿" + buf.getvalue(),
        media_type="text/csv",  # BOM so Excel reads ₦ correctly
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/exports/debtors.csv", response_class=Response)
async def export_debtors(_: FeeManager, db: TenantDB, term_id: uuid.UUID | None = None) -> Response:
    term = await _term(db, term_id)
    rows = await fees.invoice_rows(
        db, list(await db.scalars(select(Invoice).where(Invoice.term_id == term.id)))
    )
    owing = sorted(
        (r for r in rows if r.balance_kobo > 0), key=lambda r: (r.class_label or "", r.student_name)
    )
    return _csv(
        [
            [
                "Invoice",
                "Student",
                "Admission no.",
                "Class",
                "Fees (NGN)",
                "Waivers / charges (NGN)",
                "Paid (NGN)",
                "Balance (NGN)",
            ]
        ]
        + [
            [
                r.reference,
                r.student_name,
                r.admission_no,
                r.class_label or "",
                _ngn(r.total_kobo),
                # balance = fees + adjustments - payments (+ refunds), so the columns add up
                _ngn(r.balance_kobo - r.total_kobo + r.paid_kobo),
                _ngn(r.paid_kobo),
                _ngn(r.balance_kobo),
            ]
            for r in owing
        ],
        "debtors.csv",
    )


@router.get("/exports/payments.csv", response_class=Response)
async def export_payments(
    _: FeeManager, db: TenantDB, term_id: uuid.UUID | None = None
) -> Response:
    term = await _term(db, term_id)
    rows = await db.execute(
        select(LedgerEntry, Invoice.reference, Student)
        .join(Invoice, Invoice.id == LedgerEntry.invoice_id)
        .join(Student, Student.id == Invoice.student_id)
        .where(Invoice.term_id == term.id)
        .order_by(LedgerEntry.created_at)
    )
    return _csv(
        [["Date", "Receipt", "Invoice", "Student", "Kind", "Method", "Amount (NGN)", "Note"]]
        + [
            [
                f"{e.created_at:%Y-%m-%d %H:%M}",
                e.receipt_no or "",
                ref,
                s.full_name,
                e.kind.value,
                e.source.value,
                _ngn(e.amount_kobo),
                e.note or "",
            ]
            for e, ref, s in rows
        ],
        "payments.csv",
    )
