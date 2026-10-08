"""Fees: schedules, invoices, the payment ledger, Paystack intents and transfer proofs (R19–R24).

Money is always integer kobo. An invoice's balance is never stored: it is derived from its
total and its ledger entries (`fees/ledger.py`).
"""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import IdMixin, TenantMixin, tenant_fk
from app.db.types import str_enum

# ---------------------------------------------------------------- what a term costs


class FeeItem(Base, TenantMixin):
    """e.g. "Tuition", "PTA levy", "Uniform" (optional items are added per student)."""

    __tablename__ = "fee_items"
    __extra_args__ = (UniqueConstraint("school_id", "name", name="uq_fee_items_name"),)

    name: Mapped[str] = mapped_column(String(100))
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)


class FeeScheduleEntry(Base, TenantMixin):
    """The amount of one fee item for one class level in one term."""

    __tablename__ = "fee_schedule"
    __extra_args__ = (
        tenant_fk("fee_item_id", "fee_items", ondelete="CASCADE"),
        tenant_fk("class_level_id", "class_levels", ondelete="CASCADE"),
        tenant_fk("term_id", "terms", ondelete="CASCADE"),
        UniqueConstraint(
            "school_id", "fee_item_id", "class_level_id", "term_id", name="uq_fee_schedule_cell"
        ),
        CheckConstraint("amount_kobo >= 0", name="amount_non_negative"),
    )

    fee_item_id: Mapped[uuid.UUID]
    class_level_id: Mapped[uuid.UUID]
    term_id: Mapped[uuid.UUID]
    amount_kobo: Mapped[int] = mapped_column(BigInteger)


class StudentDiscount(Base, TenantMixin):
    """A standing discount (scholarship, sibling, staff child) applied when invoicing."""

    __tablename__ = "student_discounts"
    __extra_args__ = (
        tenant_fk("student_id", "students", ondelete="CASCADE"),
        tenant_fk("fee_item_id", "fee_items", ondelete="CASCADE"),
        CheckConstraint("(percent IS NULL) <> (fixed_kobo IS NULL)", name="percent_xor_fixed"),
        CheckConstraint(
            "percent IS NULL OR (percent > 0 AND percent <= 100)", name="percent_range"
        ),
        CheckConstraint("fixed_kobo IS NULL OR fixed_kobo > 0", name="fixed_positive"),
    )

    student_id: Mapped[uuid.UUID]
    fee_item_id: Mapped[uuid.UUID | None]  # None = whole invoice
    percent: Mapped[int | None] = mapped_column(SmallInteger)
    fixed_kobo: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(200))


# ---------------------------------------------------------------- invoices


class Invoice(Base, TenantMixin):
    """One student's bill for one term (R20). Lines are frozen once issued."""

    __tablename__ = "invoices"
    __extra_args__ = (
        tenant_fk("student_id", "students", ondelete="RESTRICT"),
        tenant_fk("enrollment_id", "enrollments", ondelete="RESTRICT"),
        tenant_fk("term_id", "terms", ondelete="RESTRICT"),
        UniqueConstraint("school_id", "reference", name="uq_invoices_reference"),
        UniqueConstraint("school_id", "student_id", "term_id", name="uq_invoices_student_term"),
        CheckConstraint("total_kobo >= 0", name="total_non_negative"),
    )

    student_id: Mapped[uuid.UUID]
    enrollment_id: Mapped[uuid.UUID]
    term_id: Mapped[uuid.UUID]
    reference: Mapped[str] = mapped_column(String(40))
    total_kobo: Mapped[int] = mapped_column(BigInteger)
    due_on: Mapped[date | None] = mapped_column(Date)
    # R18: results stay visible despite a balance (granted by admin/bursar, audited).
    results_exempt: Mapped[bool] = mapped_column(Boolean, default=False)
    issued_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class InvoiceLine(Base, TenantMixin):
    __tablename__ = "invoice_lines"
    __extra_args__ = (
        tenant_fk("invoice_id", "invoices", ondelete="CASCADE"),
        tenant_fk("fee_item_id", "fee_items", ondelete="SET NULL"),
    )

    invoice_id: Mapped[uuid.UUID]
    fee_item_id: Mapped[uuid.UUID | None]
    description: Mapped[str] = mapped_column(String(200))
    amount_kobo: Mapped[int] = mapped_column(BigInteger)  # discounts are negative
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)


