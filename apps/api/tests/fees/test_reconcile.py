"""Reconciliation catches payments whose webhook and browser return were both lost (R22)."""

from datetime import UTC, datetime, timedelta

from app.fees.reconcile import reconcile
from tests.conftest import ClientFactory
from tests.fees.conftest import TUITION_KOBO, FeesWorld
from tests.fees.fake_paystack import FakePaystack

LATER = timedelta(minutes=15)


async def _payments(fees_world: FeesWorld, invoice_id: str) -> list[dict]:
    detail = (await fees_world.bursar.get(f"/api/fees/invoices/{invoice_id}")).json()
    return [e for e in detail["entries"] if e["kind"] == "payment"]


async def test_lost_payment_is_applied_exactly_once(
    fees_world: FeesWorld, client_for: ClientFactory, paystack: FakePaystack
) -> None:
    parent = await fees_world.parent(client_for)
    inv = fees_world.invoice_ids[0]
    res = await parent.post(f"/api/fees/invoices/{inv}/paystack")
    assert res.status_code == 200
    # The parent paid, but neither the webhook nor the return page ever reached us.

    too_soon = await reconcile(paystack, school_ids=[fees_world.w.school.id])
    assert too_soon.checked == 0  # the webhook still gets its chance first

    first = await reconcile(
        paystack, now=datetime.now(UTC) + LATER, school_ids=[fees_world.w.school.id]
    )
    assert (first.checked, first.applied) == (1, 1)
    second = await reconcile(
        paystack, now=datetime.now(UTC) + LATER, school_ids=[fees_world.w.school.id]
    )
    assert second.checked == 0  # no longer pending

    payments = await _payments(fees_world, inv)
    assert len(payments) == 1 and payments[0]["amount_kobo"] == TUITION_KOBO
    # A late webhook/verify for the same payment changes nothing.
    again = await parent.post(
        "/api/fees/paystack/verify", json={"reference": res.json()["reference"]}
    )
    assert again.json()["status"] == "paid"
    assert len(await _payments(fees_world, inv)) == 1


async def test_in_progress_checkouts_are_left_alone_then_given_up(
    fees_world: FeesWorld, client_for: ClientFactory, paystack: FakePaystack
) -> None:
    parent = await fees_world.parent(client_for)
    inv = fees_world.invoice_ids[0]
    ref = (await parent.post(f"/api/fees/invoices/{inv}/paystack")).json()["reference"]
    paystack.outcomes[ref] = (False, 0)
    paystack.statuses[ref] = "ongoing"

    report = await reconcile(
        paystack, now=datetime.now(UTC) + LATER, school_ids=[fees_world.w.school.id]
    )
    assert (report.still_pending, report.failed) == (1, 0)
    report = await reconcile(
        paystack, now=datetime.now(UTC) + timedelta(hours=25), school_ids=[fees_world.w.school.id]
    )
    assert (report.still_pending, report.failed) == (0, 1)
    assert await _payments(fees_world, inv) == []
