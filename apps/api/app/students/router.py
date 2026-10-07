"""Students and guardians (admin only in M1)."""

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse

from app.academics.models import Arm, House
from app.audit import service as audit
from app.auth.deps import SchoolAdmin
from app.auth.models import User
from app.auth.passwords import hash_password
from app.core.http import client_ip
from app.db.helpers import flush_or_conflict, get_or_404
from app.students import importer, service
from app.students.models import Student
from app.students.schemas import (
    ImportResultOut,
    LoginSlip,
    LoginSlipsIn,
    StudentDetail,
    StudentIn,
    StudentPage,
    StudentUpdateIn,
)
from app.tenancy.deps import CurrentSchool, TenantDB

router = APIRouter(prefix="/api/students", tags=["students"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024


@router.get("", response_model=StudentPage)
async def list_students(
    _: SchoolAdmin,
    db: TenantDB,
    q: Annotated[str | None, Query(max_length=100)] = None,
    arm_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> StudentPage:
    items, total = await service.list_students(
        db, q=q, arm_id=arm_id, page=page, page_size=page_size
    )
    return StudentPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/import-template", response_class=PlainTextResponse)
async def import_template(_: SchoolAdmin) -> PlainTextResponse:
    example = (
        "PJS/2026/001,Chinedu,Emeka,Okafor,Male,2014-05-21,JSS1,A,,"
        "Mrs Ngozi Okafor,ngozi@example.com,08031234567,Mother"
    )
    return PlainTextResponse(
        f"{importer.TEMPLATE_HEADER}\n{example}\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="students-template.csv"'},
    )


@router.post("/import", response_model=ImportResultOut)
async def import_students(
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
    file: Annotated[UploadFile, File(description="CSV file")],
    dry_run: Annotated[bool, Form()] = True,
) -> ImportResultOut:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Keep the file under 2 MB.")
    result = await importer.run(db, school.id, content, dry_run=dry_run)
    if not dry_run:
        await audit.record(
            db,
            school_id=school.id,
            actor_user_id=admin.session.user_uuid,
            action="students.imported",
            after={
                "file": file.filename,
                "created": result.students_created,
                "skipped_rows": len({e.row for e in result.errors}),
            },
            ip=client_ip(request),
        )
    return result


@router.post("/logins", response_model=list[LoginSlip])
async def issue_logins(
    body: LoginSlipsIn, request: Request, admin: SchoolAdmin, school: CurrentSchool, db: TenantDB
) -> list[LoginSlip]:
    """Create or reset student logins. Passwords are returned once, for printing slips."""
    slips: list[LoginSlip] = []
    for student_id in dict.fromkeys(body.student_ids):
        student = await get_or_404(db, Student, student_id, "Student")
        password = f"{secrets.token_hex(2)}-{secrets.token_hex(2)}"  # easy to type from paper
        user = await db.get(User, student.user_id) if student.user_id else None
        if user is None:
            user = User(full_name=student.full_name)
            db.add(user)
            await db.flush()
            student.user_id = user.id
        user.password_hash = hash_password(password)
        user.must_change_password = True
        detail = await service.student_detail(db, student.id)
        slips.append(
            LoginSlip(
                student_id=student.id,
                admission_no=student.admission_no,
                full_name=student.full_name,
                class_name=detail.class_name if detail else None,
                temporary_password=password,
            )
        )
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=admin.session.user_uuid,
        action="students.logins_issued",
        after={"count": len(slips)},
        ip=client_ip(request),
    )
    return slips


@router.get("/{student_id}", response_model=StudentDetail)
async def get_student(student_id: uuid.UUID, _: SchoolAdmin, db: TenantDB) -> StudentDetail:
    detail = await service.student_detail(db, student_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    return detail


@router.post("", response_model=StudentDetail, status_code=status.HTTP_201_CREATED)
async def create_student(
    body: StudentIn, request: Request, admin: SchoolAdmin, school: CurrentSchool, db: TenantDB
) -> StudentDetail:
    arm = await get_or_404(db, Arm, body.arm_id, "Arm")
    if body.house_id:
        await get_or_404(db, House, body.house_id, "House")
    student = Student(
        school_id=school.id,
        admission_no=body.admission_no.strip().upper(),
        first_name=body.first_name.strip(),
        middle_name=(body.middle_name or "").strip() or None,
        last_name=body.last_name.strip(),
        gender=body.gender,
        date_of_birth=body.date_of_birth,
        house_id=body.house_id,
    )
    db.add(student)
    await flush_or_conflict(db, f"Admission number {student.admission_no} is already in use.")
    await service.set_arm(db, school.id, student, arm)
    if body.guardian and (body.guardian.email or body.guardian.phone):
        phone = service.normalise_phone(body.guardian.phone) if body.guardian.phone else None
        if body.guardian.phone and phone is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Use a Nigerian mobile number"
            )
        index = await service.GuardianIndex(school.id).load(db)
        guardian = index.get_or_create(db, body.guardian.full_name, body.guardian.email, phone)
        await service.link_guardian(db, school.id, student, guardian, body.guardian.relationship)
    await db.flush()
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=admin.session.user_uuid,
        action="students.created",
        entity_type="Student",
        entity_id=student.id,
        ip=client_ip(request),
    )
    detail = await service.student_detail(db, student.id)
    assert detail is not None
    return detail


@router.patch("/{student_id}", response_model=StudentDetail)
async def update_student(
    student_id: uuid.UUID,
    body: StudentUpdateIn,
    request: Request,
    admin: SchoolAdmin,
    school: CurrentSchool,
    db: TenantDB,
) -> StudentDetail:
    student = await get_or_404(db, Student, student_id, "Student")
    changes = body.model_dump(exclude_unset=True)
    arm_id = changes.pop("arm_id", None)
    if changes.get("house_id"):
        await get_or_404(db, House, changes["house_id"], "House")
    for name, value in changes.items():
        setattr(student, name, value.strip() if isinstance(value, str) else value)
    if arm_id is not None:
        await service.set_arm(db, school.id, student, await get_or_404(db, Arm, arm_id, "Arm"))
    await db.flush()
    await audit.record(
        db,
        school_id=school.id,
        actor_user_id=admin.session.user_uuid,
        action="students.updated",
        entity_type="Student",
        entity_id=student.id,
        after={k: str(v) for k, v in body.model_dump(exclude_unset=True).items()},
        ip=client_ip(request),
    )
    detail = await service.student_detail(db, student.id)
    assert detail is not None
    return detail
