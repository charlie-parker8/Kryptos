"""Keeps the Redis price cache warm from Kraken's live WS v2 feed and, on every tick, runs
the liquidation engine and fans out affected users' account updates over `/ws`. Started as a
background task from app.main's lifespan; this is the one thing that makes prices live and
liquidations automatic rather than pulled-on-demand.

Ticks for a given pair are processed strictly one at a time (the stream loop awaits
`on_tick` before reading the next frame), so the liquidation scan for a pair never overlaps
itself — the only concurrency it must handle is a user-initiated close racing it, which the
`positions.close_position` row lock + `closed_now` flag cover.
"""

import asyncio
import logging
import time
import uuid
from decimal import Decimal

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import bankruptcy, leaderboard, position_index, positions
from app import positions_math as pm
from app.account import get_account_snapshot
from app.config import Settings
from app.db import AsyncSessionLocal
from app.market_data.cache import set_cached_ticker
from app.market_data.kraken import Ticker, stream_tickers
from app.models import Position, User
from app.ws_manager import ws_manager
from app.ws_messages import (
    AccountUpdateMessage,
    PositionUpdateMessage,
    PriceTickMessage,
)

logger = logging.getLogger(__name__)

_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 30.0


async def run_price_stream(
    settings: Settings,
    redis_client: redis.Redis,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Reconnect-with-backoff loop around stream_tickers(). Every exception except
    CancelledError (re-raised so shutdown stays clean) is logged and retried with capped
    exponential backoff, reset once a connection runs cleanly.
    """
    session_factory = session_factory or AsyncSessionLocal
    backoff = _INITIAL_BACKOFF_SECONDS
    while True:
        try:
            await stream_tickers(
                settings.supported_pairs,
                settings.kraken_ws_url,
                on_tick=lambda ticker: handle_tick(
                    ticker, settings, redis_client, session_factory
                ),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "price stream disconnected; reconnecting in %.1fs", backoff
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)
        else:
            backoff = _INITIAL_BACKOFF_SECONDS


async def handle_tick(
    ticker: Ticker,
    settings: Settings,
    redis_client: redis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Public (not `_`-prefixed) so tests can simulate a single tick directly instead of
    driving a real Kraken connection — see backend/tests/test_price_stream.py.
    """
    await set_cached_ticker(
        redis_client, ticker, ttl_seconds=settings.price_max_age_seconds
    )
    await ws_manager.broadcast_price_tick(
        PriceTickMessage(
            pair=ticker.pair,
            bid=ticker.bid,
            ask=ticker.ask,
            last=ticker.last,
            as_of=ticker.as_of,
            broadcast_at=_now_ms(),
        )
    )
    liquidated_user_ids = await _run_liquidations(
        ticker.pair, ticker.last, settings, redis_client, session_factory
    )
    await _push_account_updates(
        ticker.pair,
        settings,
        redis_client,
        session_factory,
        also_users=liquidated_user_ids,
    )


async def _run_liquidations(
    pair: str,
    mark: Decimal,
    settings: Settings,
    redis_client: redis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
) -> set[uuid.UUID]:
    """Close every open position on `pair` whose stored liquidation price the fresh `mark`
    has crossed. Runs for all users, connected or not. Each close is its own transaction
    (one failing doesn't roll back the others). Returns the set of affected user ids.
    """
    candidate_ids = await _liquidation_candidates(pair, redis_client, session_factory)
    if not candidate_ids:
        return set()

    async with session_factory() as scan_db:
        rows = (
            await scan_db.execute(
                select(
                    Position.id,
                    Position.user_id,
                    Position.side,
                    Position.liquidation_price,
                ).where(
                    Position.id.in_(candidate_ids), Position.status == "open"
                )
            )
        ).all()

    crossed = [
        (position_id, user_id)
        for position_id, user_id, side, liquidation_price in rows
        if pm.is_liquidatable(
            side=side, mark_price=mark, liquidation_price=liquidation_price
        )
    ]

    affected: set[uuid.UUID] = set()
    for position_id, user_id in crossed:
        message: PositionUpdateMessage | None = None
        async with session_factory() as db:
            try:
                position, closed_now = await positions.close_position(
                    db,
                    redis_client,
                    settings,
                    user_id=user_id,
                    position_id=position_id,
                    reason="liquidation",
                    mark_override=mark,
                )
            except Exception:
                logger.exception("liquidation failed for position %s", position_id)
                continue

            if not closed_now or position.status != "liquidated":
                continue  # a user close (or an earlier tick) got there first
            # Build the message while the session is still open — the row's attributes are
            # populated (commit uses expire_on_commit=False).
            message = PositionUpdateMessage(
                position_id=position.id,
                pair=position.pair,
                side=position.side,  # type: ignore[arg-type]
                status="liquidated",
                close_price=position.close_price,  # type: ignore[arg-type]
                realized_pnl=position.realized_pnl,  # type: ignore[arg-type]
                reason="liquidation",
                at=position.closed_at,  # type: ignore[arg-type]
            )

        affected.add(user_id)
        await ws_manager.send_position_update(user_id, message)
    return affected


async def _liquidation_candidates(
    pair: str,
    redis_client: redis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
) -> list[uuid.UUID]:
    """Candidate position ids from the Redis index; on a Redis outage, fall back to a direct
    PostgreSQL scan so a lost index never means a missed liquidation.
    """
    try:
        return await position_index.get_open_position_ids(redis_client, pair)
    except redis.RedisError:
        logger.warning(
            "position index unavailable for %s; scanning Postgres", pair, exc_info=True
        )
        async with session_factory() as db:
            return list(
                (
                    await db.execute(
                        select(Position.id).where(
                            Position.pair == pair, Position.status == "open"
                        )
                    )
                )
                .scalars()
                .all()
            )


async def _push_account_updates(
    pair: str,
    settings: Settings,
    redis_client: redis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    also_users: set[uuid.UUID],
) -> None:
    """Push a fresh `account_update` to every connected user with an open position on the
    ticked pair (their equity moved), plus every user liquidated on this tick (so a
    connected client sees the position gone) — and run the bankruptcy check for each. The
    bankruptcy check runs even for a disconnected liquidated user: a liquidation is the
    main way an account is wiped out, and the reset must not wait for a reconnect.
    """
    connected = set(ws_manager.connected_user_ids())

    async with session_factory() as db:
        holder_ids = set(
            (
                await db.execute(
                    select(Position.user_id)
                    .where(Position.pair == pair, Position.status == "open")
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        target_ids = (holder_ids & connected) | also_users
        for user_id in target_ids:
            user = await db.get(User, user_id)
            if user is None:
                continue
            snapshot = await get_account_snapshot(db, redis_client, settings, user)
            await ws_manager.send_account_update(
                user_id, AccountUpdateMessage(**snapshot.model_dump())
            )
            await leaderboard.update_score(redis_client, user_id, snapshot.equity)
            if snapshot.equity <= settings.bankruptcy_equity_floor:
                await bankruptcy.check_and_broadcast(db, redis_client, settings, user)


def _now_ms() -> int:
    return int(time.time() * 1000)
