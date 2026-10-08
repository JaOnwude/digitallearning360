"""Fee operations that move money or summarise it. Callers pass a tenant session."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import AcademicSession, Arm, ClassLevel, Term
from app.audit import service as audit
from app.auth.models import Membership, Role
from app.core.config import get_settings
from app.fees import ledger
from app.fees.models import (
    EntryKind,
    EntrySource,
    IntentStatus,
    Invoice,
    InvoiceLine,
    LedgerEntry,
    PaymentIntent,
    ProofStatus,
    TransferProof,
)
from app.fees.paystack import Verification
from app.fees.schemas import (
    BankDetails,
    ClassSummary,
    EntryOut,
    FeeSettingsIO,
    FeeSummaryOut,
    InvoiceDetail,
    InvoiceRow,
    LineOut,
    ProofOut,
)
from app.notifications import events
from app.results.service import term_label
from app.students.models import Enrollment, Guardian, Student, StudentGuardian
from app.tenancy.deps import after_commit
from app.tenancy.models import School

# ---------------------------------------------------------------- settings


def fee_settings(school: School) -> FeeSettingsIO:
    s = (school.settings or {}).get("fees", {})
    return FeeSettingsIO.model_validate(s)


def bank_details(school: School) -> BankDetails:
    s = fee_settings(school)
    return BankDetails(
        bank_name=s.bank_name, account_name=s.account_name, account_number=s.account_number
    )


# ---------------------------------------------------------------- reading invoices


async def _term_labels(db: AsyncSession, term_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not term_ids:
        return {}
    rows = await db.execute(
        select(Term, AcademicSession.name)
        .join(AcademicSession, AcademicSession.id == Term.academic_session_id)
        .where(Term.id.in_(term_ids))
    )
    return {t.id: term_label(t, name) for t, name in rows}


async def invoice_rows(db: AsyncSession, invoices: list[Invoice]) -> list[InvoiceRow]:
    if not invoices:
        return []
    ids = [i.id for i in invoices]
    bal = await ledger.balances(db, ids)
    paid = dict(
        (inv, int(total))
        for inv, total in await db.execute(
            select(LedgerEntry.invoice_id, func.sum(LedgerEntry.amount_kobo))
            .where(LedgerEntry.invoice_id.in_(ids), LedgerEntry.kind == EntryKind.PAYMENT)
            .group_by(LedgerEntry.invoice_id)
        )
    )
    pending = dict(
        (inv, int(n))
        for inv, n in await db.execute(
            select(TransferProof.invoice_id, func.count())
            .where(TransferProof.invoice_id.in_(ids), TransferProof.status == ProofStatus.PENDING)
            .group_by(TransferProof.invoice_id)
        )
    )
    students = {
        s.id: s
        for s in await db.scalars(
            select(Student).where(Student.id.in_({i.student_id for i in invoices}))
        )
    }
    classes = {
        e_id: f"{lvl} {arm}"
        for e_id, lvl, arm in await db.execute(
            select(Enrollment.id, ClassLevel.name, Arm.name)
            .join(Arm, Arm.id == Enrollment.arm_id)
            .join(ClassLevel, ClassLevel.id == Arm.class_level_id)
            .where(Enrollment.id.in_({i.enrollment_id for i in invoices}))
        )
    }
    labels = await _term_labels(db, {i.term_id for i in invoices})
    return [
        InvoiceRow(
            id=i.id,
            reference=i.reference,
            student_id=i.student_id,
            student_name=students[i.student_id].full_name,
            admission_no=students[i.student_id].admission_no,
            class_label=classes.get(i.enrollment_id),
            term_label=labels.get(i.term_id, ""),
            total_kobo=i.total_kobo,
            paid_kobo=paid.get(i.id, 0),
            balance_kobo=bal.get(i.id, i.total_kobo),
            pending_proofs=pending.get(i.id, 0),
        )
        for i in invoices
    ]


async def proof_outs(db: AsyncSession, proofs: list[TransferProof]) -> list[ProofOut]:
    if not proofs:
        return []
    inv = {
        i.id: i
        for i in await db.scalars(
            select(Invoice).where(Invoice.id.in_({p.invoice_id for p in proofs}))
        )
    }
    names = {
        s.id: s.full_name
        for s in await db.scalars(
            select(Student).where(Student.id.in_({i.student_id for i in inv.values()}))
        )
    }
    return [
        ProofOut(
            id=p.id,
            invoice_id=p.invoice_id,
            invoice_reference=inv[p.invoice_id].reference,
            student_name=names[inv[p.invoice_id].student_id],
            claimed_amount_kobo=p.claimed_amount_kobo,
            bank_reference=p.bank_reference,
            paid_on=p.paid_on,
            content_type=p.content_type,
            status=p.status,
            confirmed_amount_kobo=p.confirmed_amount_kobo,
            review_note=p.review_note,
            duplicate_of=p.duplicate_of,
            created_at=p.created_at,
        )
        for p in proofs
    ]


async def invoice_detail(db: AsyncSession, school: School, invoice: Invoice) -> InvoiceDetail:
    [row] = await invoice_rows(db, [invoice])
    lines = await db.scalars(
        select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id).order_by(InvoiceLine.sort)
    )
    entries = await db.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.invoice_id == invoice.id)
        .order_by(LedgerEntry.created_at)
    )
    proofs = list(
        await db.scalars(
            select(TransferProof)
            .where(TransferProof.invoice_id == invoice.id)
            .order_by(TransferProof.created_at)
        )
    )
    settings = fee_settings(school)
    return InvoiceDetail(
        **row.model_dump(),
        due_on=invoice.due_on,
        results_exempt=invoice.results_exempt,
        lines=[
            LineOut(description=line.description, amount_kobo=line.amount_kobo) for line in lines
        ],
        entries=[
            EntryOut(
                id=e.id,
                kind=e.kind,
                source=e.source,
                amount_kobo=e.amount_kobo,
                receipt_no=e.receipt_no,
                note=e.note,
                created_at=e.created_at,
            )
            for e in entries
        ],
        proofs=await proof_outs(db, proofs),
        bank=bank_details(school),
        can_pay_online=row.balance_kobo > 0 and online_payment_ready(settings),
    )


def online_payment_ready(settings: FeeSettingsIO) -> bool:
    cfg = get_settings()
    if cfg.paystack_secret_key is None:
        return False
    # Development may run without a subaccount (money stays in the test account).
    return bool(settings.paystack_subaccount_code) or not cfg.is_deployed


# ---------------------------------------------------------------- notifying people


async def notify_invoice(
    db: AsyncSession, invoice: Invoice, event: str = "invoice.updated"
) -> None:
    """Tell the family (and bursars) an invoice changed, once the change has committed."""
    parents = await db.scalars(
        select(Guardian.user_id)
        .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
        .where(StudentGuardian.student_id == invoice.student_id, Guardian.user_id.is_not(None))
    )
    student_user = await db.scalar(select(Student.user_id).where(Student.id == invoice.student_id))
    channels = [events.user_channel(u) for u in parents if u]
    if student_user:
        channels.append(events.user_channel(student_user))
    channels.append(events.fees_channel(invoice.school_id))
    data = {"invoice_id": str(invoice.id)}
    after_commit(db, lambda: events.publish(channels, event, data))


# ---------------------------------------------------------------- Paystack


async def apply_paystack(
    db: AsyncSession, reference: str, verification: Verification, *, via: str
) -> tuple[Invoice | None, LedgerEntry | None]:
    """Apply a verified Paystack transaction to its invoice, exactly once (R22, AC7).

    Safe to call any number of times, concurrently, from the webhook and the browser's
    verify call: the invoice row lock serialises them, the intent status short-circuits
    repeats, and the unique external_ref is the last line of defence.
    """
    intent = await db.scalar(select(PaymentIntent).where(PaymentIntent.reference == reference))
    if intent is None:
        return None, None
    invoice = await ledger.lock_invoice(db, intent.invoice_id)
    assert invoice is not None
    await db.refresh(intent)  # re-read under the lock: another request may have applied it
    external_ref = f"paystack:{reference}"
    if intent.status == IntentStatus.SUCCEEDED:
        return invoice, await ledger.entry_by_ref(db, external_ref)
    if not verification.success or verification.currency != "NGN":
        intent.status, intent.gateway_response = IntentStatus.FAILED, _trim(verification.raw)
        return invoice, None
    try:
        async with db.begin_nested():
            # Record what Paystack says was actually paid; flag (audit) if it differs.
            entry = await ledger.record(
                db,
                invoice,
                kind=EntryKind.PAYMENT,
                source=EntrySource.PAYSTACK,
                amount_kobo=verification.amount_kobo,
                recorded_by=intent.payer_user_id,
                external_ref=external_ref,
                note="Paid online (Paystack)",
            )
    except IntegrityError:
        return invoice, await ledger.entry_by_ref(db, external_ref)
    intent.status, intent.gateway_response = IntentStatus.SUCCEEDED, _trim(verification.raw)
    await audit.record(
        db,
        school_id=invoice.school_id,
        actor_user_id=intent.payer_user_id,
        action="fees.paystack_payment",
        entity_type="Invoice",
        entity_id=invoice.id,
        after={
            "reference": reference,
            "amount_kobo": verification.amount_kobo,
            "expected_kobo": intent.amount_kobo,
            "mismatch": verification.amount_kobo != intent.amount_kobo,
            "via": via,
        },
    )
    await notify_invoice(db, invoice)
    return invoice, entry


def _trim(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep what's useful for support; drop card/customer details."""
    keep = (
        "reference",
        "status",
        "amount",
        "currency",
        "channel",
        "paid_at",
        "gateway_response",
        "fees",
    )
    return {k: raw.get(k) for k in keep}


