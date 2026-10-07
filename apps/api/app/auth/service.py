"""Login flows for staff, parents and students (spec R4–R7)."""

import json
import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.academics.models import AcademicSession, Arm, ClassLevel, Section
from app.audit import service as audit
from app.auth import passwords, sessions, totp
from app.auth.models import MFA_REQUIRED_ROLES, STAFF_ROLES, Membership, Role, User
from app.auth.schemas import NextStep
from app.auth.sessions import SessionData, SessionKind
from app.core import ratelimit
from app.core.crypto import constant_time_equals, decrypt, encrypt, sha256_hex
from app.core.redis import get_redis
from app.notifications.service import send_email
from app.students.models import Enrollment, Guardian, Student
from app.tenancy.models import School

INVALID_LOGIN = "Incorrect details. Check and try again."
CODE_TTL_SECONDS = 600
CODE_MAX_ATTEMPTS = 5


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def next_step(data: SessionData, user: User) -> NextStep:
    """The step the web app should show next for this session."""
    if not data.mfa_ok:
        return NextStep.TOTP_VERIFY if user.totp_enabled else NextStep.TOTP_ENROLL
    if data.must_change_password:
        return NextStep.CHANGE_PASSWORD
    return NextStep.DONE


async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(func.lower(User.email) == email.lower()))


async def _roles_in_school(db: AsyncSession, user: User) -> set[Role]:
    rows = await db.scalars(select(Membership.role).where(Membership.user_id == user.id))
    return set(rows)


async def _login_failed(db: AsyncSession, school: School, request: Request, who: str) -> None:
    await audit.record(
        db,
        school_id=school.id,
        action="auth.login_failed",
        after={"identifier": who},
        ip=client_ip(request),
    )


# ---------------------------------------------------------------- staff


async def staff_login(
    db: AsyncSession,
    school: School,
    request: Request,
    response: Response,
    email: str,
    password: str,
) -> NextStep:
    ip = client_ip(request)
    await ratelimit.hit(f"login:staff:{school.id}:{email.lower()}", limit=10, window_seconds=900)
    await ratelimit.hit(f"login:ip:{ip}", limit=50, window_seconds=900)

    user = await _user_by_email(db, email)
    ok = passwords.verify_password(password, user.password_hash if user else None)
    roles = (await _roles_in_school(db, user)) & STAFF_ROLES if user and ok else set()
    if user is None or not ok or not user.is_active or not roles:
        await _login_failed(db, school, request, email.lower())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)

    needs_mfa = user.totp_enabled or bool(roles & MFA_REQUIRED_ROLES)
    data = SessionData(
        user_id=str(user.id),
        school_id=str(school.id),
        kind=SessionKind.STAFF,
        roles=sorted(roles),
        mfa_ok=not needs_mfa,
        must_change_password=user.must_change_password,
    )
    await sessions.create(response, data)
    if not needs_mfa:
        await _login_succeeded(db, school, user, ip)
    return next_step(data, user)


async def _login_succeeded(db: AsyncSession, school: School, user: User, ip: str) -> None:
    user.last_login_at = datetime.now(UTC)
    await audit.record(db, school_id=school.id, action="auth.login", actor_user_id=user.id, ip=ip)


async def totp_enroll(db: AsyncSession, token: str, data: SessionData) -> tuple[str, str]:
    user = await db.get(User, data.user_uuid)
    assert user is not None
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-factor is already set up")
    secret = totp.new_secret()
    data.pending_totp_enc = encrypt(secret)
    await sessions.save(token, data)
    return totp.provisioning(secret, user.email or user.full_name)


async def totp_verify(
    db: AsyncSession, school: School, request: Request, token: str, data: SessionData, code: str
) -> tuple[NextStep, list[str] | None]:
    await ratelimit.hit(f"totp:{data.user_id}", limit=8, window_seconds=900)
    user = await db.get(User, data.user_uuid)
    assert user is not None
    recovery_codes: list[str] | None = None

    if data.pending_totp_enc is not None:  # finishing enrollment
        secret = decrypt(data.pending_totp_enc)
        if not totp.verify(secret, code):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code didn't match. Try again.")
        recovery_codes, hashes = totp.new_recovery_codes()
        user.totp_secret_enc = encrypt(secret)
        user.totp_enabled = True
        user.recovery_code_hashes = hashes
        data.pending_totp_enc = None
        await audit.record(
            db, school_id=school.id, action="auth.totp_enrolled", actor_user_id=user.id
        )
    else:
        if not user.totp_enabled or user.totp_secret_enc is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Set up two-factor first")
        if not totp.verify(decrypt(user.totp_secret_enc), code):
            used = sha256_hex(totp.normalise_recovery_code(code))
            if used not in user.recovery_code_hashes:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code didn't match.")
            user.recovery_code_hashes = [h for h in user.recovery_code_hashes if h != used]
            await audit.record(
                db, school_id=school.id, action="auth.recovery_code_used", actor_user_id=user.id
            )

    data.mfa_ok = True
    await sessions.save(token, data)
    await ratelimit.reset(f"totp:{data.user_id}")
    await _login_succeeded(db, school, user, client_ip(request))
    return (NextStep.CHANGE_PASSWORD if data.must_change_password else NextStep.DONE), (
        recovery_codes
    )


# ---------------------------------------------------------------- parents (email code)


def _code_key(school: School, email: str) -> str:
    return f"otp:{school.id}:{sha256_hex(email.lower())}"


