"""Report card PDFs, QR verification, the school crest, and the parent/student portal."""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select

from app.academics.models import AcademicSession, Arm, ClassLevel, Term
from app.auth.deps import CurrentPrincipal, Principal
from app.auth.models import STAFF_ROLES, Role
from app.core.config import get_settings
from app.db.helpers import get_or_404
from app.reports import pdf
from app.results.access import forbidden, heads_section, is_withheld
from app.results.models import ReportSnapshot, TeachingAssignment
from app.results.schemas import ChildResultsOut, PublishedTermOut, SnapshotOut, VerifyOut
from app.students.models import Enrollment, Guardian, Student, StudentGuardian
from app.tenancy.deps import CurrentSchool, TenantDB
from app.tenancy.models import School

router = APIRouter(tags=["reports"])


# ---------------------------------------------------------------- access


async def _student_ids_for(db: TenantDB, p: Principal) -> set[uuid.UUID]:
    """Students whose published results this parent/student may see."""
    me = p.session.user_uuid
    ids: set[uuid.UUID] = set()
    if Role.PARENT in p.roles:
        ids |= set(
            await db.scalars(
                select(StudentGuardian.student_id)
                .join(Guardian, Guardian.id == StudentGuardian.guardian_id)
                .where(Guardian.user_id == me)
            )
        )
    if Role.STUDENT in p.roles:
        ids |= set(await db.scalars(select(Student.id).where(Student.user_id == me)))
    return ids


async def _staff_may_see_arm(db: TenantDB, p: Principal, arm: Arm) -> bool:
    if not (p.roles & STAFF_ROLES):
        return False
    if Role.COUNSELLOR in p.roles or arm.form_teacher_user_id == p.session.user_uuid:
        return True
    level = await get_or_404(db, ClassLevel, arm.class_level_id, "Class")
    if await heads_section(db, p, level.section_id):
        return True
    return bool(
        await db.scalar(
            select(func.count())
            .select_from(TeachingAssignment)
            .where(
                TeachingAssignment.arm_id == arm.id,
                TeachingAssignment.teacher_user_id == p.session.user_uuid,
            )
        )
    )


async def _readable_snapshot(db: TenantDB, p: Principal, snapshot_id: uuid.UUID) -> ReportSnapshot:
    snap = await get_or_404(db, ReportSnapshot, snapshot_id, "Report card")
    enrollment = await get_or_404(db, Enrollment, snap.enrollment_id, "Report card")
    arm = await get_or_404(db, Arm, enrollment.arm_id, "Report card")
    if await _staff_may_see_arm(db, p, arm):
        return snap
    if enrollment.student_id in await _student_ids_for(db, p) and snap.is_current:
        if await is_withheld(db, enrollment.student_id, snap.term_id):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "This result is withheld. Please contact the school."
            )
        return snap
    # Indistinguishable from a missing card for anyone else (AC1).
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Report card not found")


def _verify_url(request: Request, snap: ReportSnapshot) -> str:
    scheme = "https" if get_settings().is_deployed else "http"
    host = request.headers.get("x-dl360-host", "")
    return f"{scheme}://{host}/verify/{snap.id}?h={snap.sha256[:16]}"


async def _logo(db: TenantDB, school: School) -> bytes | None:
    return await db.scalar(select(School.logo).where(School.id == school.id))


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


# ---------------------------------------------------------------- PDFs


@router.get("/api/reports/{snapshot_id}.pdf", response_class=Response)
async def report_pdf(
    snapshot_id: uuid.UUID,
    request: Request,
    p: CurrentPrincipal,
    school: CurrentSchool,
    db: TenantDB,
) -> Response:
    snap = await _readable_snapshot(db, p, snapshot_id)
    content = pdf.render(
        [(snap.data, _verify_url(request, snap), snap.sha256[:16])],
        await _logo(db, school),
        title=f"{snap.data['student']['name']} – {snap.data['term']['label']}",
    )
    name = snap.data["student"]["admission_no"].replace("/", "-")
    return _pdf_response(content, f"report-{name}.pdf")


