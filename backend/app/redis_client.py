"""Shared async Redis client and its FastAPI dependency — the Redis analogue of app.db.

Unlike a Postgres AsyncSession (opened and closed per request via app.db.get_session),
redis.asyncio.Redis already manages its own internal connection pool and is safe to reuse
as a single long-lived module-level instance across requests, so this dependency just
hands that instance back — no per-request lifecycle to manage.
"""

import redis.asyncio as redis

from app.config import get_settings

redis_client = redis.from_url(get_settings().redis_url)


async def get_redis() -> redis.Redis:
    return redis_client
