"""Create or update a school from a TOML file (spec R3: schools are set up by script in the pilot).

Usage:
    uv run python -m app.scripts.seed_school seeds/progress-jss.toml \
        --admin-email head@school.ng --admin-name "Mrs Principal"

Idempotent: records are matched by their natural keys and only created when missing.
A new admin gets a temporary password (printed once) and must change it and set up
two-factor at first sign-in.
"""

import argparse
import asyncio
import secrets
import tomllib
import uuid
from itertools import pairwise
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import (
    AcademicSession,
    Arm,
    ClassLevel,
    LevelSubject,
    Section,
    SectionKind,
    Subject,
    Term,
)
from app.auth.models import Membership, Role, User
from app.auth.passwords import hash_password
from app.db.session import dispose_engine, get_sessionmaker
from app.fees.models import FeeItem, FeeScheduleEntry
from app.results import config as rconfig
from app.results.config import BandSpec, ComponentSpec
from app.results.models import AssessmentComponent, CommentAuthor
from app.tenancy.deps import set_tenant
from app.tenancy.models import School


async def _get_or_create[T](
    db: AsyncSession, model: type[T], defaults: dict[str, Any], **keys: Any
) -> T:
    row = await db.scalar(select(model).filter_by(**keys))
    if row is None:
        row = model(**keys, **defaults)
        db.add(row)
        await db.flush()
    return row


async def _seed_results_config(
    db: AsyncSession, school_id: uuid.UUID, section: Section, sec: dict[str, Any]
) -> None:
    """Score columns, grades, traits, comment slots and report settings for a section.

    Uses the file's values when given; otherwise platform defaults, but only for a section
    that has none yet (never overwrites what a school configured in Setup).
    """
    has_components = await db.scalar(
        select(func.count())
        .select_from(AssessmentComponent)
        .where(AssessmentComponent.section_id == section.id)
    )
    if "assessment_components" in sec:
        specs = [ComponentSpec(**c) for c in sec["assessment_components"]]
        await rconfig.set_components(db, school_id, section, specs)
    elif not has_components:
        await rconfig.set_components(db, school_id, section, rconfig.DEFAULT_COMPONENTS)
        await rconfig.set_bands(db, school_id, section, rconfig.default_bands(sec["kind"]))
        await rconfig.set_comment_slots(db, school_id, section, rconfig.DEFAULT_SLOTS)
    if "grading_bands" in sec:
        await rconfig.set_bands(
            db, school_id, section, [BandSpec(**b) for b in sec["grading_bands"]]
        )
    if "comment_slots" in sec:
        slots = [(c["label"], CommentAuthor(c["author_role"])) for c in sec["comment_slots"]]
        await rconfig.set_comment_slots(db, school_id, section, slots)
    if "trait_groups" in sec:
        groups = [(g["name"], list(g["traits"])) for g in sec["trait_groups"]]
        await rconfig.set_traits(db, school_id, section, groups)
    if "report_config" in sec:
        section.report_config = dict(sec["report_config"])


