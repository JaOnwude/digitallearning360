"""Parents and students: their invoices, paying online, uploading transfer proof (R22–R23)."""

import hashlib
import uuid
from datetime import date
from typing import Annotated

import uuid_utils
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import or_, select

from app.audit import service as audit
from app.auth.deps import CurrentPrincipal
from app.auth.models import User
from app.core.config import get_settings
from app.core.http import client_ip
from app.fees import ledger
from app.fees import service as fees
from app.fees.access import family_student_ids, payable_invoice
from app.fees.models import Invoice, PaymentIntent, PaystackReference, ProofStatus, TransferProof
from app.fees.paystack import PaystackClient, get_paystack
from app.fees.schemas import (
    CheckoutOut,
    FamilyInvoices,
    MyFeesOut,
    PaymentResultOut,
    ProofOut,
    VerifyIn,
)
from app.notifications import events
from app.students.models import Guardian, Student
from app.tenancy.deps import CurrentSchool, TenantDB, after_commit

router = APIRouter(prefix="/api/fees", tags=["fees"])

MAX_PROOF_BYTES = 5 * 1024 * 1024
Paystack = Annotated[PaystackClient, Depends(get_paystack)]


@router.get("/mine", response_model=MyFeesOut)
async def my_fees(p: CurrentPrincipal, school: CurrentSchool, db: TenantDB) -> MyFeesOut:
    """A parent's children (or a student) with every invoice, newest first."""
    ids = await family_student_ids(db, p)
    children = []
    for student in await db.scalars(
        select(Student).where(Student.id.in_(ids)).order_by(Student.first_name)
    ):
        invoices = list(
            await db.scalars(
                select(Invoice)
                .where(Invoice.student_id == student.id)
                .order_by(Invoice.created_at.desc())
            )
        )
        rows = await fees.invoice_rows(db, invoices)
        children.append(
            FamilyInvoices(
                student_id=student.id,
                student_name=student.full_name,
                class_label=rows[0].class_label if rows else None,
                invoices=rows,
            )
        )
    return MyFeesOut(children=children, bank=fees.bank_details(school))


def _web_base(request: Request) -> str:
    scheme = "https" if get_settings().is_deployed else "http"
    return f"{scheme}://{request.headers.get('x-dl360-host', '')}"


@router.post("/invoices/{invoice_id}/paystack", response_model=CheckoutOut)
async def start_paystack(
    invoice_id: uuid.UUID,
    request: Request,
    p: CurrentPrincipal,
    school: CurrentSchool,
    db: TenantDB,
    paystack: Paystack,
) -> CheckoutOut:
    """Paystack checkout for the full outstanding balance (decided: no part-payment online)."""
    invoice = await payable_invoice(db, p, invoice_id)
    settings = fees.fee_settings(school)
    if not fees.online_payment_ready(settings):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Online payment isn't set up for this school yet. Please pay by bank transfer.",
        )
    amount = await ledger.balance(db, invoice.id)
    if amount <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice is already fully paid.")
    payer = await db.get(User, p.session.user_uuid)
    email = payer.email if payer and payer.email else None
    if (
        email is None
    ):  # a parent without email (e.g. phone-only) still needs one for Paystack receipts
        email = (
            await db.scalar(
                select(Guardian.email).where(
                    Guardian.user_id == p.session.user_uuid, Guardian.email.is_not(None)
                )
            )
            or f"parent-{p.session.user_id}@noreply.digitallearning360.ng"
        )
    reference = f"DL360-{uuid_utils.uuid7().hex}"
    db.add(
        PaymentIntent(
            school_id=school.id,
            invoice_id=invoice.id,
            reference=reference,
            amount_kobo=amount,
            payer_user_id=p.session.user_uuid,
        )
    )
    db.add(PaystackReference(reference=reference, owner_school_id=school.id))
    await db.flush()
    checkout = await paystack.initialize(
        email=email,
        amount_kobo=amount,
        reference=reference,
        callback_url=f"{_web_base(request)}/fees/paid",
        subaccount=settings.paystack_subaccount_code,
        metadata={
            "school_id": str(school.id),
            "invoice_id": str(invoice.id),
            "invoice": invoice.reference,
        },
    )
    return CheckoutOut(
        authorization_url=checkout.authorization_url, reference=reference, amount_kobo=amount
    )


