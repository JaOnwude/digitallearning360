from typing import Any

from sqlalchemy import Boolean, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import IdMixin, TimestampMixin


class School(Base, IdMixin, TimestampMixin):
    """A tenant. Global table (no RLS): the resolver reads it before any school context exists."""

    __tablename__ = "schools"

    slug: Mapped[str] = mapped_column(String(63), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    motto: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500))
    # {"primary": "#F5B50A", "accent": "#D9261C", "ink": "#5C4A12", "logo_url": "..."}
    branding: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # e.g. {"platform_fee_per_student_kobo": 5000000, "document_header": "..."}
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Crest, used by the web header and printed documents. Small (≤ 512 KB) so stored inline.
    logo: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(50))
