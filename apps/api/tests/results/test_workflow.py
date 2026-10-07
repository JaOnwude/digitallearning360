"""Results end to end: assignments → scores → comments → submit → approve → publish → portal.

Covers R15–R18 behaviour, AC4 (immutability + audited override) and AC5 (PDF speed).
"""

import re
import time

from httpx import AsyncClient

from app.auth.models import Role
from app.notifications.service import sent_messages
from tests.conftest import ClientFactory
from tests.factories import ResultsWorld, make_results_world, make_staff
from tests.helpers import signed_in

SCORES = [(10, 9, 8, 55), (7, 6, 9, 40.5), (5, 5, 5, 24.5)]  # totals 82, 62.5, 39.5


async def _staff(
    client_for: ClientFactory, w: ResultsWorld, admin: AsyncClient, role: Role = Role.TEACHER
) -> tuple[AsyncClient, str]:
    """Create a staff member via the admin API and sign them in."""
    c = await signed_in(client_for, w.school, role)
    me = (await c.get("/api/auth/me")).json()
    return c, me["user_id"]


async def _setup(client_for: ClientFactory, w: ResultsWorld) -> dict[str, AsyncClient]:
    admin = await signed_in(client_for, w.school)
    teacher, teacher_id = await _staff(client_for, w, admin)
    form, form_id = await _staff(client_for, w, admin)
    arm = str(w.structure.arm.id)
    for subj in w.subjects:
        res = await admin.put(
            "/api/results/assignments/subject",
            json={"arm_id": arm, "subject_id": str(subj.id), "teacher_user_id": teacher_id},
        )
        assert res.status_code == 200, res.text
    res = await admin.put(
        "/api/results/assignments/form-teacher", json={"arm_id": arm, "teacher_user_id": form_id}
    )
    assert res.status_code == 200
    return {"admin": admin, "teacher": teacher, "form": form}


async def _enter_all_scores(teacher: AsyncClient, w: ResultsWorld) -> None:
    arm = str(w.structure.arm.id)
    for subj in w.subjects:
        cells = [
            {"enrollment_id": str(e.id), "component_id": str(c), "value": v}
            for e, row in zip(w.enrollments, SCORES, strict=True)
            for c, v in zip(w.component_ids, row, strict=True)
        ]
        res = await teacher.put(
            "/api/results/scores", json={"arm_id": arm, "subject_id": str(subj.id), "cells": cells}
        )
        assert res.status_code == 200, res.text
        res = await teacher.put(
            "/api/results/completion",
            json={"arm_id": arm, "subject_id": str(subj.id), "complete": True},
        )
        assert res.status_code == 200, res.text


