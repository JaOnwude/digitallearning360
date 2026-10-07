"""Staff accounts (admin only)."""

import secrets
import uuid
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import delete, func, select

from app.academics.models import Section
from app.audit import service as audit
from app.auth.deps import SchoolAdmin
from app.auth.models import STAFF_ROLES, Membership, Role, User
from app.auth.passwords import hash_password
from app.core.http import client_ip
from app.db.helpers import conflict, get_or_404
from app.staff.schemas import StaffCreatedOut, StaffCreateIn, StaffOut, StaffRoleOut
from app.tenancy.deps import CurrentSchool, TenantDB

router = APIRouter(prefix="/api/staff", tags=["staff"])


async def _staff(db: TenantDB, user_ids: list[uuid.UUID] | None = None) -> list[StaffOut]:
    query = select(Membership).where(Membership.role.in_(STAFF_ROLES))
    if user_ids is not None:
        query = query.where(Membership.user_id.in_(user_ids))
    memberships = list(await db.scalars(query))
    roles: dict[uuid.UUID, list[StaffRoleOut]] = defaultdict(list)
    for m in memberships:
        roles[m.user_id].append(StaffRoleOut(role=m.role, section_id=m.section_id))
    if not roles:
        return []
    users = await db.scalars(select(User).where(User.id.in_(roles)).order_by(User.full_name))
    return [
        StaffOut(
            user_id=u.id,
            full_name=u.full_name,
            email=u.email,
            roles=roles[u.id],
            two_factor_enabled=u.totp_enabled,
            is_active=u.is_active,
        )
        for u in users
    ]


@router.get("", response_model=list[StaffOut])
async def list_staff(_: SchoolAdmin, db: TenantDB) -> list[StaffOut]:
    return await _staff(db)


@router.post("", response_model=StaffCreatedOut, status_code=status.HTTP_201_CREATED)
async def add_staff(
    body: StaffCreateIn, request: Request, admin: SchoolAdmin, school: CurrentSchool, db: TenantDB
) -> StaffCreatedOut:
    if body.role not in STAFF_ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Not a staff role")
    if body.role == Role.SECTION_HEAD and body.section_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose the section they head")
    if body.section_id is not None:
        await get_or_404(db, Section, body.section_id, "Section")

    email = body.email.lower()
    user = await db.scalar(select(User).where(func.lower(User.email) == email))
    temporary_password = None
    if user is None:
        temporary_password = secrets.token_urlsafe(9)
        user = User(
            email=email,
            full_name=body.full_name.strip(),
            password_hash=hash_password(temporary_password),
            must_change_password=True,
        )
        db.add(user)
        await db.flush()
    existing = await db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.role == body.role,
            Membership.section_id.is_(None)
            if body.section_id is None
            else Membership.section_id == body.section_id,
        )
    )
    if existing is not None:
        raise conflict(f"{user.full_name} already has this role.")
    db.add(
        Membership(school_id=school.id, user_id=user.id, role=body.role, section_id=body.section_id)
    )
    await db.flush()
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=admin.session.user_uuid,
        action="staff.role_granted",
        entity_type="User",
        entity_id=user.id,
        after={"role": body.role, "section_id": str(body.section_id) if body.section_id else None},
        ip=client_ip(request),
    )
    [staff] = await _staff(db, [user.id])
    return StaffCreatedOut(staff=staff, temporary_password=temporary_password)


@router.delete("/{user_id}/roles/{role}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role(
    user_id: uuid.UUID,
    role: Role,
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> None:
    if user_id == admin.session.user_uuid and role == Role.SCHOOL_ADMIN:
        raise conflict("You can't remove your own admin role. Ask another admin.")
    result = await db.execute(
        delete(Membership).where(Membership.user_id == user_id, Membership.role == role)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff role not found")
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=admin.session.user_uuid,
        action="staff.role_removed",
        entity_type="User",
        entity_id=user_id,
        after={"role": role},
        ip=client_ip(request),
    )
