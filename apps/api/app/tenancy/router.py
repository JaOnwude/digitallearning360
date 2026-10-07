from fastapi import APIRouter
from sqlalchemy import select

from app.academics.models import Section
from app.tenancy.deps import CurrentSchool, TenantDB
from app.tenancy.schemas import Branding, PublicSchoolOut, PublicSection

router = APIRouter(prefix="/api/public", tags=["school"])


@router.get("/school", response_model=PublicSchoolOut)
async def public_school(school: CurrentSchool, db: TenantDB) -> PublicSchoolOut:
    sections = await db.scalars(select(Section).order_by(Section.sort, Section.name))
    return PublicSchoolOut(
        slug=school.slug,
        name=school.name,
        motto=school.motto,
        branding=Branding.model_validate(school.branding),
        sections=[
            PublicSection(
                display_name=s.display_name,
                kind=s.kind,
                student_login_enabled=s.student_login_enabled,
            )
            for s in sections
        ],
    )
