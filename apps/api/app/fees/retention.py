"""Data retention (NDPA 2023; privacy notice): transfer-receipt images are deleted one year
after the bursar reviews them. The proof row (amount, reference, decision) stays, because it
is part of the fee record; only the uploaded image or PDF goes."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.db.session import get_sessionmaker
from app.fees.models import ProofStatus, TransferProof
from app.tenancy.deps import set_tenant
from app.tenancy.models import School

PROOF_FILE_RETENTION = timedelta(days=365)


async def purge_old_proof_files(now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(UTC)) - PROOF_FILE_RETENTION
    purged = 0
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        schools = list(await db.scalars(select(School)))
    for school in schools:
        async with sessionmaker() as db, db.begin():
            await set_tenant(db, school)
            result = await db.execute(
                update(TransferProof)
                .where(
                    TransferProof.status != ProofStatus.PENDING,
                    TransferProof.reviewed_at < cutoff,
                    func.length(TransferProof.file) > 0,
                )
                .values(file=b"")
            )
            purged += result.rowcount or 0  # type: ignore[attr-defined]
    return purged