# ---------------------------------------------------------------- transfer proofs


async def confirm_proof(
    db: AsyncSession,
    proof: TransferProof,
    *,
    amount_kobo: int,
    note: str | None,
    reviewer: uuid.UUID,
) -> LedgerEntry:
    invoice = await ledger.lock_invoice(db, proof.invoice_id)
    assert invoice is not None
    entry = await ledger.record(
        db,
        invoice,
        kind=EntryKind.PAYMENT,
        source=EntrySource.TRANSFER,
        amount_kobo=amount_kobo,
        recorded_by=reviewer,
        external_ref=f"proof:{proof.id}",
        note=note
        or (f"Bank transfer {proof.bank_reference}" if proof.bank_reference else "Bank transfer"),
    )
    proof.status = ProofStatus.CONFIRMED
    proof.confirmed_amount_kobo = amount_kobo
    proof.review_note = note
    proof.reviewed_by = reviewer
    proof.reviewed_at = datetime.now(UTC)
    await notify_invoice(db, invoice, "proof.reviewed")
    return entry


# ---------------------------------------------------------------- summary (R24)


async def summary(db: AsyncSession, term: Term, session_name: str) -> FeeSummaryOut:
    invoices = list(await db.scalars(select(Invoice).where(Invoice.term_id == term.id)))
    bal = await ledger.balances(db, [i.id for i in invoices])
    paid = defaultdict(int)
    for inv, total in await db.execute(
        select(LedgerEntry.invoice_id, func.sum(LedgerEntry.amount_kobo))
        .join(Invoice, Invoice.id == LedgerEntry.invoice_id)
        .where(Invoice.term_id == term.id, LedgerEntry.kind == EntryKind.PAYMENT)
        .group_by(LedgerEntry.invoice_id)
    ):
        paid[inv] = int(total)
    labels = {
        e_id: f"{lvl} {arm}"
        for e_id, lvl, arm in await db.execute(
            select(Enrollment.id, ClassLevel.name, Arm.name)
            .join(Arm, Arm.id == Enrollment.arm_id)
            .join(ClassLevel, ClassLevel.id == Arm.class_level_id)
        )
    }
    per: dict[str, list[int]] = defaultdict(
        lambda: [0, 0, 0, 0]
    )  # invoices, expected, collected, outstanding
    for i in invoices:
        row = per[labels.get(i.enrollment_id, "—")]
        expected = i.total_kobo + (
            bal[i.id] - i.total_kobo + paid[i.id]
        )  # total + adjustments + refunds
        row[0] += 1
        row[1] += expected
        row[2] += paid[i.id]
        row[3] += max(bal[i.id], 0)
    pending = await db.scalar(
        select(func.count())
        .select_from(TransferProof)
        .join(Invoice, Invoice.id == TransferProof.invoice_id)
        .where(Invoice.term_id == term.id, TransferProof.status == ProofStatus.PENDING)
    )
    classes = [
        ClassSummary(
            label=k, invoices=v[0], expected_kobo=v[1], collected_kobo=v[2], outstanding_kobo=v[3]
        )
        for k, v in sorted(per.items())
    ]
    return FeeSummaryOut(
        term_label=term_label(term, session_name),
        expected_kobo=sum(c.expected_kobo for c in classes),
        collected_kobo=sum(c.collected_kobo for c in classes),
        outstanding_kobo=sum(c.outstanding_kobo for c in classes),
        invoices=len(invoices),
        fully_paid=sum(1 for i in invoices if bal[i.id] <= 0),
        pending_proofs=pending or 0,
        classes=classes,
    )


async def bursar_user_ids(db: AsyncSession) -> list[uuid.UUID]:
    return list(
        await db.scalars(
            select(Membership.user_id)
            .where(Membership.role.in_([Role.BURSAR, Role.SCHOOL_ADMIN]))
            .distinct()
        )
    )
