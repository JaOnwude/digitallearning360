from app.auth.models import Role
from tests.conftest import ClientFactory
from tests.factories import make_school, unique
from tests.helpers import signed_in


async def test_admin_adds_staff_with_one_time_temporary_password(
    client_for: ClientFactory,
) -> None:
    school = await make_school()
    admin = await signed_in(client_for, school)
    email = f"{unique('t')}@example.com"
    res = await admin.post(
        "/api/staff", json={"full_name": "Mr Teacher", "email": email, "role": "teacher"}
    )
    assert res.status_code == 201
    temp = res.json()["temporary_password"]
    assert temp

    # The new teacher signs in with it and must change it.
    c = client_for(school.slug)
    login = await c.post("/api/auth/staff/login", json={"email": email, "password": temp})
    assert login.json()["next"] == "change_password"

    # Same person, second role: no new password.
    res = await admin.post(
        "/api/staff", json={"full_name": "Mr Teacher", "email": email, "role": "counsellor"}
    )
    assert res.json()["temporary_password"] is None
    assert {r["role"] for r in res.json()["staff"]["roles"]} == {"teacher", "counsellor"}
    dup = await admin.post(
        "/api/staff", json={"full_name": "Mr Teacher", "email": email, "role": "teacher"}
    )
    assert dup.status_code == 409


async def test_staff_list_and_role_removal(client_for: ClientFactory) -> None:
    school = await make_school()
    admin = await signed_in(client_for, school)
    res = await admin.post(
        "/api/staff",
        json={"full_name": "Bursar", "email": f"{unique('b')}@example.com", "role": "bursar"},
    )
    user_id = res.json()["staff"]["user_id"]
    names = [s["full_name"] for s in (await admin.get("/api/staff")).json()]
    assert "Bursar" in names
    assert (await admin.delete(f"/api/staff/{user_id}/roles/bursar")).status_code == 204
    assert (await admin.delete(f"/api/staff/{user_id}/roles/bursar")).status_code == 404


async def test_admin_cannot_remove_own_admin_role(client_for: ClientFactory) -> None:
    school = await make_school()
    admin = await signed_in(client_for, school)
    me = (await admin.get("/api/auth/me")).json()
    res = await admin.delete(f"/api/staff/{me['user_id']}/roles/school_admin")
    assert res.status_code == 409


async def test_section_head_needs_a_section(client_for: ClientFactory) -> None:
    school = await make_school()
    admin = await signed_in(client_for, school)
    res = await admin.post(
        "/api/staff",
        json={
            "full_name": "Head",
            "email": f"{unique('h')}@example.com",
            "role": Role.SECTION_HEAD,
        },
    )
    assert res.status_code == 422
