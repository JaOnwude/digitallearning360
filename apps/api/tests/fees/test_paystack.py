"""Paystack: checkout, verification and the webhook (R22, AC7, AC8)."""

import asyncio
import hashlib
import hmac
import json
import os

from httpx import AsyncClient

from tests.conftest import ClientFactory
from tests.fees.conftest import TUITION_KOBO, FeesWorld
from tests.fees.fake_paystack import FakePaystack


def _signed(payload: dict) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    key = os.environ["DL360_PAYSTACK_SECRET_KEY"].encode()
    sig = hmac.new(key, body, hashlib.sha512).hexdigest()
    return body, {"x-paystack-signature": sig, "content-type": "application/json"}


async def _checkout(parent: AsyncClient, invoice_id: str) -> str:
    res = await parent.post(f"/api/fees/invoices/{invoice_id}/paystack")
    assert res.status_code == 200, res.text
    return res.json()["reference"]


async def _ledger_payments(fees_world: FeesWorld, invoice_id: str) -> int:
    detail = (await fees_world.bursar.get(f"/api/fees/invoices/{invoice_id}")).json()
    return sum(1 for e in detail["entries"] if e["kind"] == "payment")


async def test_checkout_charges_full_balance_to_the_schools_subaccount(
    fees_world: FeesWorld, client_for: ClientFactory, paystack: FakePaystack
) -> None:
    """AC8 (unit): full balance, in kobo, split to the school's subaccount."""
    await fees_world.bursar.put(
        "/api/fees/settings",
        json={"paystack_subaccount_code": "ACCT_progress123", "withhold_results_for_debt": True},
    )
    parent = await fees_world.parent(client_for)
    await _checkout(parent, fees_world.invoice_ids[0])
    sent = paystack.initialized[-1]
    assert sent["amount_kobo"] == TUITION_KOBO
    assert sent["subaccount"] == "ACCT_progress123"
    assert sent["callback_url"].endswith("/fees/paid")


async def test_verify_after_return_applies_once(
    fees_world: FeesWorld, client_for: ClientFactory, paystack: FakePaystack
) -> None:
    parent = await fees_world.parent(client_for)
    inv = fees_world.invoice_ids[0]
    ref = await _checkout(parent, inv)
    first = (await parent.post("/api/fees/paystack/verify", json={"reference": ref})).json()
    assert first["status"] == "paid" and first["balance_kobo"] == 0
    again = (await parent.post("/api/fees/paystack/verify", json={"reference": ref})).json()
    assert again["status"] == "paid" and again["receipt_entry_id"] == first["receipt_entry_id"]
    assert await _ledger_payments(fees_world, inv) == 1
    # Nothing left to pay.
    assert (await parent.post(f"/api/fees/invoices/{inv}/paystack")).status_code == 409


async def test_failed_payment_changes_nothing(
    fees_world: FeesWorld, client_for: ClientFactory, paystack: FakePaystack
) -> None:
    parent = await fees_world.parent(client_for)
    inv = fees_world.invoice_ids[0]
    ref = await _checkout(parent, inv)
    paystack.outcomes[ref] = (False, 0)
    res = (await parent.post("/api/fees/paystack/verify", json={"reference": ref})).json()
    assert res["status"] == "failed" and res["balance_kobo"] == TUITION_KOBO
    assert await _ledger_payments(fees_world, inv) == 0


async def test_webhook_replayed_concurrently_applies_exactly_once(
    fees_world: FeesWorld, client_for: ClientFactory, paystack: FakePaystack
) -> None:
    """AC7: the same webhook 5× at once → one ledger entry; then the browser's verify too."""
    parent = await fees_world.parent(client_for)
    inv = fees_world.invoice_ids[0]
    ref = await _checkout(parent, inv)
    body, headers = _signed(
        {"event": "charge.success", "data": {"reference": ref, "amount": TUITION_KOBO}}
    )
    paystack_side = client_for(None)  # no school host, no session: like Paystack itself
    results = await asyncio.gather(
        *[
            paystack_side.post("/api/webhooks/paystack", content=body, headers=headers)
            for _ in range(5)
        ]
    )
    assert [r.status_code for r in results] == [200] * 5
    assert await _ledger_payments(fees_world, inv) == 1
    await parent.post("/api/fees/paystack/verify", json={"reference": ref})
    assert await _ledger_payments(fees_world, inv) == 1
    detail = (await fees_world.bursar.get(f"/api/fees/invoices/{inv}")).json()
    assert detail["balance_kobo"] == 0


async def test_webhook_with_bad_signature_is_rejected_and_not_stored(
    fees_world: FeesWorld, client_for: ClientFactory, paystack: FakePaystack, owner_conn
) -> None:
    parent = await fees_world.parent(client_for)
    ref = await _checkout(parent, fees_world.invoice_ids[0])
    body = json.dumps({"event": "charge.success", "data": {"reference": ref}}).encode()
    res = await client_for(None).post(
        "/api/webhooks/paystack", content=body, headers={"x-paystack-signature": "0" * 128}
    )
    assert res.status_code == 401
    stored = await owner_conn.fetchval(
        "SELECT count(*) FROM paystack_events WHERE reference = $1", ref
    )
    assert stored == 0
    assert await _ledger_payments(fees_world, fees_world.invoice_ids[0]) == 0


async def test_student_can_view_but_not_pay(
    fees_world: FeesWorld, client_for: ClientFactory, paystack: FakePaystack
) -> None:
    from tests.factories import PASSWORD

    student = fees_world.w.students[0]
    c = client_for(fees_world.w.school.slug)
    res = await c.post(
        "/api/auth/student/login", json={"admission_no": student.admission_no, "password": PASSWORD}
    )
    assert res.status_code == 200
    c.headers["x-csrf-token"] = c.cookies.get("dl360_csrf") or ""
    inv = fees_world.invoice_ids[0]
    assert (await c.get(f"/api/fees/invoices/{inv}")).status_code == 200
    assert (await c.post(f"/api/fees/invoices/{inv}/paystack")).status_code == 403
