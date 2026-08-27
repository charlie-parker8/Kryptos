"""Keeps the Redis price cache warm from Kraken's live WS v2 feed and fans out both raw price
ticks and affected users' portfolio updates over `/ws`. Started as a background task from
app.main's lifespan; this is the one thing that makes prices actually live rather than
pulled-on-demand.
"""

import asyncio
import logging
import time

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import bankruptcy, leaderboard
from app.config import Settings
from app.db import AsyncSessionLocal
from app.market_data.cache import set_cached_ticker
from app.market_data.kraken import Ticker, stream_tickers
from app.models import Holding, User
from app.portfolio import get_portfolio_snapshot
from app.ws_manager import ws_manager
from app.ws_messages import PortfolioUpdateMessage, PriceTickMessage

logger = logging.getLogger(__name__)

_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 30.0


async def run_price_stream(
    settings: Settings,
    redis_client: redis.Redis,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Reconnect-with-backoff loop around stream_tickers(). A Kraken disconnect or a
    transient error anywhere in tick handling (e.g. a Redis blip) must not permanently kill
    price streaming for the rest of the process's life — every exception except
    CancelledError (explicitly re-raised so app shutdown stays clean) is logged and retried
    with capped exponential backoff, reset once a connection runs cleanly.
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
    await _push_portfolio_updates_to_holders(
        ticker.pair, settings, redis_client, session_factory
    )


async def _push_portfolio_updates_to_holders(
    pair: str,
    settings: Settings,
    redis_client: redis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    connected_user_ids = ws_manager.connected_user_ids()
    if not connected_user_ids:
        return

    base_asset = pair.split("/", 1)[0]
    async with session_factory() as db:
        holder_ids = (
            (
                await db.execute(
                    select(Holding.user_id)
                    .where(
                        Holding.symbol == base_asset,
                        Holding.quantity > 0,
                        Holding.user_id.in_(connected_user_ids),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        for user_id in holder_ids:
            user = await db.get(User, user_id)
            if user is None:
                continue
            snapshot = await get_portfolio_snapshot(db, redis_client, settings, user)
            await ws_manager.send_portfolio_update(
                user_id, PortfolioUpdateMessage(**snapshot.model_dump())
            )
            await leaderboard.update_score(redis_client, user_id, snapshot.net_worth)
            # Price movement is what actually pushes an account to $0 — this is the primary
            # bankruptcy trigger. Gate on the (tolerant) snapshot so the hot path only pays
            # for the locked, strict re-check when a reset is plausible.
            if snapshot.net_worth <= 0:
                await bankruptcy.check_and_broadcast(
                    db, redis_client, settings, user
                )


def _now_ms() -> int:
    return int(time.time() * 1000)
