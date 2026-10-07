"""AC1: every id-taking endpoint, called by school B's admin with school A's real ids.

The expected answer is "not found" (or a validation error for ids in a body): never data,
never a change. A route added without a case here fails `test_every_route_is_covered`.
"""

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.academics.models import House, Subject, Term
from app.auth.models import Role
from tests.conftest import ClientFactory
from tests.factories import make_school, make_staff, make_structure, make_student, tenant_session
from tests.helpers import signed_in

# (method, path template) → body. Path params are filled from school A's ids.
CASES: dict[tuple[str, str], dict | None] = {
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
}


def id_routes(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and "{" in route.path
        for method in route.methods or ()
    }


async def test_every_route_is_covered(app_instance: FastAPI) -> None:
    missing = id_routes(app_instance) - set(CASES)
    assert not missing, f"add isolation cases for: {sorted(missing)}"


async def test_school_b_cannot_touch_school_a(client_for: ClientFactory) -> None:
    a, b = await make_school(), await make_school()
    sa = await make_structure(a)
    await make_structure(b)
    student = await make_student(a, sa)
    teacher = await make_staff(a, Role.TEACHER)
    async with tenant_session(a) as db:
        house = House(school_id=a.id, name="Red")
        subject = Subject(school_id=a.id, name="Maths")
        term = Term(school_id=a.id, academic_session_id=sa.session.id, number=1)
        db.add_all([house, subject, term])
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
    }
    admin_b = await signed_in(client_for, b)
    for (method, path), body in CASES.items():
        url = path.format(**ids)
        res = await admin_b.request(method, url, json=body)
        assert res.status_code == 404, f"{method} {path} → {res.status_code} {res.text}"

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
    assert (await admin_a.get(f"/api/students/{student.id}")).json()["first_name"] == "Ada"
