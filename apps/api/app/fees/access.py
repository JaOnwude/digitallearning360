"""Who may see or act on an invoice."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import Principal, require_roles
from app.auth.models import Role
from app.db.helpers import get_or_404
from app.fees.models import Invoice
from app.students.models import Guardian, Student, StudentGuardian

FeeManager = Annotated[Principal, Depends(require_roles(Role.SCHOOL_ADMIN, Role.BURSAR))]


def manages_fees(p: Principal) -> bool:
    return bool(p.roles & {Role.SCHOOL_ADMIN, Role.BURSAR})


async def family_student_ids(db: AsyncSession, p: Principal) -> set[uuid.UUID]:
    """Students a parent (their children) or a student (themself) may see."""
    me = p.session.user_uuid
    ids: set[uuid.UUID] = set()
    if Role.PARENT in p.roles:
        ids |= set(
            await db.scalars(
                select(StudentGuardian.student_id)
                .join(Guardian, Guardian.id == StudentGuardian.guardian_id)
                .where(Guardian.user_id == me)
            )
        )
    if Role.STUDENT in p.roles:
        ids |= set(await db.scalars(select(Student.id).where(Student.user_id == me)))
    return ids


async def readable_invoice(db: AsyncSession, p: Principal, invoice_id: uuid.UUID) -> Invoice:
    """Fee managers see every invoice; families see their own. Others get a plain 404."""
    invoice = await get_or_404(db, Invoice, invoice_id, "Invoice")
    if manages_fees(p) or invoice.student_id in await family_student_ids(db, p):
        return invoice
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")


async def payable_invoice(db: AsyncSession, p: Principal, invoice_id: uuid.UUID) -> Invoice:
    """Only a parent (not the student) pays or uploads proof for their child's invoice."""
    invoice = await readable_invoice(db, p, invoice_id)
    if Role.PARENT not in p.roles and not manages_fees(p):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Ask a parent or guardian to pay this invoice."
        )
    return invoice
