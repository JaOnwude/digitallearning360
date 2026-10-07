"""Map an incoming request host to a school."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.tenancy.models import School


def slug_from_host(host: str, settings: Settings) -> str | None:
    """`progress.digitallearning360.localhost:3360` → `progress`.

    Falls back to the configured default school for hosts outside the base domain
    (e.g. a vercel.app staging URL). Returns None when no school applies.
    """
    hostname = host.split(":", 1)[0].lower().rstrip(".")
    suffix = "." + settings.base_domain.lower()
    if hostname.endswith(suffix):
        label = hostname.removesuffix(suffix)
        if label and "." not in label and label not in {"www", "api", "app"}:
            return label
        return None
    return settings.default_school_slug


async def get_active_school(db: AsyncSession, slug: str) -> School | None:
    return await db.scalar(select(School).where(School.slug == slug, School.is_active))
