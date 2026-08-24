from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import redis.asyncio as redis

from app.market_data.cache import (
    get_cached_ticker,
    get_latest_ticker,
    set_cached_ticker,
)
from app.market_data.kraken import Ticker
from app.market_data.pricing import StalePriceError


def _ticker(**overrides: object) -> Ticker:
    defaults: dict[str, object] = {
        "pair": "BTC/USD",
        "bid": Decimal("49995.00"),
        "ask": Decimal("50005.00"),
        "last": Decimal("50000.00"),
        "as_of": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Ticker(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_cached_ticker_returns_none_when_absent(
    redis_client: redis.Redis,
) -> None:
    assert await get_cached_ticker(redis_client, "BTC/USD") is None


@pytest.mark.asyncio
async def test_set_then_get_round_trips_all_fields(redis_client: redis.Redis) -> None:
    ticker = _ticker()
    await set_cached_ticker(redis_client, ticker, ttl_seconds=10)

    cached = await get_cached_ticker(redis_client, ticker.pair)

    assert cached == ticker


@pytest.mark.asyncio
async def test_get_latest_ticker_serves_cache_hit_without_fetching(
    redis_client: redis.Redis,
) -> None:
    ticker = _ticker()
    await set_cached_ticker(redis_client, ticker, ttl_seconds=10)

    result = await get_latest_ticker(
        redis_client,
        ticker.pair,
        base_url="http://unused.invalid",
        timeout=1.0,
        max_age_seconds=10,
    )

    assert result == ticker


@pytest.mark.asyncio
async def test_get_latest_ticker_fetches_and_populates_cache_on_miss(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched = _ticker()

    async def fake_get_ticker(pair: str, **_: object) -> Ticker:
        return fetched

    monkeypatch.setattr("app.market_data.cache.get_ticker", fake_get_ticker)

    result = await get_latest_ticker(
        redis_client,
        fetched.pair,
        base_url="http://unused.invalid",
        timeout=1.0,
        max_age_seconds=10,
    )

    assert result == fetched
    assert await get_cached_ticker(redis_client, fetched.pair) == fetched


@pytest.mark.asyncio
async def test_get_latest_ticker_rejects_a_stale_cache_entry_even_if_not_yet_expired(
    redis_client: redis.Redis,
) -> None:
    stale = _ticker(as_of=datetime.now(UTC) - timedelta(seconds=999))
    # A long TTL so the entry wouldn't expire on its own — freshness must be enforced
    # independently of whatever TTL happened to be used when the entry was cached.
    await set_cached_ticker(redis_client, stale, ttl_seconds=9999)

    with pytest.raises(StalePriceError):
        await get_latest_ticker(
            redis_client,
            stale.pair,
            base_url="http://unused.invalid",
            timeout=1.0,
            max_age_seconds=10,
        )
