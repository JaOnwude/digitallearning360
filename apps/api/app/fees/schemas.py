from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.fees.models import EntryKind, EntrySource, ProofStatus

Kobo = Field(ge=0, le=10_000_000_000)  # ≤ ₦100m: generous, but catches typos with extra zeros


# ---------------------------------------------------------------- setup


class FeeItemIO(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    is_optional: bool = False


class ScheduleCell(BaseModel):
    fee_item_id: UUID
    class_level_id: UUID
    term_id: UUID
    amount_kobo: int | None = Field(default=None, ge=0, le=10_000_000_000)  # None clears


class FeeSettingsIO(BaseModel):
    bank_name: str | None = Field(default=None, max_length=100)
    account_name: str | None = Field(default=None, max_length=150)
    account_number: str | None = Field(default=None, pattern=r"^\d{10}$")  # NUBAN
    paystack_subaccount_code: str | None = Field(default=None, pattern=r"^ACCT_[A-Za-z0-9]+$")
    withhold_results_for_debt: bool = True


class FeeLevelOut(BaseModel):
    id: UUID
    name: str


class FeeTermOut(BaseModel):
    id: UUID
    label: str
    is_current: bool


class FeeSetupOut(BaseModel):
    items: list[FeeItemIO]
    levels: list[FeeLevelOut]
    terms: list[FeeTermOut]
    schedule: list[ScheduleCell]
    settings: FeeSettingsIO
    paystack_configured: bool


class DiscountIn(BaseModel):
    student_id: UUID
    fee_item_id: UUID | None = None
    percent: int | None = Field(default=None, ge=1, le=100)
    fixed_kobo: int | None = Field(default=None, ge=1, le=10_000_000_000)
    reason: str = Field(min_length=3, max_length=200)


class DiscountOut(DiscountIn):
    id: UUID
    student_name: str
    fee_item_name: str | None


# ---------------------------------------------------------------- invoices


class GenerateIn(BaseModel):
    term_id: UUID | None = None  # default: current term
    class_level_ids: list[UUID] | None = None


class GenerateOut(BaseModel):
    created: int
    already_invoiced: int
    no_schedule: int


class InvoiceRow(BaseModel):
    id: UUID
    reference: str
    student_id: UUID
    student_name: str
    admission_no: str
    class_label: str | None
    term_label: str
    total_kobo: int
    paid_kobo: int
    balance_kobo: int
    pending_proofs: int


class InvoicePage(BaseModel):
    items: list[InvoiceRow]
    total: int
    page: int
    page_size: int


class LineOut(BaseModel):
    description: str
    amount_kobo: int


class EntryOut(BaseModel):
    id: UUID
    kind: EntryKind
    source: EntrySource
    amount_kobo: int
    receipt_no: str | None
    note: str | None
    created_at: datetime


class ProofOut(BaseModel):
    id: UUID
    invoice_id: UUID
    invoice_reference: str
    student_name: str
    claimed_amount_kobo: int
    bank_reference: str | None
    paid_on: date | None
    content_type: str
    status: ProofStatus
    confirmed_amount_kobo: int | None
    review_note: str | None
    duplicate_of: UUID | None
    created_at: datetime


class BankDetails(BaseModel):
    bank_name: str | None
    account_name: str | None
    account_number: str | None


class InvoiceDetail(InvoiceRow):
    due_on: date | None
    results_exempt: bool
    lines: list[LineOut]
    entries: list[EntryOut]
    proofs: list[ProofOut]
    bank: BankDetails
    can_pay_online: bool


class AdjustmentIn(BaseModel):
    amount_kobo: int = Field(ge=-10_000_000_000, le=10_000_000_000)  # negative = waiver
    note: str = Field(min_length=3, max_length=300)


class OfficePaymentIn(BaseModel):
    """Cash or other payment received at the school office."""

    amount_kobo: int = Field(gt=0, le=10_000_000_000)
    source: EntrySource = EntrySource.CASH
    note: str | None = Field(default=None, max_length=300)


class ExemptIn(BaseModel):
    exempt: bool
    reason: str = Field(min_length=3, max_length=300)


class ProofReviewIn(BaseModel):
    amount_kobo: int = Field(gt=0, le=10_000_000_000)
    note: str | None = Field(default=None, max_length=300)


class ProofRejectIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


# ---------------------------------------------------------------- paystack


class CheckoutOut(BaseModel):
    authorization_url: str
    reference: str
    amount_kobo: int


class VerifyIn(BaseModel):
    reference: str = Field(min_length=6, max_length=100)


class PaymentResultOut(BaseModel):
    status: str  # "paid" | "pending" | "failed"
    invoice_id: UUID | None
    balance_kobo: int | None
    receipt_entry_id: UUID | None


# ---------------------------------------------------------------- dashboards


class ClassSummary(BaseModel):
    label: str
    invoices: int
    expected_kobo: int
    collected_kobo: int
    outstanding_kobo: int


class FeeSummaryOut(BaseModel):
    term_label: str
    expected_kobo: int
    collected_kobo: int
    outstanding_kobo: int
    invoices: int
    fully_paid: int
    pending_proofs: int
    classes: list[ClassSummary]


class FamilyInvoices(BaseModel):
    student_id: UUID
    student_name: str
    class_label: str | None
    invoices: list[InvoiceRow]


class MyFeesOut(BaseModel):
    children: list[FamilyInvoices]
    bank: BankDetails
