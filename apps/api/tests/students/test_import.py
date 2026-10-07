"""CSV import (spec R11, AC10)."""

from httpx import AsyncClient

from tests.conftest import ClientFactory
from tests.factories import make_school, make_structure, unique
from tests.helpers import signed_in

HEADER = (
    "admission_no,first_name,middle_name,last_name,gender,date_of_birth,class,arm,house,"
    "guardian_name,guardian_email,guardian_phone,guardian_relationship\n"
)


async def upload(c: AsyncClient, csv: str, *, dry_run: bool) -> dict:
    res = await c.post(
        "/api/students/import",
        files={"file": ("students.csv", csv.encode(), "text/csv")},
        data={"dry_run": "true" if dry_run else "false"},
    )
    assert res.status_code == 200, res.text
    return res.json()


def good_row(i: int, prefix: str) -> str:
    # Every 3 students share a parent (siblings).
    family = i // 3
    return (
        f"{prefix}{i:04d},Ada,,Okafor{i},F,2014-05-21,JSS1,A,,"
        f"Parent {family},parent{family}.{prefix}@example.com,0803{family:07d},Mother\n"
    )


async def test_600_rows_with_5_bad_imports_595_and_reports_the_5(
    client_for: ClientFactory,
) -> None:
    school = await make_school()
    await make_structure(school)
    admin = await signed_in(client_for, school)
    prefix = unique("P").upper()
    rows = [good_row(i, prefix) for i in range(600)]
    rows[9] = rows[9].replace(",Ada,", ",,")  # missing first name (row 11)
    rows[99] = rows[99].replace(",JSS1,A,", ",JSS9,A,")  # unknown class (row 101)
    rows[199] = rows[199].replace("2014-05-21", "21st May")  # bad date (row 201)
    rows[299] = rows[299].replace(",F,", ",X,")  # bad gender (row 301)
    rows[399] = rows[0]  # duplicate admission number (row 401)
    csv = HEADER + "".join(rows)

    preview = await upload(admin, csv, dry_run=True)
    assert preview["total_rows"] == 600 and preview["valid_rows"] == 595
    assert sorted({e["row"] for e in preview["errors"]}) == [11, 101, 201, 301, 401]
    assert preview["students_created"] == 0
    assert (await admin.get("/api/students")).json()["total"] == 0  # dry run saved nothing

    done = await upload(admin, csv, dry_run=False)
    assert done["students_created"] == 595
    assert done["guardians_created"] == 200  # siblings share one parent record
    listing = (await admin.get("/api/students", params={"page_size": 1})).json()
    assert listing["total"] == 595

    # Importing the same file again: every row is now a duplicate.
    again = await upload(admin, csv, dry_run=True)
    assert again["valid_rows"] == 0


async def test_friendly_headers_and_phone_normalisation(client_for: ClientFactory) -> None:
    school = await make_school()
    await make_structure(school)
    admin = await signed_in(client_for, school)
    adm = unique("X").upper()
    csv = (
        "Admission No,Surname,First Name,Class,Arm,Parent Name,Parent Phone\n"
        f"{adm},Eze,Chidi,JSS 1,a,Mr Eze,0803 123 4567\n"
    )
    res = await upload(admin, csv, dry_run=False)
    assert res["errors"] == [] and res["students_created"] == 1
    page = (await admin.get("/api/students", params={"q": adm})).json()
    detail = (await admin.get(f"/api/students/{page['items'][0]['id']}")).json()
    assert detail["class_name"] == "JSS1 A"
    assert detail["guardians"][0]["phone"] == "+2348031234567"


async def test_missing_required_column_is_reported(client_for: ClientFactory) -> None:
    school = await make_school()
    await make_structure(school)
    admin = await signed_in(client_for, school)
    res = await upload(admin, "first_name,last_name\nAda,Okafor\n", dry_run=True)
    assert res["errors"][0]["row"] == 1 and "admission_no" in res["errors"][0]["message"]
