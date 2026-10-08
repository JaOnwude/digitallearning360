"""The only place an invoice's balance is worked out (R21).

balance = total + adjustments − payments + refunds   (kobo; negative = in credit)
"""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.fees.models import EntryKind, EntrySource, Invoice, LedgerEntry

_SIGNED = case(
    (LedgerEntry.kind == EntryKind.PAYMENT, -LedgerEntry.amount_kobo),
    else_=LedgerEntry.amount_kobo,  # refunds add back; adjustments carry their own sign
)


async def balances(db: AsyncSession, invoice_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not invoice_ids:
        return {}
    movement = dict(
        (inv, int(total))
        for inv, total in await db.execute(
            select(LedgerEntry.invoice_id, func.coalesce(func.sum(_SIGNED), 0))
            .where(LedgerEntry.invoice_id.in_(invoice_ids))
            .group_by(LedgerEntry.invoice_id)
        )
    )
    totals = dict(
        (i, t)
        for i, t in await db.execute(
            select(Invoice.id, Invoice.total_kobo).where(Invoice.id.in_(invoice_ids))
        )
    )
    return {i: totals[i] + movement.get(i, 0) for i in totals}


async def balance(db: AsyncSession, invoice_id: uuid.UUID) -> int:
    return (await balances(db, [invoice_id])).get(invoice_id, 0)


async def paid_total(db: AsyncSession, invoice_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount_kobo), 0)).where(
                LedgerEntry.invoice_id == invoice_id, LedgerEntry.kind == EntryKind.PAYMENT
            )
        )
        or 0
    )


async def lock_invoice(db: AsyncSession, invoice_id: uuid.UUID) -> Invoice | None:
    """Row-lock an invoice for the rest of the transaction: payments on it are applied one
    at a time, so concurrent webhooks/verifications can't both see "not yet paid"."""
    return await db.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update())


async def entry_by_ref(db: AsyncSession, external_ref: str) -> LedgerEntry | None:
    return await db.scalar(select(LedgerEntry).where(LedgerEntry.external_ref == external_ref))


async def record(
    db: AsyncSession,
    invoice: Invoice,
    *,
    kind: EntryKind,
    source: EntrySource,
    amount_kobo: int,
    recorded_by: uuid.UUID | None,
    external_ref: str | None = None,
    note: str | None = None,
) -> LedgerEntry:
    """Append one entry. Callers must hold the invoice lock (`lock_invoice`)."""
    receipt_no = None
    if kind == EntryKind.PAYMENT:
        count = await db.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.invoice_id == invoice.id, LedgerEntry.kind == EntryKind.PAYMENT)
        )
        receipt_no = f"RCT-{invoice.reference}-{(count or 0) + 1}"
    entry = LedgerEntry(
        school_id=invoice.school_id,
        invoice_id=invoice.id,
        kind=kind,
        source=source,
        amount_kobo=amount_kobo,
        external_ref=external_ref,
        receipt_no=receipt_no,
        note=note,
        recorded_by=recorded_by,
    )
    db.add(entry)
    await db.flush()
    return entry


def naira(kobo: int) -> str:
    """4500000 → "₦45,000.00"."""
    sign = "-" if kobo < 0 else ""
    whole, part = divmod(abs(kobo), 100)
    return f"{sign}₦{whole:,}.{part:02d}"
