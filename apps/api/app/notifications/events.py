"""Live updates to signed-in browsers via Redis pub/sub → server-sent events (spec R28).

Channels: `events:user:{user_id}` (one person) and `events:school:{school_id}:fees` (bursars).
Events are hints ("invoice X changed"); the browser re-fetches, so nothing sensitive is sent.
"""

import json
import uuid
from collections.abc import AsyncIterator, Iterable

from app.core.redis import get_redis

HEARTBEAT_SECONDS = 20


def user_channel(user_id: uuid.UUID | str) -> str:
    return f"events:user:{user_id}"


def fees_channel(school_id: uuid.UUID | str) -> str:
    return f"events:school:{school_id}:fees"


async def publish(channels: Iterable[str], event: str, data: dict[str, str]) -> None:
    payload = json.dumps({"event": event, "data": data})
    redis = get_redis()
    for channel in set(channels):
        await redis.publish(channel, payload)


async def stream(channels: list[str]) -> AsyncIterator[str]:
    """Yield SSE frames for these channels until the client disconnects."""
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(*channels)
    try:
        yield "retry: 5000\n\n"
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS
            )
            if message is None:
                yield ": keep-alive\n\n"  # comment frame: keeps proxies from closing the stream
                continue
            body = json.loads(message["data"])
            yield f"event: {body['event']}\ndata: {json.dumps(body['data'])}\n\n"
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.aclose()
