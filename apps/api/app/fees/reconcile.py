"""Paystack reconciliation (R22): catch payments whose webhook and browser return both failed.

Every pending checkout older than a few minutes is re-verified with Paystack and applied
through the same idempotent `apply_paystack` the webhook uses, so running this any number of
times, alongside the webhook, never double counts. Runs on a timer in the API process
(`run_forever`, guarded by a Redis lock) and on demand: `python -m app.scripts.reconcile`.
"""

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import HTTPException
from sqlalchemy import select

from app.core.redis import get_redis
from app.db.session import get_sessionmaker
from app.fees import retention
from app.fees import service as fees
from app.fees.models import IntentStatus, PaymentIntent
from app.fees.paystack import PaystackClient, get_paystack
from app.tenancy.deps import run_after_commit, set_tenant
from app.tenancy.models import School

log = structlog.get_logger(__name__)

MIN_AGE = timedelta(minutes=10)  # give the webhook and the browser return a chance first
MAX_AGE = timedelta(days=7)  # older checkouts are long abandoned
GIVE_UP_AFTER = timedelta(hours=24)  # after this, "still in progress" counts as failed
IN_PROGRESS = {"ongoing", "pending", "processing", "queued"}
INTERVAL_SECONDS = 30 * 60
LOCK_KEY = "lock:paystack-reconcile"


@dataclass
class Report:
    checked: int = 0
    applied: int = 0
    failed: int = 0
    still_pending: int = 0
    errors: list[str] = field(default_factory=list)


async def reconcile(
    paystack: PaystackClient,
    now: datetime | None = None,
    school_ids: list[uuid.UUID] | None = None,
) -> Report:
    """Re-check pending checkouts in every school (or just `school_ids`)."""
    now = now or datetime.now(UTC)
    report = Report()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        query = select(School)
        if school_ids is not None:
            query = query.where(School.id.in_(school_ids))
        schools = list(await db.scalars(query))
    for school in schools:
        async with sessionmaker() as db, db.begin():
            await set_tenant(db, school)
            rows = await db.execute(
                select(PaymentIntent.reference, PaymentIntent.created_at)
                .where(
                    PaymentIntent.status == IntentStatus.PENDING,
                    PaymentIntent.created_at <= now - MIN_AGE,
                    PaymentIntent.created_at >= now - MAX_AGE,
                )
                .order_by(PaymentIntent.created_at)
            )
            pending = [(reference, created_at) for reference, created_at in rows]
        for reference, created_at in pending:
            report.checked += 1
            try:
                verification = await paystack.verify(reference)
            except HTTPException as exc:  # Paystack down or unknown reference: try next run
                report.errors.append(f"{reference}: {exc.detail}")
                continue
            status = str(verification.raw.get("status", ""))
            if (
                not verification.success
                and status in IN_PROGRESS
                and now - created_at < GIVE_UP_AFTER
            ):
                report.still_pending += 1
                continue
            async with sessionmaker() as db:
                async with db.begin():
                    await set_tenant(db, school)
                    _, entry = await fees.apply_paystack(
                        db, reference, verification, via="reconcile"
                    )
                await run_after_commit(db)
            if entry is not None:
                report.applied += 1
                log.warning(
                    "paystack.reconciled_missed_payment", reference=reference, school=school.slug
                )
            else:
                report.failed += 1
    log.info("paystack.reconcile", **{k: v for k, v in report.__dict__.items() if k != "errors"},
             errors=len(report.errors))  # fmt: skip
    return report


async def run_once_locked() -> Report | None:
    """Run unless another instance is already running (Redis lock)."""
    try:
        paystack = get_paystack()
    except HTTPException:
        return None  # no Paystack key: nothing to reconcile
    redis = get_redis()
    if not await redis.set(LOCK_KEY, "1", nx=True, ex=INTERVAL_SECONDS - 60):
        return None
    try:
        return await reconcile(paystack)
    finally:
        await redis.delete(LOCK_KEY)


async def run_forever() -> None:
    """Background loop started by the API's lifespan. Never lets an error kill the loop."""
    await asyncio.sleep(60)  # let the app finish starting
    while True:
        try:
            await run_once_locked()
        except Exception:
            log.exception("paystack.reconcile_failed")
        try:  # housekeeping rides on the same timer (idempotent, so no lock needed)
            if purged := await retention.purge_old_proof_files():
                log.info("retention.proof_files_purged", count=purged)
        except Exception:
            log.exception("retention.purge_failed")
        await asyncio.sleep(INTERVAL_SECONDS)


@contextlib.asynccontextmanager
async def background() -> AsyncIterator[None]:
    task = asyncio.create_task(run_forever())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
