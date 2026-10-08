"""AC1: every id-taking endpoint, called by school B's admin with school A's real ids.

The expected answer is "not found" (or a validation error for ids in a body): never data,
never a change. A route added without a case here fails `test_every_route_is_covered`.
"""

from datetime import UTC, datetime

from fastapi import FastAPI

from app.academics.models import House, Subject
from app.auth.models import Role
from app.fees.models import (
    EntryKind,
    EntrySource,
    Invoice,
    LedgerEntry,
    StudentDiscount,
    TransferProof,
)
from app.results.models import ReportSnapshot, ResultSheet, SheetStatus
from tests.conftest import ClientFactory
from tests.factories import (
    make_results_world,
    make_school,
    make_staff,
    make_structure,
    tenant_session,
)
from tests.helpers import signed_in

# (method, path template) → body. Path params are filled from school A's ids.
CASES: dict[tuple[str, str], dict | list | str | None] = {
    ("PATCH", "/api/setup/sections/{section_id}"): {"display_name": "Hacked"},
    ("PATCH", "/api/setup/levels/{level_id}"): {"name": "Hacked"},
    ("PATCH", "/api/setup/terms/{term_id}"): {"starts_on": "2030-01-01"},
    ("POST", "/api/setup/terms/{term_id}/make-current"): None,
    ("DELETE", "/api/setup/arms/{arm_id}"): None,
    ("DELETE", "/api/setup/houses/{house_id}"): None,
    ("PUT", "/api/setup/subjects/{subject_id}"): {"name": "Hacked", "level_ids": []},
    ("DELETE", "/api/setup/subjects/{subject_id}"): None,
    ("DELETE", "/api/staff/{user_id}/roles/{role}"): None,
    ("GET", "/api/students/{student_id}"): None,
    ("PATCH", "/api/students/{student_id}"): {"first_name": "Hacked"},
    # Results (M2)
    ("GET", "/api/results/config/{section_id}"): None,
    ("PUT", "/api/results/config/{section_id}/components"): [
        {"name": "All", "short_name": "All", "max_score": 100}
    ],
    ("PUT", "/api/results/config/{section_id}/bands"): [
        {"letter": "A", "descriptor": "All", "min_score": 0, "max_score": 100}
    ],
    ("PUT", "/api/results/config/{section_id}/traits"): [],
    ("PUT", "/api/results/config/{section_id}/comment-slots"): [],
    ("PUT", "/api/results/config/{section_id}/report"): {"template": "standard"},
    ("POST", "/api/results/sheets/{arm_id}/submit"): None,
    ("POST", "/api/results/sheets/{arm_id}/return"): None,
    ("POST", "/api/results/sheets/{arm_id}/approve"): None,
    ("POST", "/api/results/sheets/{arm_id}/publish"): None,
    ("POST", "/api/results/sheets/{arm_id}/unpublish"): {"reason": "Trying another school's data"},
    ("GET", "/api/reports/{snapshot_id}.pdf"): None,
    ("GET", "/api/reports/arm/{arm_id}.pdf"): None,
    ("GET", "/api/portal/snapshots/{snapshot_id}"): None,
    # Fees (M3)
    ("GET", "/api/fees/invoices/{invoice_id}"): None,
    ("GET", "/api/fees/invoices/{invoice_id}/document.pdf"): None,
    ("POST", "/api/fees/invoices/{invoice_id}/adjustments"): {"amount_kobo": -100, "note": "Hack"},
    ("POST", "/api/fees/invoices/{invoice_id}/payments"): {"amount_kobo": 100},
    ("PUT", "/api/fees/invoices/{invoice_id}/results-exempt"): {"exempt": True, "reason": "Hack"},
    ("POST", "/api/fees/invoices/{invoice_id}/paystack"): None,
    ("POST", "/api/fees/invoices/{invoice_id}/proofs"): "MULTIPART",
    ("GET", "/api/fees/receipts/{entry_id}.pdf"): None,
    ("GET", "/api/fees/proofs/{proof_id}/file"): None,
    ("POST", "/api/fees/proofs/{proof_id}/confirm"): {"amount_kobo": 100},
    ("POST", "/api/fees/proofs/{proof_id}/reject"): {"reason": "Not yours"},
    ("DELETE", "/api/fees/discounts/{discount_id}"): None,
    # Public by design, but must not reveal another school's card: answers "not valid".
    ("GET", "/api/public/verify/{snapshot_id}"): None,
}
# Routes whose correct cross-school answer isn't a plain 404.
EXPECT = {("GET", "/api/public/verify/{snapshot_id}"): 200}


def id_routes(app: FastAPI) -> set[tuple[str, str]]:
    """Every (METHOD, path) taking an id, from the OpenAPI document.

    Walking app.routes isn't reliable: newer FastAPI keeps included routers nested.
    """
    return {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if "{" in path
        for method in ops
    }