async def seed(
    config: dict[str, Any], admin_email: str | None, admin_name: str, base_dir: Path
) -> None:
    s = config["school"]
    async with get_sessionmaker()() as db, db.begin():
        school = await db.scalar(select(School).where(School.slug == s["slug"]))
        if school is None:
            school = School(slug=s["slug"], name=s["name"])
            db.add(school)
        school.name = s["name"]
        school.motto = s.get("motto")
        school.address = s.get("address")
        school.branding = s.get("branding", {})
        # Merge, never replace: settings edited in the app (bank details…) survive re-seeding.
        school.settings = {**(school.settings or {}), **s.get("settings", {})}
        if "logo_file" in s:
            logo = (base_dir / s["logo_file"]).resolve()
            school.logo = logo.read_bytes()
            school.logo_content_type = "image/png" if logo.suffix == ".png" else "image/jpeg"
        await db.flush()
        await set_tenant(db, school)
        sid = school.id

        subjects: dict[str, Subject] = {}
        for sort, sec in enumerate(config.get("sections", [])):
            section = await _get_or_create(
                db,
                Section,
                {
                    "display_name": sec["display_name"],
                    "kind": SectionKind(sec["kind"]),
                    "student_login_enabled": sec.get("student_login_enabled", False),
                    "sort": sort,
                },
                school_id=sid,
                name=sec["name"],
            )
            levels = [
                await _get_or_create(
                    db, ClassLevel, {"sort": i}, school_id=sid, section_id=section.id, name=name
                )
                for i, name in enumerate(sec.get("levels", []))
            ]
            for lower, higher in pairwise(levels):
                lower.next_level_id = lower.next_level_id or higher.id
            for i, name in enumerate(sec.get("subjects", [])):
                subjects[name] = subjects.get(name) or await _get_or_create(
                    db, Subject, {}, school_id=sid, name=name
                )
                for level in levels:
                    await _get_or_create(
                        db,
                        LevelSubject,
                        {"sort": i},
                        school_id=sid,
                        class_level_id=level.id,
                        subject_id=subjects[name].id,
                    )
            sec["_levels"] = levels
            await _seed_results_config(db, sid, section, sec)

        acad = config["academic_session"]
        session = await _get_or_create(db, AcademicSession, {}, school_id=sid, name=acad["name"])
        current = acad.get("current_term", 1)
        has_current = await db.scalar(select(func.count()).select_from(Term).where(Term.is_current))
        for number in (1, 2, 3):
            await _get_or_create(
                db,
                Term,
                {"is_current": not has_current and number == current},
                school_id=sid,
                academic_session_id=session.id,
                number=number,
            )
        for sec in config.get("sections", []):
            for level in sec["_levels"]:
                for arm in sec.get("arms", []):
                    await _get_or_create(
                        db,
                        Arm,
                        {},
                        school_id=sid,
                        class_level_id=level.id,
                        academic_session_id=session.id,
                        name=arm,
                    )

        # Fees: one schedule amount per item × every level × listed terms (kobo in the DB).
        terms_by_number = {
            t.number: t
            for t in await db.scalars(select(Term).where(Term.academic_session_id == session.id))
        }
        all_levels = [lv for sec in config.get("sections", []) for lv in sec["_levels"]]
        for sort, fee in enumerate(config.get("fees", [])):
            item = await _get_or_create(
                db, FeeItem, {"sort": sort}, school_id=sid, name=fee["name"]
            )
            for number in fee.get("terms", [1, 2, 3]):
                for level in all_levels:
                    await _get_or_create(
                        db,
                        FeeScheduleEntry,
                        {"amount_kobo": int(fee["amount_naira"] * 100)},
                        school_id=sid,
                        fee_item_id=item.id,
                        class_level_id=level.id,
                        term_id=terms_by_number[number].id,
                    )
        if "fees" in config and "fees" not in (school.settings or {}):
            school.settings = {
                **(school.settings or {}),
                "fees": {"withhold_results_for_debt": True},
            }

        temp_password = None
        if admin_email:
            user = await db.scalar(
                select(User).where(func.lower(User.email) == admin_email.lower())
            )
            if user is None:
                temp_password = secrets.token_urlsafe(9)
                user = User(
                    email=admin_email.lower(),
                    full_name=admin_name,
                    password_hash=hash_password(temp_password),
                    must_change_password=True,
                )
                db.add(user)
                await db.flush()
            await _get_or_create(
                db, Membership, {}, school_id=sid, user_id=user.id, role=Role.SCHOOL_ADMIN
            )

    print(f"School '{school.slug}' ready ({school.name}).")
    if temp_password:
        print(f"Admin {admin_email}: temporary password {temp_password}")
        print("They must change it and set up two-factor at first sign-in.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a school from a TOML file.")
    parser.add_argument("config", type=Path)
    parser.add_argument("--admin-email")
    parser.add_argument("--admin-name", default="School Administrator")
    args = parser.parse_args()
    config = tomllib.loads(args.config.read_text(encoding="utf-8"))

    async def run() -> None:
        try:
            await seed(config, args.admin_email, args.admin_name, args.config.parent)
        finally:
            await dispose_engine()

    asyncio.run(run())


if __name__ == "__main__":
    main()
