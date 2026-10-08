"""Build a fresh database for the browser end-to-end tests (e2e/), then print its accounts.

Run by e2e/global-setup.ts; never against a real database. It recreates `dl360_e2e`
(refusing any other name), migrates it, and creates one school ("e2e"):

- JSS1 A: two students with published results (scores via the API, submitted, approved,
  published). Fees are set up but not invoiced: the bursar issues invoices in the browser.
- JSS1 B: one student, no scores yet: the teacher enters them in the browser.
- Staff: admin and bursar (two-step sign-in with known secrets), a subject teacher and a
  form teacher. Student 1 must change their password at first sign-in.

    uv run python -m tests.e2e_world <output.json>
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
import pyotp
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

E2E_DB = "dl360_e2e"
SLUG = "e2e"
SCHOOL = "Unity Model College"
API_DIR = Path(__file__).resolve().parents[1]
INIT_SQL = API_DIR.parents[1] / "infra" / "postgres-init.sql"
SCORES = [(10, 9, 8, 55), (7, 6, 9, 40.5)]  # totals 82 and 62.5


def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def recreate_database() -> None:
    owner_url = os.environ["DL360_MIGRATION_DATABASE_URL"]
    if (
        not owner_url.rstrip("/").endswith(f"/{E2E_DB}")
        or E2E_DB not in os.environ["DL360_DATABASE_URL"]
    ):
        raise SystemExit(f"Refusing to run: the e2e database must be named {E2E_DB}")
    maintenance = _plain(owner_url).rsplit("/", 1)[0] + "/postgres"
    conn = await asyncpg.connect(maintenance)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{E2E_DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{E2E_DB}"')
    finally:
        await conn.close()
    conn = await asyncpg.connect(_plain(owner_url))
    try:
        await conn.execute(INIT_SQL.read_text(encoding="utf-8"))
    finally:
        await conn.close()
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    await asyncio.to_thread(command.upgrade, cfg, "head")


async def build() -> dict[str, object]:
    from app.academics.models import Arm
    from app.auth.models import Role, User
    from app.core.redis import get_redis
    from app.fees.models import FeeItem, FeeScheduleEntry
    from app.main import create_app
    from app.students.models import Guardian, Student, StudentGuardian
    from app.tenancy.models import School
    from tests.factories import (
        PASSWORD,
        Structure,
        make_results_world,
        make_staff,
        make_student,
        tenant_session,
        totp_now,
    )

    await get_redis().flushdb()
    if outbox := os.environ.get("DL360_EMAIL_OUTBOX_FILE"):
        Path(outbox).write_text("", encoding="utf-8")  # noqa: ASYNC240 - setup script
    w = await make_results_world(n_students=2, slug=SLUG)
    names = [("Adaeze", "Nwosu"), ("Chinedu", "Eze")]
    async with tenant_session(w.school) as db:
        await db.execute(update(School).where(School.id == w.school.id).values(
            name=SCHOOL,
            settings={"fees": {"bank_name": "Test Bank", "account_name": "Unity Model College Fees",
                                "account_number": "0123456789", "withhold_results_for_debt": True}},
        ))  # fmt: skip
        for student, (first, last) in zip(w.students, names, strict=True):
            await db.execute(
                update(Student)
                .where(Student.id == student.id)
                .values(first_name=first, last_name=last)
            )
        await db.execute(  # student 1 changes their password at first sign-in (AC2)
            update(User).where(User.id == w.students[0].user_id).values(must_change_password=True)
        )
        arm_b = Arm(school_id=w.school.id, class_level_id=w.structure.level.id,
                    academic_session_id=w.structure.session.id, name="B")  # fmt: skip
        db.add(arm_b)
        item = FeeItem(school_id=w.school.id, name="Tuition")
        db.add(item)
        await db.flush()
        db.add(FeeScheduleEntry(school_id=w.school.id, fee_item_id=item.id, class_level_id=w.structure.level.id,
                                term_id=w.term.id, amount_kobo=4_500_000))  # fmt: skip
    b = Structure(w.structure.section, w.structure.level, w.structure.session, arm_b)
    student_b = await make_student(w.school, b, with_login=False)
    async with tenant_session(w.school) as db:
        await db.execute(
            update(Student)
            .where(Student.id == student_b.id)
            .values(first_name="Bisi", last_name="Ade")
        )

    secrets = {"admin": pyotp.random_base32(), "bursar": pyotp.random_base32()}
    admin = await make_staff(w.school, Role.SCHOOL_ADMIN, totp_secret=secrets["admin"])
    bursar = await make_staff(w.school, Role.BURSAR, totp_secret=secrets["bursar"])
    teacher = await make_staff(w.school, Role.TEACHER)
    form = await make_staff(w.school, Role.TEACHER)

    app = create_app()
    proxy = {"x-dl360-proxy-key": os.environ["DL360_PROXY_KEY"],
             "x-dl360-host": f"{SLUG}.{os.environ['DL360_BASE_DOMAIN']}"}  # fmt: skip

    async def client(user: User, secret: str | None = None) -> AsyncClient:
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://e2e", headers=proxy)
        res = await c.post(
            "/api/auth/staff/login", json={"email": user.email, "password": PASSWORD}
        )
        assert res.status_code == 200, res.text
        c.headers["x-csrf-token"] = c.cookies.get("dl360_csrf") or ""
        if secret:
            assert (
                await c.post("/api/auth/totp/verify", json={"code": totp_now(secret)})
            ).status_code == 200
        return c

    admin_c, teacher_c, form_c = (
        await client(admin, secrets["admin"]),
        await client(teacher),
        await client(form),
    )
    for arm in (w.structure.arm.id, arm_b.id):
        for subj in w.subjects:
            res = await admin_c.put("/api/results/assignments/subject", json={
                "arm_id": str(arm), "subject_id": str(subj.id), "teacher_user_id": str(teacher.id)})  # fmt: skip
            assert res.status_code == 200, res.text
    res = await admin_c.put("/api/results/assignments/form-teacher",
                            json={"arm_id": str(w.structure.arm.id), "teacher_user_id": str(form.id)})  # fmt: skip
    assert res.status_code == 200, res.text

    arm_a = str(w.structure.arm.id)
    for subj in w.subjects:
        cells = [{"enrollment_id": str(e.id), "component_id": str(c), "value": v}
                 for e, row in zip(w.enrollments, SCORES, strict=True)
                 for c, v in zip(w.component_ids, row, strict=True)]  # fmt: skip
        for path, body in (
            ("/api/results/scores", {"arm_id": arm_a, "subject_id": str(subj.id), "cells": cells}),
            (
                "/api/results/completion",
                {"arm_id": arm_a, "subject_id": str(subj.id), "complete": True},
            ),
        ):
            res = await teacher_c.put(path, json=body)
            assert res.status_code == 200, res.text
    for actor, step in ((form_c, "submit"), (admin_c, "approve"), (admin_c, "publish")):
        res = await actor.post(f"/api/results/sheets/{arm_a}/{step}")
        assert res.status_code == 200, f"{step}: {res.text}"
    for c in (admin_c, teacher_c, form_c):
        await c.aclose()
    # Forget setup's sessions and used 2FA codes, so the browser can use this window's code.
    await get_redis().flushdb()

    async with tenant_session(w.school) as db:
        parent_email = await db.scalar(
            select(Guardian.email)
            .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
            .where(StudentGuardian.student_id == w.students[0].id)
        )
        admission_no = await db.scalar(
            select(Student.admission_no).where(Student.id == w.students[0].id)
        )

    return {
        "slug": SLUG,
        "school": SCHOOL,
        "password": PASSWORD,
        "admin": {"email": admin.email, "totp": secrets["admin"]},
        "bursar": {"email": bursar.email, "totp": secrets["bursar"]},
        "teacher": {"email": teacher.email},
        "parent": {"email": parent_email, "child": "Adaeze Nwosu", "other_child": "Chinedu Eze"},
        "student": {"admission_no": admission_no, "name": "Adaeze Nwosu"},
        "arm_b": {"id": str(arm_b.id), "label": "JSS1 B", "student": "Bisi Ade"},
        "subjects": [s.name for s in w.subjects],
    }


async def main() -> dict[str, object]:
    await recreate_database()
    world = await build()
    from app.core.redis import close_redis
    from app.db.session import dispose_engine

    await dispose_engine()
    await close_redis()
    return world


if __name__ == "__main__":
    world = asyncio.run(main())
    Path(sys.argv[1]).write_text(json.dumps(world, indent=2), encoding="utf-8")