async def test_every_route_is_covered(app_instance: FastAPI) -> None:
    routes = id_routes(app_instance)
    assert len(routes) >= len(CASES), "route discovery found too few routes"
    missing = routes - set(CASES)
    assert not missing, f"add isolation cases for: {sorted(missing)}"


async def test_school_b_cannot_touch_school_a(client_for: ClientFactory) -> None:
    w = await make_results_world(n_students=1)
    a, sa, student, term = w.school, w.structure, w.students[0], w.term
    b = await make_school()
    await make_structure(b)
    teacher = await make_staff(a, Role.TEACHER)
    async with tenant_session(a) as db:
        house = House(school_id=a.id, name="Red")
        subject = Subject(school_id=a.id, name="Maths")
        sheet = ResultSheet(
            school_id=a.id, arm_id=sa.arm.id, term_id=term.id, status=SheetStatus.PUBLISHED
        )
        db.add_all([house, subject, sheet])
        await db.flush()
        snapshot = ReportSnapshot(
            school_id=a.id, enrollment_id=w.enrollments[0].id, term_id=term.id,
            result_sheet_id=sheet.id, data={"student": {"name": "Ada"}}, sha256="ab" * 32,
            published_at=datetime.now(UTC),
        )  # fmt: skip
        db.add(snapshot)
        invoice = Invoice(school_id=a.id, student_id=student.id, enrollment_id=w.enrollments[0].id,
                          term_id=term.id, reference="A-2627-T1-00001", total_kobo=4_500_000)  # fmt: skip
        db.add(invoice)
        await db.flush()
        entry = LedgerEntry(school_id=a.id, invoice_id=invoice.id, kind=EntryKind.PAYMENT, source=EntrySource.CASH,
                            amount_kobo=100_000, receipt_no="RCT-A-1")  # fmt: skip
        proof = TransferProof(school_id=a.id, invoice_id=invoice.id, claimed_amount_kobo=100_000, file=b"%PDF-1",
                              content_type="application/pdf", sha256="d" * 64)  # fmt: skip
        discount = StudentDiscount(
            school_id=a.id, student_id=student.id, percent=10, reason="Sibling"
        )
        db.add_all([entry, proof, discount])
    ids = {
        "section_id": sa.section.id,
        "level_id": sa.level.id,
        "term_id": term.id,
        "arm_id": sa.arm.id,
        "house_id": house.id,
        "subject_id": subject.id,
        "user_id": teacher.id,
        "role": "teacher",
        "student_id": student.id,
        "snapshot_id": snapshot.id,
        "invoice_id": invoice.id,
        "entry_id": entry.id,
        "proof_id": proof.id,
        "discount_id": discount.id,
    }
    admin_b = await signed_in(client_for, b)
    for (method, path), body in CASES.items():
        url = path.format(**ids)
        params = {"h": snapshot.sha256[:16]} if "verify" in path else None
        if body == "MULTIPART":
            res = await admin_b.request(
                method,
                url,
                files={"file": ("r.pdf", b"%PDF-1", "application/pdf")},
                data={"amount_kobo": "100"},
            )
        else:
            res = await admin_b.request(method, url, json=body, params=params)
        expected = EXPECT.get((method, path), 404)
        assert res.status_code == expected, f"{method} {path} → {res.status_code} {res.text}"
        if "verify" in path:
            assert res.json()["valid"] is False and res.json()["student"] is None

    # Ids inside request bodies.
    checks = [
        ("POST", "/api/setup/arms", {"class_level_id": str(sa.level.id), "name": "Z"}, 404),
        (
            "POST",
            "/api/students",
            {"admission_no": "X1", "first_name": "A", "last_name": "B", "arm_id": str(sa.arm.id)},
            404,
        ),
        ("POST", "/api/students/logins", {"student_ids": [str(student.id)]}, 404),
    ]
    for method, url, body, expected in checks:
        res = await admin_b.request(method, url, json=body)
        assert res.status_code == expected, f"{method} {url} → {res.status_code} {res.text}"

    # And school A's data is untouched.
    admin_a = await signed_in(client_for, a)
    overview = (await admin_a.get("/api/setup/overview")).json()
    assert overview["sections"][0]["display_name"] == "Test Junior Secondary School"
    cfg = (await admin_a.get(f"/api/results/config/{sa.section.id}")).json()
    assert [c["max_score"] for c in cfg["components"]] == [10, 10, 10, 70]
    assert (await admin_a.get(f"/api/students/{student.id}")).json()["first_name"] == "Ada"
    a_invoice = (await admin_a.get(f"/api/fees/invoices/{invoice.id}")).json()
    assert a_invoice["balance_kobo"] == 4_400_000 and a_invoice["results_exempt"] is False
    assert [p["status"] for p in a_invoice["proofs"]] == ["pending"]