async def parent_send_code(db: AsyncSession, school: School, request: Request, email: str) -> None:
    """Always succeeds from the caller's view, so it can't be used to discover parent emails."""
    email = email.lower()
    await ratelimit.hit(f"otp-send:{school.id}:{email}", limit=3, window_seconds=900)
    await ratelimit.hit(f"otp-send-ip:{client_ip(request)}", limit=20, window_seconds=3600)
    exists = await db.scalar(
        select(func.count()).select_from(Guardian).where(func.lower(Guardian.email) == email)
    )
    if not exists:
        return
    code = f"{secrets.randbelow(1_000_000):06d}"
    await get_redis().set(
        _code_key(school, email),
        json.dumps({"hash": sha256_hex(code), "attempts": 0}),
        ex=CODE_TTL_SECONDS,
    )
    await send_email(
        to=email,
        subject=f"Your {school.name} sign-in code",
        text=(
            f"Your sign-in code is {code}. It expires in 10 minutes.\n\n"
            "If you didn't ask for this, you can ignore this email."
        ),
    )


async def parent_verify(
    db: AsyncSession, school: School, request: Request, response: Response, email: str, code: str
) -> NextStep:
    email = email.lower()
    key = _code_key(school, email)
    redis = get_redis()
    raw = await redis.get(key)
    if raw is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code expired. Request a new one.")
    entry = json.loads(raw)
    if not constant_time_equals(entry["hash"], sha256_hex(code)):
        entry["attempts"] += 1
        if entry["attempts"] >= CODE_MAX_ATTEMPTS:
            await redis.delete(key)
            await _login_failed(db, school, request, email)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "Too many wrong codes. Request a new one."
            )
        await redis.set(key, json.dumps(entry), keepttl=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code didn't match.")
    await redis.delete(key)  # single use

    guardians = list(await db.scalars(select(Guardian).where(func.lower(Guardian.email) == email)))
    if not guardians:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_LOGIN)
    user = await _user_by_email(db, email)
    if user is None:
        user = User(email=email, full_name=guardians[0].full_name)
        db.add(user)
        await db.flush()
    for g in guardians:
        g.user_id = user.id
    if Role.PARENT not in await _roles_in_school(db, user):
        db.add(Membership(school_id=school.id, user_id=user.id, role=Role.PARENT))

    data = SessionData(
        user_id=str(user.id),
        school_id=str(school.id),
        kind=SessionKind.PARENT,
        roles=[Role.PARENT],
        mfa_ok=True,
        must_change_password=False,
    )
    await sessions.create(response, data)
    await _login_succeeded(db, school, user, client_ip(request))
    return NextStep.DONE


# ---------------------------------------------------------------- students


async def student_login_allowed(db: AsyncSession, student: Student) -> bool:
    """R5a: student login is enabled per section; use the student's latest enrollment."""
    enabled = await db.scalar(
        select(Section.student_login_enabled)
        .join(ClassLevel, ClassLevel.section_id == Section.id)
        .join(Arm, Arm.class_level_id == ClassLevel.id)
        .join(Enrollment, Enrollment.arm_id == Arm.id)
        .join(AcademicSession, AcademicSession.id == Enrollment.academic_session_id)
        .where(Enrollment.student_id == student.id)
        .order_by(AcademicSession.name.desc())
        .limit(1)
    )
    return bool(enabled)


async def student_login(
    db: AsyncSession,
    school: School,
    request: Request,
    response: Response,
    admission_no: str,
    password: str,
) -> NextStep:
    admission_no = admission_no.strip().upper()
    await ratelimit.hit(f"login:student:{school.id}:{admission_no}", limit=10, window_seconds=900)
    await ratelimit.hit(f"login:ip:{client_ip(request)}", limit=50, window_seconds=900)

    student = await db.scalar(
        select(Student).where(func.upper(Student.admission_no) == admission_no)
    )
    user = await db.get(User, student.user_id) if student and student.user_id else None
    ok = passwords.verify_password(password, user.password_hash if user else None)
    if student is None or user is None or not ok or not user.is_active:
        await _login_failed(db, school, request, admission_no)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)
    if not await student_login_allowed(db, student):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Student sign-in isn't enabled for your class yet."
        )

    data = SessionData(
        user_id=str(user.id),
        school_id=str(school.id),
        kind=SessionKind.STUDENT,
        roles=[Role.STUDENT],
        mfa_ok=True,
        must_change_password=user.must_change_password,
    )
    await sessions.create(response, data)
    await _login_succeeded(db, school, user, client_ip(request))
    return NextStep.CHANGE_PASSWORD if data.must_change_password else NextStep.DONE


# ---------------------------------------------------------------- password


async def change_password(
    db: AsyncSession,
    school: School,
    token: str,
    data: SessionData,
    current_password: str | None,
    new_password: str,
) -> None:
    if not data.mfa_ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "two_factor_required")
    await ratelimit.hit(f"pwchange:{data.user_id}", limit=10, window_seconds=900)
    user = await db.get(User, data.user_uuid)
    assert user is not None
    # A forced change (temporary password) was just proven at login; otherwise re-check.
    if not data.must_change_password and not passwords.verify_password(
        current_password or "", user.password_hash
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if not passwords.is_acceptable(new_password):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Use at least 8 characters, not only numbers."
        )
    if passwords.verify_password(new_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a password you haven't used.")
    user.password_hash = passwords.hash_password(new_password)
    user.must_change_password = False
    data.must_change_password = False
    await sessions.save(token, data)
    await audit.record(
        db, school_id=school.id, action="auth.password_changed", actor_user_id=user.id
    )