@router.get("/api/reports/arm/{arm_id}.pdf", response_class=Response)
async def arm_reports_pdf(
    arm_id: uuid.UUID,
    request: Request,
    p: CurrentPrincipal,
    school: CurrentSchool,
    db: TenantDB,
    term_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    """Every current card for a class, one page each, ready to print."""
    arm = await get_or_404(db, Arm, arm_id, "Class")
    if not await _staff_may_see_arm(db, p, arm):
        raise forbidden()
    term = (
        await get_or_404(db, Term, term_id, "Term")
        if term_id
        else await db.scalar(select(Term).where(Term.is_current))
    )
    if term is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Term not found")
    snaps = list(
        await db.scalars(
            select(ReportSnapshot)
            .join(Enrollment, Enrollment.id == ReportSnapshot.enrollment_id)
            .join(Student, Student.id == Enrollment.student_id)
            .where(
                Enrollment.arm_id == arm.id,
                ReportSnapshot.term_id == term.id,
                ReportSnapshot.is_current,
            )
            .order_by(Student.last_name, Student.first_name)
        )
    )
    if not snaps:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No published results for this class yet.")
    content = pdf.render(
        [(s.data, _verify_url(request, s), s.sha256[:16]) for s in snaps],
        await _logo(db, school),
        title=f"{snaps[0].data['student']['class_label']} – {snaps[0].data['term']['label']}",
    )
    return _pdf_response(content, "report-cards.pdf")


# ---------------------------------------------------------------- public: verification + crest


@router.get("/api/public/verify/{snapshot_id}", response_model=VerifyOut)
async def verify(
    snapshot_id: uuid.UUID,
    school: CurrentSchool,
    db: TenantDB,
    h: Annotated[str, Query(min_length=8, max_length=64)],
) -> VerifyOut:
    """Anyone holding a printed card can check it's genuine. Shows only what's on the card."""
    snap = await db.get(ReportSnapshot, snapshot_id)
    if snap is None or not snap.sha256.startswith(h.lower()):
        return VerifyOut(valid=False, school=school.name)
    return VerifyOut(
        valid=snap.is_current,
        school=school.name,
        student=snap.data["student"]["name"],
        class_label=snap.data["student"]["class_label"],
        term_label=snap.data["term"]["label"],
        published_at=snap.published_at,
    )


@router.get("/api/public/logo", response_class=Response)
async def logo(school: CurrentSchool, db: TenantDB) -> Response:
    content = await _logo(db, school)
    if not content:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No logo")
    return Response(
        content,
        media_type=school.logo_content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ---------------------------------------------------------------- portal


@router.get("/api/portal/results", response_model=list[ChildResultsOut])
async def portal_results(p: CurrentPrincipal, db: TenantDB) -> list[ChildResultsOut]:
    """A parent's children (or a student themself) with their published results."""
    student_ids = await _student_ids_for(db, p)
    if not student_ids:
        return []
    out = []
    for student in await db.scalars(
        select(Student).where(Student.id.in_(student_ids)).order_by(Student.first_name)
    ):
        latest = (
            await db.execute(
                select(ClassLevel.name, Arm.name)
                .join(Arm, Arm.class_level_id == ClassLevel.id)
                .join(Enrollment, Enrollment.arm_id == Arm.id)
                .join(AcademicSession, AcademicSession.id == Enrollment.academic_session_id)
                .where(Enrollment.student_id == student.id)
                .order_by(AcademicSession.name.desc())
                .limit(1)
            )
        ).first()
        snaps = await db.execute(
            select(ReportSnapshot, Term)
            .join(Enrollment, Enrollment.id == ReportSnapshot.enrollment_id)
            .join(Term, Term.id == ReportSnapshot.term_id)
            .where(Enrollment.student_id == student.id, ReportSnapshot.is_current)
            .order_by(ReportSnapshot.published_at.desc())
        )
        results = []
        for snap, term in snaps:
            withheld = await is_withheld(db, student.id, term.id)
            results.append(
                PublishedTermOut(
                    snapshot_id=snap.id,
                    term_label=snap.data["term"]["label"],
                    session=snap.data["term"]["session"],
                    average=snap.data["summary"]["average"],
                    published_at=snap.published_at,
                    withheld=withheld,
                )
            )
        out.append(
            ChildResultsOut(
                student_id=student.id,
                full_name=student.full_name,
                class_label=f"{latest[0]} {latest[1]}" if latest else None,
                results=results,
            )
        )
    return out


@router.get("/api/portal/snapshots/{snapshot_id}", response_model=SnapshotOut)
async def portal_snapshot(snapshot_id: uuid.UUID, p: CurrentPrincipal, db: TenantDB) -> SnapshotOut:
    snap = await _readable_snapshot(db, p, snapshot_id)
    return SnapshotOut(snapshot_id=snap.id, data=snap.data)