@router.post("/paystack/verify", response_model=PaymentResultOut)
async def verify_paystack(
    body: VerifyIn, p: CurrentPrincipal, db: TenantDB, paystack: Paystack
) -> PaymentResultOut:
    """Called by the page Paystack returns the parent to. Applies the payment if the webhook
    hasn't already (both paths are idempotent)."""
    intent = await db.scalar(select(PaymentIntent).where(PaymentIntent.reference == body.reference))
    if intent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    await payable_invoice(db, p, intent.invoice_id)
    verification = await paystack.verify(body.reference)
    invoice, entry = await fees.apply_paystack(db, body.reference, verification, via="verify")
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return PaymentResultOut(
        status="paid" if entry else ("failed" if not verification.success else "pending"),
        invoice_id=invoice.id,
        balance_kobo=await ledger.balance(db, invoice.id),
        receipt_entry_id=entry.id if entry else None,
    )


def _sniff(content: bytes) -> str | None:
    """Trust the bytes, not the filename or browser-declared type."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    return None


@router.post(
    "/invoices/{invoice_id}/proofs", response_model=ProofOut, status_code=status.HTTP_201_CREATED
)
async def upload_proof(
    invoice_id: uuid.UUID,
    request: Request,
    p: CurrentPrincipal,
    school: CurrentSchool,
    db: TenantDB,
    file: Annotated[UploadFile, File(description="Photo or PDF of the transfer receipt")],
    amount_kobo: Annotated[int, Form(gt=0, le=10_000_000_000)],
    bank_reference: Annotated[str | None, Form(max_length=100)] = None,
    paid_on: Annotated[date | None, Form()] = None,
) -> ProofOut:
    """R23: a parent's evidence of a bank transfer, for the bursar to confirm."""
    invoice = await payable_invoice(db, p, invoice_id)
    content = await file.read(MAX_PROOF_BYTES + 1)
    if len(content) > MAX_PROOF_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Keep the file under 5 MB.")
    content_type = _sniff(content)
    if content_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a photo (JPEG/PNG) or a PDF."
        )
    digest = hashlib.sha256(content).hexdigest()
    ref = (bank_reference or "").strip() or None
    # Same file, or same bank reference, already submitted → flag for the bursar (AC9).
    dup_conditions = [TransferProof.sha256 == digest]
    if ref:
        dup_conditions.append(TransferProof.bank_reference == ref)
    duplicate = await db.scalar(
        select(TransferProof.id)
        .where(or_(*dup_conditions), TransferProof.status != ProofStatus.REJECTED)
        .order_by(TransferProof.created_at)
        .limit(1)
    )
    proof = TransferProof(
        school_id=school.id,
        invoice_id=invoice.id,
        submitted_by=p.session.user_uuid,
        claimed_amount_kobo=amount_kobo,
        bank_reference=ref,
        paid_on=paid_on,
        file=content,
        content_type=content_type,
        sha256=digest,
        duplicate_of=duplicate,
    )
    db.add(proof)
    await db.flush()
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=p.session.user_uuid,
        action="fees.proof_submitted",
        entity_type="TransferProof",
        entity_id=proof.id,
        after={
            "invoice": invoice.reference,
            "amount_kobo": amount_kobo,
            "duplicate": bool(duplicate),
        },
        ip=client_ip(request),
    )
    channel = events.fees_channel(school.id)
    after_commit(
        db, lambda: events.publish([channel], "proof.submitted", {"invoice_id": str(invoice.id)})
    )
    return (await fees.proof_outs(db, [proof]))[0]
