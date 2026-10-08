"""Invoices, the ledger and balances (R19–R21)."""

import re

from tests.conftest import ClientFactory
from tests.fees.conftest import TUITION_KOBO, FeesWorld


async def test_generation_is_idempotent_with_unique_references(fees_world: FeesWorld) -> None:
    bursar = fees_world.bursar
    again = (await bursar.post("/api/fees/invoices/generate", json={})).json()
    assert again == {"created": 0, "already_invoiced": 3, "no_schedule": 0}
    rows = (await bursar.get("/api/fees/invoices")).json()["items"]
    refs = [r["reference"] for r in rows]
    assert len(set(refs)) == 3
    assert all(re.fullmatch(r"[A-Z0-9]+-\d{4}-T1-\d{5}", r) for r in refs), refs
    assert all(r["total_kobo"] == TUITION_KOBO and r["balance_kobo"] == TUITION_KOBO for r in rows)


async def test_adjustments_and_office_payments_move_the_balance(fees_world: FeesWorld) -> None:
    bursar, inv = fees_world.bursar, fees_world.invoice_ids[0]
    res = await bursar.post(
        f"/api/fees/invoices/{inv}/adjustments",
        json={"amount_kobo": -500_000, "note": "Sibling waiver"},
    )
    assert res.json()["balance_kobo"] == TUITION_KOBO - 500_000
    res = await bursar.post(
        f"/api/fees/invoices/{inv}/payments",
        json={"amount_kobo": 1_000_000, "note": "Cash at office"},
    )
    detail = res.json()
    assert detail["balance_kobo"] == TUITION_KOBO - 1_500_000 and detail["paid_kobo"] == 1_000_000
    receipt = next(e for e in detail["entries"] if e["kind"] == "payment")
    assert receipt["receipt_no"].endswith("-1")
    pdf = await bursar.get(f"/api/fees/receipts/{receipt['id']}.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    doc = await bursar.get(f"/api/fees/invoices/{inv}/document.pdf")
    assert doc.status_code == 200 and doc.content.startswith(b"%PDF")
    # The bursar can't fake an online or transfer payment by hand.
    fake = await bursar.post(
        f"/api/fees/invoices/{inv}/payments", json={"amount_kobo": 100, "source": "paystack"}
    )
    assert fake.status_code == 422


async def test_discounts_apply_when_invoicing(
    fees_world: FeesWorld, client_for: ClientFactory
) -> None:
    from tests.factories import make_student

    w, bursar = fees_world.w, fees_world.bursar
    late = await make_student(w.school, w.structure)  # joins after the first invoicing run
    res = await bursar.post(
        "/api/fees/discounts",
        json={"student_id": str(late.id), "percent": 50, "reason": "Scholarship"},
    )
    assert res.status_code == 201
    assert (await bursar.post("/api/fees/invoices/generate", json={})).json()["created"] == 1
    rows = (await bursar.get("/api/fees/invoices", params={"q": late.last_name})).json()["items"]
    mine = next(r for r in rows if r["student_id"] == str(late.id))
    assert mine["total_kobo"] == TUITION_KOBO // 2


async def test_families_see_only_their_own_invoices(
    fees_world: FeesWorld, client_for: ClientFactory
) -> None:
    parent = await fees_world.parent(client_for, 0)
    mine = (await parent.get("/api/fees/mine")).json()
    assert [c["student_id"] for c in mine["children"]] == [str(fees_world.w.students[0].id)]
    other = fees_world.invoice_ids[1]
    assert (await parent.get(f"/api/fees/invoices/{other}")).status_code == 404
    assert (await parent.get("/api/fees/invoices")).status_code == 403  # bursar list
