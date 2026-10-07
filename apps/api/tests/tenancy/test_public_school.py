from tests.conftest import ClientFactory
from tests.factories import make_school, make_structure


async def test_public_school_shows_only_its_own_sections(client_for: ClientFactory) -> None:
    a, b = await make_school(), await make_school()
    await make_structure(a, student_login=True)
    res = await client_for(a.slug).get("/api/public/school")
    assert res.status_code == 200
    body = res.json()
    assert body["slug"] == a.slug
    assert [s["student_login_enabled"] for s in body["sections"]] == [True]
    other = (await client_for(b.slug).get("/api/public/school")).json()
    assert other["slug"] == b.slug and other["sections"] == []
