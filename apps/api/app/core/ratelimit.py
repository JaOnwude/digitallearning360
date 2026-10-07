"""Fixed-window rate limits in Redis (spec R26)."""

from fastapi import HTTPException, status

from app.core.redis import get_redis


async def hit(bucket: str, *, limit: int, window_seconds: int) -> None:
    """Count one attempt in `bucket`; raise 429 once `limit` is exceeded within the window."""
    redis = get_redis()
    key = f"rl:{bucket}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count > limit:
        ttl = await redis.ttl(key)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(max(ttl, 1))},
        )


async def reset(bucket: str) -> None:
    await get_redis().delete(f"rl:{bucket}")
