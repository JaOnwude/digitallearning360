from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.auth.deps import CurrentPrincipal
from app.auth.models import Role
from app.notifications.events import fees_channel, stream, user_channel

router = APIRouter(tags=["events"])


@router.get("/api/events", response_class=StreamingResponse)
async def events(p: CurrentPrincipal) -> StreamingResponse:
    """Server-sent events for the signed-in user (R28). The browser re-fetches on each event."""
    channels = [user_channel(p.session.user_id)]
    if p.roles & {Role.BURSAR, Role.SCHOOL_ADMIN}:
        channels.append(fees_channel(p.session.school_id))
    return StreamingResponse(
        stream(channels),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