class InvoiceCounter(Base, TenantMixin):
    """Per-term invoice sequence, incremented under a row lock (no gaps from races)."""

    __tablename__ = "invoice_counters"
    __extra_args__ = (
        tenant_fk("term_id", "terms", ondelete="CASCADE"),
        UniqueConstraint("school_id", "term_id", name="uq_invoice_counters_term"),
    )

    term_id: Mapped[uuid.UUID]
    last_seq: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------- the ledger


class EntryKind(StrEnum):
    PAYMENT = "payment"  # money in: reduces the balance
    REFUND = "refund"  # money back out: increases the balance
    ADJUSTMENT = "adjustment"  # waiver (negative) or extra charge (positive), with a reason


class EntrySource(StrEnum):
    PAYSTACK = "paystack"
    TRANSFER = "transfer"
    CASH = "cash"
    MANUAL = "manual"


class LedgerEntry(Base, TenantMixin):
    """Every naira that moves on an invoice (R21). Never updated or deleted by the app."""

    __tablename__ = "ledger_entries"
    __extra_args__ = (
        tenant_fk("invoice_id", "invoices", ondelete="RESTRICT"),
        # The final guard against double-counting the same payment (webhook + verify + retries).
        UniqueConstraint("school_id", "external_ref", name="uq_ledger_entries_external_ref"),
        UniqueConstraint("school_id", "receipt_no", name="uq_ledger_entries_receipt_no"),
        CheckConstraint(
            "(kind = 'adjustment' AND amount_kobo <> 0)"
            " OR (kind <> 'adjustment' AND amount_kobo > 0)",
            name="amount_sign",
        ),
    )

    invoice_id: Mapped[uuid.UUID]
    kind: Mapped[EntryKind] = mapped_column(str_enum(EntryKind))
    source: Mapped[EntrySource] = mapped_column(str_enum(EntrySource))
    amount_kobo: Mapped[int] = mapped_column(BigInteger)
    external_ref: Mapped[str | None] = mapped_column(String(100))
    receipt_no: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(300))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


# ---------------------------------------------------------------- Paystack


class IntentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PaymentIntent(Base, TenantMixin):
    """A Paystack checkout we started. Applied to the ledger at most once."""

    __tablename__ = "payment_intents"
    __extra_args__ = (
        tenant_fk("invoice_id", "invoices", ondelete="RESTRICT"),
        UniqueConstraint("school_id", "reference", name="uq_payment_intents_reference"),
    )

    invoice_id: Mapped[uuid.UUID]
    reference: Mapped[str] = mapped_column(String(100))
    amount_kobo: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[IntentStatus] = mapped_column(
        str_enum(IntentStatus), default=IntentStatus.PENDING
    )
    payer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    gateway_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class PaystackReference(Base, IdMixin):
    """Global (no RLS): which school a Paystack reference belongs to, for the webhook,
    which arrives without a school host. Holds no payment data."""

    __tablename__ = "paystack_references"

    reference: Mapped[str] = mapped_column(String(100), unique=True)
    owner_school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaystackEvent(Base, IdMixin):
    """Global (no RLS): every webhook delivery we accepted, stored once (idempotency, audit)."""

    __tablename__ = "paystack_events"

    event_key: Mapped[str] = mapped_column(String(200), unique=True)
    event: Mapped[str] = mapped_column(String(60))
    reference: Mapped[str | None] = mapped_column(String(100), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- bank transfer proofs


class ProofStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class TransferProof(Base, TenantMixin):
    """A parent's evidence of a bank transfer, confirmed or rejected by the bursar (R23)."""

    __tablename__ = "transfer_proofs"
    __extra_args__ = (
        tenant_fk("invoice_id", "invoices", ondelete="RESTRICT"),
        tenant_fk("duplicate_of", "transfer_proofs"),
        CheckConstraint("claimed_amount_kobo > 0", name="claimed_positive"),
    )

    invoice_id: Mapped[uuid.UUID]
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    claimed_amount_kobo: Mapped[int] = mapped_column(BigInteger)
    bank_reference: Mapped[str | None] = mapped_column(String(100))
    paid_on: Mapped[date | None] = mapped_column(Date)
    file: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    content_type: Mapped[str] = mapped_column(String(40))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[ProofStatus] = mapped_column(str_enum(ProofStatus), default=ProofStatus.PENDING)
    confirmed_amount_kobo: Mapped[int | None] = mapped_column(BigInteger)
    review_note: Mapped[str | None] = mapped_column(String(300))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duplicate_of: Mapped[uuid.UUID | None]
