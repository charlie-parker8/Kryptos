"""Redis fixed-window rate limiting for the abuse-prone endpoints (auth, order submission).

Best-effort by design — a guard rail, not an invariant (contrast app.trading): if Redis is
unreachable the request is allowed through rather than taking login/trading down with the
cache. Keyed on client IP; behind Render (a proxy) the real client is the leftmost
`X-Forwarded-For` entry.
"""

import time
from collections.abc import Awaitable, Callable

import redis.asyncio as redis
from fastapi import Depends, HTTPException, Request, status

from app.redis_client import get_redis


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(
    bucket: str, *, limit: int, window_seconds: int
) -> Callable[[Request, redis.Redis], Awaitable[None]]:
    """Build a FastAPI dependency that allows at most `limit` requests per `window_seconds`
    per client IP for `bucket`. Use as a route `dependencies=[Depends(...)]` entry.
    """

    async def _dependency(
        request: Request,
        redis_client: redis.Redis = Depends(get_redis),  # noqa: B008 — FastAPI DI idiom
    ) -> None:
        window = int(time.time()) // window_seconds
        key = f"ratelimit:{bucket}:{_client_ip(request)}:{window}"
        try:
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, window_seconds)
        except redis.RedisError:
            return  # fail open — a Redis blip must not block auth or trading
        if count > limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests; slow down and retry shortly.",
                headers={"Retry-After": str(window_seconds)},
            )

    return _dependency
