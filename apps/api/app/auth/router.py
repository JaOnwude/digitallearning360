from fastapi import APIRouter, Request, Response, status

from app.auth import service, sessions
from app.auth.deps import PartialPrincipal
from app.auth.models import Role, User
from app.auth.schemas import (
    LoginOut,
    MeOut,
    MessageOut,
    ParentCodeIn,
    ParentVerifyIn,
    PasswordChangeIn,
    StaffLoginIn,
    StudentLoginIn,
    TotpCodeIn,
    TotpEnrollOut,
    TotpVerifyOut,
)
from app.tenancy.deps import CurrentSchool, TenantDB

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/staff/login", response_model=LoginOut)
async def staff_login(
    body: StaffLoginIn, request: Request, response: Response, school: CurrentSchool, db: TenantDB
) -> LoginOut:
    step = await service.staff_login(db, school, request, response, body.email, body.password)
    return LoginOut(next=step)


@router.post("/totp/enroll", response_model=TotpEnrollOut)
async def totp_enroll(p: PartialPrincipal, db: TenantDB) -> TotpEnrollOut:
    uri, svg = await service.totp_enroll(db, p.token, p.session)
    return TotpEnrollOut(otpauth_uri=uri, qr_svg_data_uri=svg)


@router.post("/totp/verify", response_model=TotpVerifyOut)
async def totp_verify(
    body: TotpCodeIn, request: Request, p: PartialPrincipal, school: CurrentSchool, db: TenantDB
) -> TotpVerifyOut:
    step, codes = await service.totp_verify(db, school, request, p.token, p.session, body.code)
    return TotpVerifyOut(next=step, recovery_codes=codes)


@router.post("/parent/code", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED)
async def parent_code(
    body: ParentCodeIn, request: Request, school: CurrentSchool, db: TenantDB
) -> MessageOut:
    await service.parent_send_code(db, school, request, body.email)
    return MessageOut(message="If that email is registered with the school, a code is on its way.")


@router.post("/parent/verify", response_model=LoginOut)
async def parent_verify(
    body: ParentVerifyIn, request: Request, response: Response, school: CurrentSchool, db: TenantDB
) -> LoginOut:
    step = await service.parent_verify(db, school, request, response, body.email, body.code)
    return LoginOut(next=step)


@router.post("/student/login", response_model=LoginOut)
async def student_login(
    body: StudentLoginIn,
    request: Request,
    response: Response,
    school: CurrentSchool,
    db: TenantDB,
) -> LoginOut:
    step = await service.student_login(
        db, school, request, response, body.admission_no, body.password
    )
    return LoginOut(next=step)


@router.post("/password/change", response_model=LoginOut)
async def change_password(
    body: PasswordChangeIn, p: PartialPrincipal, school: CurrentSchool, db: TenantDB
) -> LoginOut:
    await service.change_password(
        db, school, p.token, p.session, body.current_password, body.new_password
    )
    user = await db.get(User, p.session.user_uuid)
    assert user is not None
    return LoginOut(next=service.next_step(p.session, user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    # Works even with an expired session, so no auth dependency here.
    token = request.cookies.get(sessions.session_cookie_name())
    if token:
        await sessions.destroy(token)
    sessions.clear_cookies(response)


@router.get("/me", response_model=MeOut)
async def me(p: PartialPrincipal, db: TenantDB) -> MeOut:
    user = await db.get(User, p.session.user_uuid)
    assert user is not None
    return MeOut(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        kind=p.session.kind,
        roles=[Role(r) for r in p.session.roles],
        next=service.next_step(p.session, user),
    )