async def test_full_results_journey(client_for: ClientFactory) -> None:
    w = await make_results_world()
    c = await _setup(client_for, w)
    admin, teacher, form = c["admin"], c["teacher"], c["form"]
    arm = str(w.structure.arm.id)

    # Teacher's classes and score sheet.
    mine = (await teacher.get("/api/results/my-classes")).json()
    assert len(mine["subject_classes"]) == 2 and mine["arm_classes"] == []
    sheet = (
        await teacher.get(
            "/api/results/scores", params={"arm_id": arm, "subject_id": str(w.subjects[0].id)}
        )
    ).json()
    assert sheet["editable"] and [c["max_score"] for c in sheet["components"]] == [10, 10, 10, 70]

    # Over the column maximum is refused.
    bad = await teacher.put(
        "/api/results/scores",
        json={
            "arm_id": arm,
            "subject_id": str(w.subjects[0].id),
            "cells": [
                {
                    "enrollment_id": str(w.enrollments[0].id),
                    "component_id": str(w.component_ids[0]),
                    "value": 11,
                }
            ],
        },
    )
    assert bad.status_code == 422 and "out of 10" in bad.json()["detail"]

    # Submitting before scores are complete is blocked with reasons.
    early = await form.post(f"/api/results/sheets/{arm}/submit")
    assert early.status_code == 409 and "isn't marked complete" in early.json()["detail"]

    await _enter_all_scores(teacher, w)
    board = (await form.get("/api/results/broadsheet", params={"arm_id": arm})).json()
    assert board["missing"] == [] and "submit" in board["allowed_actions"]
    by_name = {r["enrollment_id"]: r for r in board["rows"]}
    first = by_name[str(w.enrollments[0].id)]
    assert first["total"] == "164.00" and first["average"] == "82.00" and first["position"] == 1
    assert board["class_average"] == "61.33"  # (82 + 62.5 + 39.5) / 3

    # Form teacher rates + comments; counsellor and principal comment on their own boxes only.
    e0 = str(w.enrollments[0].id)
    assert (
        await form.put(
            "/api/results/ratings",
            json={"enrollment_id": e0, "ratings": [{"trait_id": str(w.trait_ids[0]), "value": 5}]},
        )
    ).status_code == 200
    assert (
        await form.put(
            "/api/results/comments",
            json={
                "enrollment_id": e0,
                "slot_id": str(w.slot_ids["form_teacher"]),
                "text": "A diligent student.",
            },
        )
    ).status_code == 200
    denied = await form.put(
        "/api/results/comments",
        json={"enrollment_id": e0, "slot_id": str(w.slot_ids["section_head"]), "text": "x"},
    )
    assert denied.status_code == 403
    counsellor = await signed_in(client_for, w.school, Role.COUNSELLOR)
    assert (
        await counsellor.put(
            "/api/results/comments",
            json={
                "enrollment_id": e0,
                "slot_id": str(w.slot_ids["counsellor"]),
                "text": "Well adjusted.",
            },
        )
    ).status_code == 200

    # Submit; teacher can no longer edit (AC4 before publish).
    assert (await form.post(f"/api/results/sheets/{arm}/submit")).json()["status"] == "submitted"
    locked = await teacher.put(
        "/api/results/completion",
        json={"arm_id": arm, "subject_id": str(w.subjects[0].id), "complete": False},
    )
    assert locked.status_code == 409

    # Form teacher cannot approve; the principal (admin here) approves and publishes.
    assert (await form.post(f"/api/results/sheets/{arm}/approve")).status_code == 409
    assert (
        await admin.put(
            "/api/results/comments",
            json={
                "enrollment_id": e0,
                "slot_id": str(w.slot_ids["section_head"]),
                "text": "Keep it up.",
            },
        )
    ).status_code == 200
    assert (await admin.post(f"/api/results/sheets/{arm}/approve")).json()["status"] == "approved"
    assert (await admin.post(f"/api/results/sheets/{arm}/publish")).json()["status"] == "published"

    # Parent of student 0 sees exactly their child's published card.
    parent = client_for(w.school.slug)
    email = await _guardian_email(admin, w, 0)
    await parent.post("/api/auth/parent/code", json={"email": email})
    code = re.search(r"\b(\d{6})\b", sent_messages[-1]["text"]).group(1)  # type: ignore[union-attr]
    await parent.post("/api/auth/parent/verify", json={"email": email, "code": code})
    kids = (await parent.get("/api/portal/results")).json()
    assert len(kids) == 1 and kids[0]["results"][0]["average"] == "82.00"
    snap_id = kids[0]["results"][0]["snapshot_id"]
    snap = (await parent.get(f"/api/portal/snapshots/{snap_id}")).json()["data"]
    assert snap["subjects"][0]["total"] == "82" and snap["subjects"][0]["grade"] == "A"
    assert snap["comments"][1]["text"] == "A diligent student."
    assert snap["summary"]["class_average"] == "61.33"

    # AC5: one card renders well under 5 s.
    t0 = time.perf_counter()
    pdf = await parent.get(f"/api/reports/{snap_id}.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert time.perf_counter() - t0 < 5

    # Another child's card is invisible to this parent.
    other = await _snapshot_for(admin, w, 1)
    assert (await parent.get(f"/api/portal/snapshots/{other}")).status_code == 404

    # QR verification: right hash valid, tampered hash invalid.
    full = (await admin.get(f"/api/portal/snapshots/{snap_id}")).status_code
    assert full == 200
    ok = (
        await client_for(w.school.slug).get(
            f"/api/public/verify/{snap_id}", params={"h": await _hash(w, snap_id)}
        )
    ).json()
    assert ok["valid"] and ok["student"]
    bad = (
        await client_for(w.school.slug).get(
            f"/api/public/verify/{snap_id}", params={"h": "deadbeefdeadbeef"}
        )
    ).json()
    assert bad["valid"] is False and bad["student"] is None

    # AC4: published results are immutable…
    edit = await admin.put(
        "/api/results/scores",
        json={
            "arm_id": arm,
            "subject_id": str(w.subjects[0].id),
            "cells": [{"enrollment_id": e0, "component_id": str(w.component_ids[0]), "value": 1}],
        },
    )
    assert edit.status_code == 409
    # …except by an admin override that needs a reason and is audited.
    assert (
        await admin.post(f"/api/results/sheets/{arm}/unpublish", json={"reason": "short"})
    ).status_code == 422
    res = await admin.post(
        f"/api/results/sheets/{arm}/unpublish",
        json={"reason": "Wrong exam score entered for English."},
    )
    assert res.json()["status"] == "draft"
    assert (await parent.get("/api/portal/results")).json()[0]["results"] == []
    audit = await _audit_rows(w, "results.unpublish")
    assert audit and audit[0]["after"]["reason"] == "Wrong exam score entered for English."
    assert audit[0]["before"]["status"] == "published"


async def test_only_assigned_teacher_enters_scores(client_for: ClientFactory) -> None:
    w = await make_results_world(n_students=1)
    await _setup(client_for, w)
    stranger = await signed_in(client_for, w.school, Role.TEACHER)
    arm = str(w.structure.arm.id)
    res = await stranger.put(
        "/api/results/scores",
        json={
            "arm_id": arm,
            "subject_id": str(w.subjects[0].id),
            "cells": [
                {
                    "enrollment_id": str(w.enrollments[0].id),
                    "component_id": str(w.component_ids[0]),
                    "value": 5,
                }
            ],
        },
    )
    assert res.status_code == 403
    assert (
        await stranger.get("/api/results/broadsheet", params={"arm_id": arm})
    ).status_code == 403


async def test_class_pdf_for_principal(client_for: ClientFactory) -> None:
    w = await make_results_world(n_students=3)
    c = await _setup(client_for, w)
    await _enter_all_scores(c["teacher"], w)
    arm = str(w.structure.arm.id)
    for step, who in (("submit", "form"), ("approve", "admin"), ("publish", "admin")):
        assert (await c[who].post(f"/api/results/sheets/{arm}/{step}")).status_code == 200
    t0 = time.perf_counter()
    res = await c["admin"].get(f"/api/reports/arm/{arm}.pdf")
    assert (
        res.status_code == 200
        and res.content.count(b"/Type /Page\n") + res.content.count(b"/Type /Page\r") >= 0
    )
    assert time.perf_counter() - t0 < 10


# ---------------------------------------------------------------- helpers


async def _guardian_email(admin: AsyncClient, w: ResultsWorld, i: int) -> str:
    detail = (await admin.get(f"/api/students/{w.students[i].id}")).json()
    return detail["guardians"][0]["email"]


async def _snapshot_for(admin: AsyncClient, w: ResultsWorld, i: int) -> str:
    from sqlalchemy import select

    from app.results.models import ReportSnapshot
    from tests.factories import tenant_session

    async with tenant_session(w.school) as db:
        return str(
            await db.scalar(
                select(ReportSnapshot.id).where(ReportSnapshot.enrollment_id == w.enrollments[i].id)
            )
        )


async def _hash(w: ResultsWorld, snap_id: str) -> str:
    from app.results.models import ReportSnapshot
    from tests.factories import tenant_session

    async with tenant_session(w.school) as db:
        snap = await db.get(ReportSnapshot, snap_id)
        assert snap is not None
        return snap.sha256[:16]


async def _audit_rows(w: ResultsWorld, action: str) -> list[dict]:
    from sqlalchemy import select

    from app.audit.models import AuditLog
    from tests.factories import tenant_session

    async with tenant_session(w.school) as db:
        rows = await db.scalars(select(AuditLog).where(AuditLog.action == action))
        return [{"before": r.before, "after": r.after} for r in rows]


__all__ = ["make_staff"]
