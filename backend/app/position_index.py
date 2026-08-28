"""Redis index of open-position ids per pair — the candidate list for the per-tick
liquidation scan in app.price_stream.

Best-effort and fully rebuildable from PostgreSQL (invariant 8): `add`/`remove` swallow
Redis errors, and `reconcile` (run on startup and once per leaderboard-refresh cycle)
rewrites every pair's set from `positions.status = 'open'`. A stale entry is harmless — the
scan re-loads and re-checks every candidate under a row lock before closing it — and a
missed add only delays a liquidation check by at most one reconcile interval.
"""

import logging
import uuid

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Position

logger = logging.getLogger(__name__)

_KEY_PREFIX = "positions:open"


def _key(pair: str) -> str:
    return f"{_KEY_PREFIX}:{pair}"


def _decode(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


async def add_open_position(
    client: redis.Redis, pair: str, position_id: uuid.UUID
) -> None:
    try:
        await client.sadd(_key(pair), str(position_id))
    except redis.RedisError:
        logger.warning(
            "position index: SADD failed for %s / %s", pair, position_id, exc_info=True
        )


async def remove_open_position(
    client: redis.Redis, pair: str, position_id: uuid.UUID
) -> None:
    try:
        await client.srem(_key(pair), str(position_id))
    except redis.RedisError:
        logger.warning(
            "position index: SREM failed for %s / %s", pair, position_id, exc_info=True
        )


async def get_open_position_ids(client: redis.Redis, pair: str) -> list[uuid.UUID]:
    """Candidate ids for the liquidation scan. Raises on a Redis outage so the caller can
    fall back to a direct PostgreSQL query for that tick.
    """
    members = await client.smembers(_key(pair))
    return [uuid.UUID(_decode(m)) for m in members]


async def reconcile(
    db: AsyncSession, client: redis.Redis, pairs: list[str]
) -> None:
    """Rewrite every pair's open-position set from PostgreSQL."""
    rows = (
        await db.execute(
            select(Position.pair, Position.id).where(Position.status == "open")
        )
    ).all()
    by_pair: dict[str, set[str]] = {pair: set() for pair in pairs}
    for pair, position_id in rows:
        by_pair.setdefault(pair, set()).add(str(position_id))

    pipe = client.pipeline()
    for pair, ids in by_pair.items():
        pipe.delete(_key(pair))
        if ids:
            pipe.sadd(_key(pair), *ids)
    await pipe.execute()
