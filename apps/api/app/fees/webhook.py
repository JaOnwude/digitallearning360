"""Paystack webhook (R22, AC7). Called by Paystack directly: no school host, no session.

1. Reject anything without a valid HMAC-SHA512 signature (401, nothing stored).
2. Store the event once (unique key) so retries are recognised.
3. Re-verify the transaction with Paystack (never trust the payload's amount alone).
4. Apply it inside that school's tenant transaction, exactly once.
Always answer 200 for a valid, recognised delivery so Paystack stops retrying.
"""

import json
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_sessionmaker
from app.fees import service as fees
from app.fees.models import PaystackEvent, PaystackReference
from app.fees.paystack import PaystackClient, get_paystack, valid_signature
from app.tenancy.deps import run_after_commit, set_tenant
from app.tenancy.models import School

router = APIRouter(tags=["webhooks"])
log = structlog.get_logger(__name__)


@router.post("/api/webhooks/paystack", include_in_schema=False)
async def paystack_webhook(
    request: Request,
    paystack: PaystackClient = Depends(get_paystack),  # noqa: B008
) -> dict[str, str]:
    raw = await request.body()
    if not valid_signature(raw, request.headers.get("x-paystack-signature")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    payload = json.loads(raw)
    event = payload.get("event", "")
    data = payload.get("data") or {}
    reference = data.get("reference")
    if event != "charge.success" or not reference:
        return {"status": "ignored"}

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db, db.begin():
        inserted = await db.scalar(
            insert(PaystackEvent)
            .values(
                event_key=f"{event}:{reference}", event=event, reference=reference, payload=payload
            )
            .on_conflict_do_nothing(index_elements=["event_key"])
            .returning(PaystackEvent.id)
        )
        owner = await db.scalar(
            select(PaystackReference.owner_school_id).where(
                PaystackReference.reference == reference
            )
        )
    if owner is None:
        log.warning("paystack.unknown_reference", reference=reference)
        return {"status": "unknown"}
    if inserted is None:
        # A retry of a delivery we already stored. Applying is idempotent, so carry on: if the
        # first attempt crashed before applying, this one finishes the job.
        log.info("paystack.duplicate_delivery", reference=reference)

    verification = await paystack.verify(reference)
    async with sessionmaker() as db:
        async with db.begin():
            school = await db.get(School, owner)
            assert school is not None
            await set_tenant(db, school)
            invoice, entry = await fees.apply_paystack(db, reference, verification, via="webhook")
        await run_after_commit(db)
    async with sessionmaker() as db, db.begin():
        await db.execute(
            update(PaystackEvent)
            .where(PaystackEvent.event_key == f"{event}:{reference}")
            .values(processed_at=datetime.now(UTC), error=None if entry else "not applied")
        )
    return {"status": "ok" if invoice else "unknown"}
