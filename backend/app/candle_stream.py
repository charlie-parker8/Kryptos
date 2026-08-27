"""Keeps the Redis forming-candle cache warm from Kraken's live WS v2 `ohlc` feed and fans
the running bar out over `/ws` as `candle_update`. Started as a background task from
app.main's lifespan, deliberately separate from app.price_stream: that stream keeps the
price cache fresh (invariant 10) and drives portfolio revaluation, leaderboard scoring, and
bankruptcy (invariant 12), and must not share a connection with 12 noisy OHLC subscriptions.

Kraken sends no "this candle closed" flag, so a bucket roll is inferred here from a change
in `interval_begin` (Candle.open_time). Closed candles are NOT persisted — history is a
REST-backed read-through cache (app.market_data.candles.get_candles); this task only
maintains `:forming` and emits the `closed=True` frame so the client finalises the bar
without waiting for its next history refetch.

Kraken allows only one ohlc interval per connection, so `run_candle_stream` opens one WS
connection per configured interval, each with its own reconnect loop. A given
(pair, interval) is therefore only ever touched by one task, so the read-compare-write on
`:forming` in `handle_candle` has no concurrent writer.
"""

import asyncio
import logging
import time

import redis.asyncio as redis

from app.config import Settings
from app.market_data import candles
from app.market_data.kraken import Candle, stream_ohlc
from app.ws_manager import ws_manager
from app.ws_messages import CandleUpdateMessage

logger = logging.getLogger(__name__)

_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 30.0
# Kraken emits an ohlc update per trade; a chart only needs ~1 Hz. Forming-bar broadcasts
# are coalesced to this rate per (pair, interval); `closed=True` frames always go immediately.
_FORMING_BROADCAST_MIN_INTERVAL_MS = 1000

_last_forming_bcast_ms: dict[tuple[str, int], int] = {}


def reset_forming_throttle() -> None:
    """Test helper — clear the per-(pair, interval) broadcast-coalescing timestamps."""
    _last_forming_bcast_ms.clear()


async def run_candle_stream(settings: Settings, redis_client: redis.Redis) -> None:
    """One Kraken WS connection per configured interval (Kraken allows only one ohlc
    interval per connection). A TaskGroup so app shutdown — which cancels this task —
    propagates to every per-interval loop cleanly. No session_factory: candles never
    touch Postgres.
    """
    async with asyncio.TaskGroup() as group:
        for interval in settings.supported_candle_intervals:
            group.create_task(_stream_interval(settings, redis_client, interval))


async def _stream_interval(
    settings: Settings, redis_client: redis.Redis, interval: int
) -> None:
    """Reconnect-with-backoff loop around stream_ohlc() for one interval, mirroring
    app.price_stream's run_price_stream: every exception except CancelledError (re-raised
    so shutdown stays clean) is logged and retried with capped exponential backoff, reset
    after a clean run.
    """
    backoff = _INITIAL_BACKOFF_SECONDS
    while True:
        try:
            await stream_ohlc(
                settings.supported_pairs,
                interval,
                settings.kraken_ws_url,
                on_candle=lambda candle: handle_candle(
                    candle, settings, redis_client
                ),
                snapshot=settings.kraken_ohlc_snapshot,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "candle stream (interval=%dm) disconnected; reconnecting in %.1fs",
                interval,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)
        else:
            backoff = _INITIAL_BACKOFF_SECONDS


async def handle_candle(
    candle: Candle, settings: Settings, redis_client: redis.Redis
) -> None:
    """Public (not `_`-prefixed) so tests can drive one candle directly instead of a real
    Kraken connection. The single WS task processes frames serially, so the
    read-compare-write on `:forming` here has no concurrent writer.
    """
    prev = await candles.get_cached_forming(
        redis_client, candle.pair, candle.interval
    )

    if prev is None or candle.open_time == prev.open_time:
        await candles.set_cached_forming(
            redis_client,
            candle.pair,
            candle.interval,
            candle,
            ttl_seconds=settings.candle_forming_ttl_seconds,
        )
        await _maybe_broadcast_forming(candle)
    elif candle.open_time > prev.open_time:
        # Bucket rolled: finalise the bar we were tracking, then open the new one.
        await _broadcast(prev, closed=True)
        await candles.set_cached_forming(
            redis_client,
            candle.pair,
            candle.interval,
            candle,
            ttl_seconds=settings.candle_forming_ttl_seconds,
        )
        await _broadcast(candle, closed=False)
        _last_forming_bcast_ms[(candle.pair, candle.interval)] = _now_ms()
    # else: candle.open_time < prev.open_time — a late frame for an already-rolled bucket.


async def _maybe_broadcast_forming(candle: Candle) -> None:
    key = (candle.pair, candle.interval)
    now = _now_ms()
    if now - _last_forming_bcast_ms.get(key, 0) < _FORMING_BROADCAST_MIN_INTERVAL_MS:
        return
    _last_forming_bcast_ms[key] = now
    await _broadcast(candle, closed=False)


async def _broadcast(candle: Candle, *, closed: bool) -> None:
    await ws_manager.broadcast_candle_update(
        CandleUpdateMessage(
            pair=candle.pair,
            interval=candle.interval,
            open_time=int(candle.open_time.timestamp()),
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            closed=closed,
            broadcast_at=_now_ms(),
        )
    )


def _now_ms() -> int:
    return int(time.time() * 1000)
