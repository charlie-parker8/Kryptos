"""Redis-backed cache of the latest known ticker per pair.

Per CLAUDE.md, Redis holds no authoritative account/order/cash/holding state — this cache
is a repopulatable read-through layer in front of the Kraken adapter (app.market_data.kraken):
losing it costs latency and extra provider calls, never correctness. `get_latest_ticker` is
the one entry point order execution should use to obtain a validated, non-stale price.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import redis.asyncio as redis

from app.market_data.kraken import Ticker, get_ticker
from app.market_data.pricing import ensure_fresh

_KEY_PREFIX = "price"


def _key(pair: str) -> str:
    return f"{_KEY_PREFIX}:{pair}"


def _serialize(ticker: Ticker) -> str:
    return json.dumps(
        {
            "pair": ticker.pair,
            "bid": str(ticker.bid),
            "ask": str(ticker.ask),
            "last": str(ticker.last),
            "as_of": ticker.as_of.isoformat(),
        }
    )


def _deserialize(raw: bytes | str) -> Ticker:
    data = json.loads(raw)
    return Ticker(
        pair=data["pair"],
        bid=Decimal(data["bid"]),
        ask=Decimal(data["ask"]),
        last=Decimal(data["last"]),
        as_of=datetime.fromisoformat(data["as_of"]),
    )


async def get_cached_ticker(client: redis.Redis, pair: str) -> Ticker | None:
    raw = await client.get(_key(pair))
    return _deserialize(raw) if raw is not None else None


async def set_cached_ticker(
    client: redis.Redis, ticker: Ticker, *, ttl_seconds: int
) -> None:
    await client.set(_key(ticker.pair), _serialize(ticker), ex=ttl_seconds)


async def get_latest_ticker(
    client: redis.Redis,
    pair: str,
    *,
    base_url: str,
    timeout: float,
    max_age_seconds: int,
    http_client: httpx.AsyncClient | None = None,
) -> Ticker:
    """Serve the cached ticker when present, else fetch live from Kraken and repopulate
    the cache with the same `max_age_seconds` as its TTL. Either way, re-validate freshness
    (invariant 10) before returning — a cache hit can't outlive its TTL under normal
    operation, but this keeps the guarantee independent of how the entry got there.
    """
    ticker = await get_cached_ticker(client, pair)
    if ticker is None:
        ticker = await get_ticker(
            pair, base_url=base_url, timeout=timeout, client=http_client
        )
        await set_cached_ticker(client, ticker, ttl_seconds=max_age_seconds)
    ensure_fresh(ticker, max_age_seconds=max_age_seconds)
    return ticker


async def get_ticker_for_display(
    client: redis.Redis,
    pair: str,
    *,
    base_url: str,
    timeout: float,
    max_age_seconds: int,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[Ticker, bool]:
    """Same cache-or-fetch behavior as `get_latest_ticker`, but for read-only display (e.g.
    portfolio valuation) rather than an order-mutating action: invariant 10 only blocks
    cash/holdings-mutating actions on a stale price, so this never raises — it returns
    `(ticker, is_stale)` and lets the caller show a stale-flagged last-known price instead.
    """
    ticker = await get_cached_ticker(client, pair)
    if ticker is None:
        ticker = await get_ticker(
            pair, base_url=base_url, timeout=timeout, client=http_client
        )
        await set_cached_ticker(client, ticker, ttl_seconds=max_age_seconds)
    age_seconds = (datetime.now(UTC) - ticker.as_of).total_seconds()
    return ticker, age_seconds > max_age_seconds
