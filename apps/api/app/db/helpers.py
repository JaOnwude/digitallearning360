import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def get_or_404[T](db: AsyncSession, model: type[T], id_: uuid.UUID, what: str) -> T:
    """Load a row by id in the current tenant transaction.

    Another school's row is invisible under RLS, so it is indistinguishable from a missing
    one: both are 404 (spec AC1).
    """
    row = await db.get(model, id_)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")
    return row


def conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


async def flush_or_conflict(db: AsyncSession, message: str) -> None:
    """Flush pending changes; a unique-constraint clash becomes a friendly 409.

    The flush runs in a savepoint so the request's transaction stays usable.
    """
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        raise conflict(message) from exc


async def ensure_all_exist(db: AsyncSession, model: type, ids: list[uuid.UUID], what: str) -> None:
    """422 unless every id is a row this school can see (protects composite-FK inserts)."""
    wanted = set(ids)
    if not wanted:
        return
    found = await db.scalar(
        select(func.count()).select_from(model).where(model.id.in_(wanted))  # type: ignore[attr-defined]
    )
    if found != len(wanted):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown {what}")
