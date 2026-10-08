"""Login flows (spec R4–R7, AC2)."""

import re

import pyotp
import pytest
from fastapi import Depends, FastAPI
from httpx import AsyncClient

from app.auth.deps import CurrentPrincipal, Principal, require_roles
from app.auth.models import Role
from app.notifications.service import sent_messages
from tests.conftest import ClientFactory
from tests.factories import (
    PASSWORD,
    make_school,
    make_staff,
    make_structure,
    make_student,
    totp_now,
    unique,
)


@pytest.fixture
def protected(app_instance: FastAPI) -> None:
    """Test-only endpoints standing in for real feature endpoints."""

    async def any_user(p: CurrentPrincipal) -> dict[str, str]:
        return {"user": p.session.user_id}

    async def admin_only(p: Principal = Depends(require_roles(Role.SCHOOL_ADMIN))) -> dict:  # noqa: B008
        return {"ok": "yes"}

    app_instance.add_api_route("/api/_test/me", any_user)
    app_instance.add_api_route("/api/_test/admin", admin_only)
    app_instance.add_api_route("/api/_test/mutate", any_user, methods=["POST"])


def csrf(c: AsyncClient) -> dict[str, str]:
    return {"x-csrf-token": c.cookies.get("dl360_csrf") or ""}


async def staff_login(c: AsyncClient, email: str, password: str = PASSWORD) -> str:
    res = await c.post("/api/auth/staff/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["next"]


# ---------------------------------------------------------------- staff


async def test_teacher_logs_in_without_two_factor(
    client_for: ClientFactory, protected: None
) -> None:
    school = await make_school()
    teacher = await make_staff(school, Role.TEACHER)
    c = client_for(school.slug)
    assert await staff_login(c, teacher.email or "") == "done"
    assert (await c.get("/api/_test/me")).status_code == 200
    me = (await c.get("/api/auth/me")).json()
    assert me["roles"] == ["teacher"] and me["kind"] == "staff"
    # A teacher is not an admin.
    assert (await c.get("/api/_test/admin")).status_code == 403


async def test_wrong_password_is_generic_401(client_for: ClientFactory) -> None:
    school = await make_school()
    teacher = await make_staff(school)
    c = client_for(school.slug)
    res = await c.post(
        "/api/auth/staff/login", json={"email": teacher.email, "password": "nope-nope"}
    )
    assert res.status_code == 401
    res = await c.post(
        "/api/auth/staff/login", json={"email": "ghost@example.com", "password": "nope-nope"}
    )
    assert res.status_code == 401


async def test_admin_must_enroll_two_factor_before_access(
    client_for: ClientFactory, protected: None
) -> None:
    school = await make_school()
    admin = await make_staff(school, Role.SCHOOL_ADMIN)
    c = client_for(school.slug)
    assert await staff_login(c, admin.email or "") == "totp_enroll"
    blocked = await c.get("/api/_test/admin")
    assert blocked.status_code == 403 and blocked.json()["detail"] == "two_factor_required"

    enroll = await c.post("/api/auth/totp/enroll", headers=csrf(c))
    assert enroll.status_code == 200
    secret = pyotp.parse_uri(enroll.json()["otpauth_uri"]).secret
    assert enroll.json()["qr_svg_data_uri"].startswith("data:image/svg+xml")

    bad = await c.post("/api/auth/totp/verify", json={"code": "000000"}, headers=csrf(c))
    assert bad.status_code == 400
    ok = await c.post("/api/auth/totp/verify", json={"code": totp_now(secret)}, headers=csrf(c))
    assert ok.status_code == 200
    assert ok.json()["next"] == "done" and len(ok.json()["recovery_codes"]) == 8
    assert (await c.get("/api/_test/admin")).status_code == 200


async def test_enrolled_admin_verifies_code_or_single_use_recovery_code(
    client_for: ClientFactory,
) -> None:
    school = await make_school()
    secret = pyotp.random_base32()
    admin = await make_staff(school, Role.SCHOOL_ADMIN, totp_secret=secret)
    c = client_for(school.slug)
    assert await staff_login(c, admin.email or "") == "totp_verify"
    code = totp_now(secret)
    res = await c.post("/api/auth/totp/verify", json={"code": code}, headers=csrf(c))
    assert res.json()["next"] == "done" and res.json()["recovery_codes"] is None

    # The same code can't be used again, even from a fresh sign-in (ASVS 2.8.4).
    again = client_for(school.slug)
    assert await staff_login(again, admin.email or "") == "totp_verify"
    replay = await again.post("/api/auth/totp/verify", json={"code": code}, headers=csrf(again))
    assert replay.status_code == 400 and "already used" in replay.json()["detail"]


async def test_session_is_only_valid_on_its_own_school(
    client_for: ClientFactory, protected: None
) -> None:
    a, b = await make_school(), await make_school()
    teacher = await make_staff(a)
    on_a = client_for(a.slug)
    await staff_login(on_a, teacher.email or "")
    # Same cookie jar, different school host (e.g. a stolen cookie replayed elsewhere).
    on_b = client_for(b.slug)
    on_b.cookies = on_a.cookies
    assert (await on_b.get("/api/_test/me")).status_code == 401
    # And staff of A cannot log in to B at all.
    res = await on_b.post(
        "/api/auth/staff/login", json={"email": teacher.email, "password": PASSWORD}
    )
    assert res.status_code == 401


async def test_mutations_require_csrf_token(client_for: ClientFactory, protected: None) -> None:
    school = await make_school()
    teacher = await make_staff(school)
    c = client_for(school.slug)
    await staff_login(c, teacher.email or "")
    assert (await c.post("/api/_test/mutate")).status_code == 403
    assert (await c.post("/api/_test/mutate", headers=csrf(c))).status_code == 200


async def test_logout_ends_session(client_for: ClientFactory, protected: None) -> None:
    school = await make_school()
    teacher = await make_staff(school)
    c = client_for(school.slug)
    await staff_login(c, teacher.email or "")
    assert (await c.post("/api/auth/logout")).status_code == 204
    assert (await c.get("/api/_test/me")).status_code == 401


async def test_login_is_rate_limited(client_for: ClientFactory) -> None:
    school = await make_school()
    teacher = await make_staff(school)
    c = client_for(school.slug)
    codes = [
        (
            await c.post(
                "/api/auth/staff/login", json={"email": teacher.email, "password": "wrong-pass"}
            )
        ).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10 and codes[10] == 429


# ---------------------------------------------------------------- parents


def last_code() -> str:
    match = re.search(r"\b(\d{6})\b", sent_messages[-1]["text"])
    assert match
    return match.group(1)


async def test_parent_signs_in_with_single_use_email_code(
    client_for: ClientFactory, protected: None
) -> None:
    school = await make_school()
    structure = await make_structure(school)
    email = f"{unique('parent')}@example.com"
    await make_student(school, structure, guardian_email=email)
    c = client_for(school.slug)

    res = await c.post("/api/auth/parent/code", json={"email": email})
    assert res.status_code == 202 and len(sent_messages) == 1
    code = last_code()
    ok = await c.post("/api/auth/parent/verify", json={"email": email, "code": code})
    assert ok.status_code == 200 and ok.json()["next"] == "done"
    me = (await c.get("/api/auth/me")).json()
    assert me["kind"] == "parent" and me["roles"] == ["parent"]
    # Single use.
    again = await client_for(school.slug).post(
        "/api/auth/parent/verify", json={"email": email, "code": code}
    )
    assert again.status_code == 400


async def test_parent_code_not_sent_for_unknown_email(client_for: ClientFactory) -> None:
    school = await make_school()
    res = await client_for(school.slug).post(
        "/api/auth/parent/code", json={"email": "stranger@example.com"}
    )
    assert res.status_code == 202  # same response either way: no email discovery
    assert sent_messages == []


async def test_parent_code_locks_after_five_wrong_attempts(client_for: ClientFactory) -> None:
    school = await make_school()
    structure = await make_structure(school)
    email = f"{unique('parent')}@example.com"
    await make_student(school, structure, guardian_email=email)
    c = client_for(school.slug)
    await c.post("/api/auth/parent/code", json={"email": email})
    right = last_code()
    wrong = "000000" if right != "000000" else "111111"
    statuses = [
        (await c.post("/api/auth/parent/verify", json={"email": email, "code": wrong})).status_code
        for _ in range(5)
    ]
    assert statuses == [400, 400, 400, 400, 429]
    # The real code no longer works either.
    res = await c.post("/api/auth/parent/verify", json={"email": email, "code": right})
    assert res.status_code == 400


# ---------------------------------------------------------------- students


async def test_student_with_temporary_password_must_change_it(
    client_for: ClientFactory, protected: None
) -> None:
    school = await make_school()
    structure = await make_structure(school, student_login=True)
    student = await make_student(school, structure, must_change_password=True)
    c = client_for(school.slug)
    res = await c.post(
        "/api/auth/student/login",
        json={"admission_no": student.admission_no.lower(), "password": PASSWORD},
    )
    assert res.status_code == 200 and res.json()["next"] == "change_password"
    blocked = await c.get("/api/_test/me")
    assert blocked.status_code == 403 and blocked.json()["detail"] == "password_change_required"

    weak = await c.post(
        "/api/auth/password/change", json={"new_password": "12345678"}, headers=csrf(c)
    )
    assert weak.status_code == 400
    ok = await c.post(
        "/api/auth/password/change", json={"new_password": "a-better-pass-9"}, headers=csrf(c)
    )
    assert ok.status_code == 200 and ok.json()["next"] == "done"
    assert (await c.get("/api/_test/me")).status_code == 200


async def test_student_login_respects_section_setting(client_for: ClientFactory) -> None:
    school = await make_school()
    structure = await make_structure(school, student_login=False)
    student = await make_student(school, structure)
    res = await client_for(school.slug).post(
        "/api/auth/student/login",
        json={"admission_no": student.admission_no, "password": PASSWORD},
    )
    assert res.status_code == 403
