"""School setup screens' API (spec R8–R10)."""

from app.auth.models import Role
from tests.conftest import ClientFactory
from tests.factories import make_school, make_structure
from tests.helpers import signed_in


async def test_only_admins_can_use_setup(client_for: ClientFactory) -> None:
    school = await make_school()
    await make_structure(school)
    teacher = await signed_in(client_for, school, Role.TEACHER)
    assert (await teacher.get("/api/setup/overview")).status_code == 403


async def test_overview_lists_structure(client_for: ClientFactory) -> None:
    school = await make_school()
    st = await make_structure(school)
    admin = await signed_in(client_for, school)
    body = (await admin.get("/api/setup/overview")).json()
    [section] = body["sections"]
    assert section["display_name"] == "Test Junior Secondary School"
    [level] = section["levels"]
    assert level["name"] == "JSS1" and [a["name"] for a in level["arms"]] == ["A"]
    assert body["active_session_id"] == str(st.session.id)


async def test_arms_houses_and_duplicate_names(client_for: ClientFactory) -> None:
    school = await make_school()
    st = await make_structure(school)
    admin = await signed_in(client_for, school)
    res = await admin.post(
        "/api/setup/arms", json={"class_level_id": str(st.level.id), "name": "B"}
    )
    assert res.status_code == 201
    arms = res.json()["sections"][0]["levels"][0]["arms"]
    assert [a["name"] for a in arms] == ["A", "B"]
    dup = await admin.post(
        "/api/setup/arms", json={"class_level_id": str(st.level.id), "name": "B"}
    )
    assert dup.status_code == 409 and "already has an arm" in dup.json()["detail"]

    house = await admin.post("/api/setup/houses", json={"name": "Blue"})
    assert [h["name"] for h in house.json()["houses"]] == ["Blue"]
    assert (await admin.post("/api/setup/houses", json={"name": "Blue"})).status_code == 409


async def test_sessions_terms_and_current_term(client_for: ClientFactory) -> None:
    school = await make_school()
    await make_structure(school)
    admin = await signed_in(client_for, school)
    bad = await admin.post("/api/setup/sessions", json={"name": "2027/2029"})
    assert bad.status_code == 409
    res = await admin.post("/api/setup/sessions", json={"name": "2027/2028"})
    session = next(s for s in res.json()["sessions"] if s["name"] == "2027/2028")
    assert [t["number"] for t in session["terms"]] == [1, 2, 3]

    term2 = session["terms"][1]["id"]
    res = await admin.post(f"/api/setup/terms/{term2}/make-current")
    current = [t for s in res.json()["sessions"] for t in s["terms"] if t["is_current"]]
    assert [t["id"] for t in current] == [term2]
    res = await admin.patch(
        f"/api/setup/terms/{term2}", json={"starts_on": "2028-01-10", "ends_on": "2028-01-01"}
    )
    assert res.status_code == 409  # ends before it starts


async def test_subjects_mapped_to_levels(client_for: ClientFactory) -> None:
    school = await make_school()
    st = await make_structure(school)
    admin = await signed_in(client_for, school)
    res = await admin.post(
        "/api/setup/subjects", json={"name": "French", "level_ids": [str(st.level.id)]}
    )
    assert res.status_code == 201
    french = next(s for s in res.json()["subjects"] if s["name"] == "French")
    assert res.json()["sections"][0]["levels"][0]["subject_ids"] == [french["id"]]
    res = await admin.put(
        f"/api/setup/subjects/{french['id']}", json={"name": "French", "level_ids": []}
    )
    assert res.json()["sections"][0]["levels"][0]["subject_ids"] == []


async def test_cannot_use_another_schools_ids(client_for: ClientFactory) -> None:
    """Even when an id is valid elsewhere, it's invisible here (AC1)."""
    a, b = await make_school(), await make_school()
    sa = await make_structure(a)
    await make_structure(b)
    admin_b = await signed_in(client_for, b)
    res = await admin_b.post(
        "/api/setup/arms", json={"class_level_id": str(sa.level.id), "name": "Z"}
    )
    assert res.status_code == 404
    res = await admin_b.post(
        "/api/setup/subjects", json={"name": "Spy", "level_ids": [str(sa.level.id)]}
    )
    assert res.status_code == 422
