"""Column and constraint building blocks shared by all models."""

import uuid
from datetime import datetime
from typing import Any

import uuid_utils
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


def uuid7() -> uuid.UUID:
    """Time-ordered UUIDs index better than random v4."""
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantMixin(IdMixin, TimestampMixin):
    """A school-owned row. Every table using this gets a FORCE'd RLS policy on school_id (R1).

    `(school_id, id)` is unique so children can reference it with a composite foreign key
    (see `tenant_fk`), which makes cross-school references impossible in the database.
    Models add their own constraints via `__extra_args__`.
    """

    __extra_args__: tuple[Any, ...] = ()

    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Any, ...]:
        name: str = cls.__tablename__  # type: ignore[attr-defined]
        return (
            UniqueConstraint("school_id", "id", name=f"uq_{name}_school_id_id"),
            *cls.__extra_args__,
        )


def tenant_fk(
    column: str, parent_table: str, *, ondelete: str | None = None
) -> ForeignKeyConstraint:
    """Composite FK (school_id, <column>) → <parent_table>(school_id, id)."""
    return ForeignKeyConstraint(
        ["school_id", column],
        [f"{parent_table}.school_id", f"{parent_table}.id"],
        ondelete=ondelete,
        name=f"fk_{column}_{parent_table}",
    )
