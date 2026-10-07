from pydantic import BaseModel

from app.academics.models import SectionKind


class Branding(BaseModel):
    primary: str | None = None
    accent: str | None = None
    ink: str | None = None
    logo_url: str | None = None


class PublicSection(BaseModel):
    display_name: str
    kind: SectionKind
    student_login_enabled: bool


class PublicSchoolOut(BaseModel):
    """What anyone visiting the school's site may see (login page branding)."""

    slug: str
    name: str
    motto: str | None
    branding: Branding
    sections: list[PublicSection]
