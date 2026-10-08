"""Bank-transfer proofs (R23, AC9) and results withholding (R18, AC6)."""

from httpx import AsyncClient

from tests.conftest import ClientFactory
from tests.fees.conftest import TUITION_KOBO, FeesWorld

JPEG = b"\xff\xd8\xff\xe0" + b"fake transfer receipt" * 20
PNG = b"\x89PNG\r\n\x1a\n" + b"another receipt" * 20


async def _upload(
    parent: AsyncClient, invoice_id: str, content: bytes, ref: str | None = "FT2610081234"
) -> dict:
    data = {"amount_kobo": str(TUITION_KOBO)}
    if ref:
        data["bank_reference"] = ref
    res = await parent.post(
        f"/api/fees/invoices/{invoice_id}/proofs",
        files={"file": ("receipt.jpg", content, "image/jpeg")},
        data=data,
    )
    assert res.status_code == 201, res.text
    return res.json()


async def test_confirmed_proof_creates_exactly_one_payment(
    fees_world: FeesWorld, client_for: ClientFactory
) -> None:
    """AC9: one ledger entry, for the amount the bursar saw arrive."""
    parent, bursar = await fees_world.parent(client_for), fees_world.bursar
    inv = fees_world.invoice_ids[0]
    proof = await _upload(parent, inv, JPEG)
    assert proof["status"] == "pending" and proof["duplicate_of"] is None
    queue = (await bursar.get("/api/fees/proofs")).json()
    assert [p["id"] for p in queue] == [proof["id"]]
    file = await bursar.get(f"/api/fees/proofs/{proof['id']}/file")
    assert file.status_code == 200 and file.headers["content-type"] == "image/jpeg"

    res = await bursar.post(
        f"/api/fees/proofs/{proof['id']}/confirm", json={"amount_kobo": 4_000_000}
    )
    assert res.json()["status"] == "confirmed"
    again = await bursar.post(
        f"/api/fees/proofs/{proof['id']}/confirm", json={"amount_kobo": 4_000_000}
    )
    assert again.status_code == 409
    detail = (await bursar.get(f"/api/fees/invoices/{inv}")).json()
    assert [e["amount_kobo"] for e in detail["entries"] if e["kind"] == "payment"] == [4_000_000]
    assert detail["balance_kobo"] == TUITION_KOBO - 4_000_000


async def test_duplicates_are_flagged_and_rejection_changes_nothing(
    fees_world: FeesWorld, client_for: ClientFactory
) -> None:
    parent, bursar = await fees_world.parent(client_for), fees_world.bursar
    inv = fees_world.invoice_ids[0]
    first = await _upload(parent, inv, JPEG)
    same_file = await _upload(parent, inv, JPEG, ref=None)
    same_ref = await _upload(parent, inv, PNG, ref="FT2610081234")
    assert same_file["duplicate_of"] == first["id"] and same_ref["duplicate_of"] == first["id"]
    res = await bursar.post(
        f"/api/fees/proofs/{same_file['id']}/reject", json={"reason": "Duplicate upload"}
    )
    assert res.json()["status"] == "rejected"
    detail = (await bursar.get(f"/api/fees/invoices/{inv}")).json()
    assert detail["balance_kobo"] == TUITION_KOBO


async def test_only_images_and_pdfs_are_accepted(
    fees_world: FeesWorld, client_for: ClientFactory
) -> None:
    parent = await fees_world.parent(client_for)
    res = await parent.post(
        f"/api/fees/invoices/{fees_world.invoice_ids[0]}/proofs",
        files={"file": ("receipt.jpg", b"<html>not an image</html>", "image/jpeg")},
        data={"amount_kobo": "100"},
    )
    assert res.status_code == 415


async def test_results_withheld_until_paid(
    fees_world: FeesWorld, client_for: ClientFactory
) -> None:
    """AC6: a balance hides published results; paying lifts it at once. Exemption also works."""
    from sqlalchemy import select

    from app.results.models import ReportSnapshot, ResultSheet, SheetStatus
    from tests.factories import tenant_session

    w = fees_world.w
    from datetime import UTC, datetime

    async with tenant_session(w.school) as db:
        sheet = ResultSheet(
            school_id=w.school.id,
            arm_id=w.structure.arm.id,
            term_id=w.term.id,
            status=SheetStatus.PUBLISHED,
        )
        db.add(sheet)
        await db.flush()
        snap = ReportSnapshot(
            school_id=w.school.id, enrollment_id=w.enrollments[0].id, term_id=w.term.id, result_sheet_id=sheet.id,
            data={"student": {"name": "Ada", "admission_no": "A1", "class_label": "JSS1 A"},
                  "term": {"label": "First Term", "session": "2026/2027"}, "summary": {"average": "70.00"}},
            sha256="c" * 64, published_at=datetime.now(UTC),
        )  # fmt: skip
        db.add(snap)
        await db.flush()
        snap_id = str(snap.id)
        assert await db.scalar(select(ReportSnapshot.id).where(ReportSnapshot.id == snap.id))

    parent = await fees_world.parent(client_for)
    kids = (await parent.get("/api/portal/results")).json()
    row = kids[0]["results"][0]
    assert row["withheld"] is True and row["withheld_balance_kobo"] == TUITION_KOBO
    assert row["average"] is None  # nothing from a withheld card leaks
    blocked = await parent.get(f"/api/portal/snapshots/{snap_id}")
    assert blocked.status_code == 403
    assert "outstanding balance ₦45,000" in blocked.json()["detail"]
    assert (await parent.get(f"/api/reports/{snap_id}.pdf")).status_code == 403

    # Exemption lifts it…
    inv = fees_world.invoice_ids[0]
    await fees_world.bursar.put(
        f"/api/fees/invoices/{inv}/results-exempt",
        json={"exempt": True, "reason": "Payment plan agreed"},
    )
    assert (await parent.get(f"/api/portal/snapshots/{snap_id}")).status_code == 200
    await fees_world.bursar.put(
        f"/api/fees/invoices/{inv}/results-exempt", json={"exempt": False, "reason": "Plan ended"}
    )
    assert (await parent.get(f"/api/portal/snapshots/{snap_id}")).status_code == 403
    # …and so does paying in full.
    await fees_world.bursar.post(
        f"/api/fees/invoices/{inv}/payments", json={"amount_kobo": TUITION_KOBO}
    )
    assert (await parent.get(f"/api/portal/snapshots/{snap_id}")).status_code == 200
    row = (await parent.get("/api/portal/results")).json()[0]["results"][0]
    assert row["withheld"] is False and row["withheld_balance_kobo"] == 0
    assert row["average"] == "70.00"
