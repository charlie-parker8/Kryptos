"""Redis-backed cache of recent OHLC candles per (pair, interval).

Per CLAUDE.md, Redis holds no authoritative market data — this is a repopulatable
read-through layer in front of Kraken's REST OHLC endpoint (app.market_data.kraken).
Losing it costs a provider round-trip, never a financial record (invariant 8).

Two keys per (pair, interval):
  candles:{pair}:{interval}:history  — JSON list of *closed* candles, ascending by open
                                       time, short TTL (closed bars barely move, and the
                                       live feed + a periodic refetch cover recency).
  candles:{pair}:{interval}:forming  — JSON of the single still-forming bucket, kept
                                       current by app.candle_stream from the WS ohlc feed.

`get_candles` merges the forming bar onto the history tail so a REST poll and the live WS
stream never disagree on the current candle.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import redis.asyncio as redis

from app.market_data.kraken import Candle, get_ohlc

_KEY_PREFIX = "candles"


def _history_key(pair: str, interval: int) -> str:
    return f"{_KEY_PREFIX}:{pair}:{interval}:history"


def _forming_key(pair: str, interval: int) -> str:
    return f"{_KEY_PREFIX}:{pair}:{interval}:forming"


def _candle_to_dict(candle: Candle) -> dict[str, Any]:
    return {
        "t": int(candle.open_time.timestamp()),
        "o": str(candle.open),
        "h": str(candle.high),
        "l": str(candle.low),
        "c": str(candle.close),
        "v": str(candle.volume),
        "vw": str(candle.vwap) if candle.vwap is not None else None,
        "n": candle.trades,
    }


def _candle_from_dict(data: dict[str, Any], *, pair: str, interval: int) -> Candle:
    return Candle(
        pair=pair,
        interval=interval,
        open_time=datetime.fromtimestamp(int(data["t"]), tz=UTC),
        open=Decimal(data["o"]),
        high=Decimal(data["h"]),
        low=Decimal(data["l"]),
        close=Decimal(data["c"]),
        volume=Decimal(data["v"]),
        vwap=Decimal(data["vw"]) if data.get("vw") is not None else None,
        trades=data.get("n"),
    )


async def get_cached_history(
    client: redis.Redis, pair: str, interval: int
) -> list[Candle] | None:
    raw = await client.get(_history_key(pair, interval))
    if raw is None:
        return None
    return [_candle_from_dict(d, pair=pair, interval=interval) for d in json.loads(raw)]


async def set_cached_history(
    client: redis.Redis,
    pair: str,
    interval: int,
    candles: list[Candle],
    *,
    ttl_seconds: int,
    limit: int,
) -> None:
    trimmed = sorted(candles, key=lambda c: c.open_time)[-limit:]
    await client.set(
        _history_key(pair, interval),
        json.dumps([_candle_to_dict(c) for c in trimmed]),
        ex=ttl_seconds,
    )


async def get_cached_forming(
    client: redis.Redis, pair: str, interval: int
) -> Candle | None:
    raw = await client.get(_forming_key(pair, interval))
    if raw is None:
        return None
    return _candle_from_dict(json.loads(raw), pair=pair, interval=interval)


async def set_cached_forming(
    client: redis.Redis,
    pair: str,
    interval: int,
    candle: Candle,
    *,
    ttl_seconds: int,
) -> None:
    await client.set(
        _forming_key(pair, interval),
        json.dumps(_candle_to_dict(candle)),
        ex=ttl_seconds,
    )


def _split_forming(
    candles: list[Candle], interval: int, *, now: datetime | None = None
) -> tuple[list[Candle], Candle | None]:
    """Kraken's REST OHLC returns the still-forming bucket as its final row. Peel it off so
    only closed candles reach the history cache. `now` is injectable for deterministic tests.
    """
    if not candles:
        return [], None
    ordered = sorted(candles, key=lambda c: c.open_time)
    now = now if now is not None else datetime.now(UTC)
    if ordered[-1].open_time + timedelta(minutes=interval) > now:
        return ordered[:-1], ordered[-1]
    return ordered, None


async def get_candles(
    client: redis.Redis,
    pair: str,
    interval: int,
    *,
    limit: int,
    base_url: str,
    timeout: float,
    history_ttl_seconds: int,
    forming_ttl_seconds: int,
    http_client: httpx.AsyncClient | None = None,
) -> list[Candle]:
    """Serve cached closed-candle history when present, else backfill from Kraken's REST
    OHLC endpoint and repopulate the cache (a short TTL, so a poll refreshes it). The
    forming bucket (kept current by app.candle_stream) is merged onto the tail. Returns the
    last `limit` candles, ascending by open time.

    `get_candles` is the only writer of `:history`, and always writes a full fetch — so an
    absent key is the only miss condition, exactly like app.market_data.cache's ticker cache.
    """
    history = await get_cached_history(client, pair, interval)
    if history is None:
        raw = await get_ohlc(
            pair, interval, base_url=base_url, timeout=timeout, client=http_client
        )
        history, forming = _split_forming(raw, interval)
        await set_cached_history(
            client,
            pair,
            interval,
            history,
            ttl_seconds=history_ttl_seconds,
            limit=limit,
        )
        if forming is not None:
            await set_cached_forming(
                client, pair, interval, forming, ttl_seconds=forming_ttl_seconds
            )

    forming = await get_cached_forming(client, pair, interval)
    merged = list(history)
    if forming is not None and (not merged or forming.open_time >= merged[-1].open_time):
        if merged and forming.open_time == merged[-1].open_time:
            merged[-1] = forming
        else:
            merged.append(forming)
    return merged[-limit:]
