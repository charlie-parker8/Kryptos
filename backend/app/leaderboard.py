"""Redis-backed leaderboard, ranked by account equity.

Per CLAUDE.md, Redis holds no authoritative state: the sorted set here caches each account's
derived equity and is fully rebuildable from PostgreSQL (free cash + open positions) plus
the latest cached prices (see `rebuild`). Losing it costs freshness, never records. Scores
are stored as **integer cents** — float64 represents integers exactly up to 2^53, so
ranking stays exact without a Decimal round-trip. Equity can be negative (a gap move past a
liquidation price); the sorted set orders negatives correctly and the reset backstop catches
them.

`update_score` is called wherever a fresh equity is already computed (registration, an open
or close, a per-tick account push, a liquidation, a bankruptcy reset); `run_leaderboard_refresh`
periodically rebuilds the whole set so disconnected accounts don't go stale and an empty
Redis self-heals.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import redis.asyncio as redis
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import position_index
from app.account import get_account_snapshot
from app.config import Settings
from app.db import AsyncSessionLocal
from app.models import User

logger = logging.getLogger(__name__)

ZSET_KEY = "leaderboard:equity"
PREV_RANKS_KEY = "leaderboard:prev_ranks"
_REFRESH_INTERVAL_SECONDS = 30.0


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    equity: Decimal
    move: int  # previous rank minus current rank: positive = climbed, 0 = new/unchanged
    is_you: bool


class LeaderboardResponse(BaseModel):
    entries: list[LeaderboardEntry]
    you: LeaderboardEntry | None  # set only when the viewer falls outside `entries`
    as_of: datetime


def _to_cents(equity: Decimal) -> int:
    return int((equity * 100).to_integral_value())


def _decode(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


async def update_score(
    redis_client: redis.Redis, user_id: uuid.UUID, equity: Decimal
) -> None:
    """Best-effort. The leaderboard is non-authoritative, so a Redis failure here must never
    break the caller — the periodic rebuild reconciles.
    """
    try:
        await redis_client.zadd(ZSET_KEY, {str(user_id): _to_cents(equity)})
    except redis.RedisError:
        logger.warning(
            "leaderboard update_score failed for %s", user_id, exc_info=True
        )


async def get_board(
    db: AsyncSession,
    redis_client: redis.Redis,
    *,
    limit: int,
    viewer_id: uuid.UUID,
) -> LeaderboardResponse:
    """Top `limit` accounts by equity, plus the viewer's own row when they rank below the
    page. `move` compares each rank against the previous-rank snapshot the last rebuild took.
    """
    top: list[tuple[bytes, float]] = cast(
        "list[tuple[bytes, float]]",
        await redis_client.zrevrange(ZSET_KEY, 0, limit - 1, withscores=True),
    )
    prev_raw: dict[Any, Any] = await redis_client.hgetall(PREV_RANKS_KEY)
    prev_ranks = {_decode(k): int(v) for k, v in prev_raw.items()}

    viewer_key = str(viewer_id)
    viewer_rank_raw = cast(
        "int | None", await redis_client.zrevrank(ZSET_KEY, viewer_key)
    )
    viewer_score = await redis_client.zscore(ZSET_KEY, viewer_key)

    top_ids = [uuid.UUID(_decode(member)) for member, _ in top]
    wanted = {*top_ids, viewer_id}
    usernames = {
        row_id: name
        for row_id, name in (
            await db.execute(
                select(User.id, User.username).where(User.id.in_(wanted))
            )
        ).all()
    }

    def _entry(uid: uuid.UUID, rank: int, score: float) -> LeaderboardEntry:
        return LeaderboardEntry(
            rank=rank,
            username=usernames.get(uid, "unknown"),
            equity=Decimal(int(score)) / 100,
            move=prev_ranks.get(str(uid), rank) - rank,
            is_you=uid == viewer_id,
        )

    entries = [
        _entry(uuid.UUID(_decode(member)), i + 1, score)
        for i, (member, score) in enumerate(top)
    ]

    you: LeaderboardEntry | None = None
    if viewer_rank_raw is not None and viewer_score is not None:
        viewer_rank = int(viewer_rank_raw) + 1
        if viewer_rank > limit:
            you = _entry(viewer_id, viewer_rank, float(viewer_score))

    return LeaderboardResponse(entries=entries, you=you, as_of=datetime.now(UTC))


async def rebuild(
    db: AsyncSession, redis_client: redis.Redis, settings: Settings
) -> int:
    """Recompute every account's equity from PostgreSQL + cached prices and rewrite the
    sorted set, and reconcile the open-position index. Snapshots the pre-rebuild ranks into
    `PREV_RANKS_KEY` first so `move` reflects change across the interval. Returns the
    account count.
    """
    await position_index.reconcile(db, redis_client, settings.supported_pairs)

    current: list[bytes] = cast(
        "list[bytes]", await redis_client.zrevrange(ZSET_KEY, 0, -1)
    )
    if current:
        mapping: dict[Any, Any] = {
            _decode(member): i + 1 for i, member in enumerate(current)
        }
        await redis_client.delete(PREV_RANKS_KEY)
        await redis_client.hset(PREV_RANKS_KEY, mapping=mapping)

    users = (await db.execute(select(User))).scalars().all()
    if not users:
        return 0

    scores: dict[str, int] = {}
    for user in users:
        snapshot = await get_account_snapshot(db, redis_client, settings, user)
        scores[str(user.id)] = _to_cents(snapshot.equity)

    await redis_client.delete(ZSET_KEY)
    await redis_client.zadd(ZSET_KEY, scores)
    return len(users)


async def run_leaderboard_refresh(
    settings: Settings,
    redis_client: redis.Redis,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Periodic full rebuild — started from app.main's lifespan, mirroring
    app.price_stream.run_price_stream's resilience loop. A transient failure (DB blip, Redis
    blip) is logged and retried on the next cycle; only CancelledError stops it.
    """
    session_factory = session_factory or AsyncSessionLocal
    while True:
        try:
            async with session_factory() as db:
                await rebuild(db, redis_client, settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("leaderboard refresh cycle failed; retrying next cycle")
        await asyncio.sleep(_REFRESH_INTERVAL_SECONDS)
