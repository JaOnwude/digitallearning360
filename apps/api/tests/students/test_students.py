from tests.conftest import ClientFactory
from tests.factories import PASSWORD, make_school, make_structure, unique
from tests.helpers import signed_in


async def test_create_edit_and_search_student(client_for: ClientFactory) -> None:
    school = await make_school()
    st = await make_structure(school)
    admin = await signed_in(client_for, school)
    adm = unique("adm")
    res = await admin.post(
        "/api/students",
        json={
            "admission_no": adm,
            "first_name": "Ngozi",
            "last_name": "Eze",
            "arm_id": str(st.arm.id),
            "guardian": {"full_name": "Mrs Eze", "email": "mrs.eze@example.com"},
        },
    )
    assert res.status_code == 201, res.text
    student = res.json()
    assert student["admission_no"] == adm.upper() and student["class_name"] == "JSS1 A"
    assert student["guardians"][0]["email"] == "mrs.eze@example.com"

    dup = await admin.post(
        "/api/students",
        json={"admission_no": adm, "first_name": "X", "last_name": "Y", "arm_id": str(st.arm.id)},
    )
    assert dup.status_code == 409

    res = await admin.patch(f"/api/students/{student['id']}", json={"first_name": "Ngozika"})
    assert res.json()["full_name"] == "Ngozika Eze"
    found = (await admin.get("/api/students", params={"q": "ngozika"})).json()
    assert [s["id"] for s in found["items"]] == [student["id"]]


async def test_login_slips_let_students_sign_in(client_for: ClientFactory) -> None:
    school = await make_school()
    st = await make_structure(school, student_login=True)
    admin = await signed_in(client_for, school)
    res = await admin.post(
        "/api/students",
        json={
            "admission_no": unique("a"),
            "first_name": "Ada",
            "last_name": "Obi",
            "arm_id": str(st.arm.id),
        },
    )
    sid = res.json()["id"]
    [slip] = (await admin.post("/api/students/logins", json={"student_ids": [sid]})).json()
    assert slip["class_name"] == "JSS1 A"

    c = client_for(school.slug)
    login = await c.post(
        "/api/auth/student/login",
        json={"admission_no": slip["admission_no"], "password": slip["temporary_password"]},
    )
    assert login.json()["next"] == "change_password"
    assert (await admin.get(f"/api/students/{sid}")).json()["has_login"] is True
    assert slip["temporary_password"] != PASSWORD
