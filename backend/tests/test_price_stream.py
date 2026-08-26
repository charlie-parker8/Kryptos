import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import price_stream
from app.config import Settings
from app.market_data.cache import get_cached_ticker
from app.market_data.kraken import Ticker


def _ticker(pair: str = "BTC/USD", last: str = "50000") -> Ticker:
    return Ticker(
        pair=pair,
        bid=Decimal(last),
        ask=Decimal(last),
        last=Decimal(last),
        as_of=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_handle_tick_updates_the_redis_price_cache(
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await price_stream.handle_tick(
        _ticker(), test_settings, redis_client, session_factory
    )

    cached = await get_cached_ticker(redis_client, "BTC/USD")
    assert cached is not None
    assert cached.last == Decimal(50000)


@pytest.mark.asyncio
async def test_handle_tick_with_no_connected_users_does_not_raise(
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # No /ws connections are registered in this test — must be a clean no-op, not an error.
    await price_stream.handle_tick(
        _ticker(), test_settings, redis_client, session_factory
    )


@pytest.mark.asyncio
async def test_run_price_stream_reraises_cancelled_error(
    monkeypatch: pytest.MonkeyPatch, redis_client: redis.Redis, test_settings: Settings
) -> None:
    async def fake_stream_tickers(pairs: list[str], ws_url: str, *, on_tick: object) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(price_stream, "stream_tickers", fake_stream_tickers)

    with pytest.raises(asyncio.CancelledError):
        await price_stream.run_price_stream(test_settings, redis_client)


@pytest.mark.asyncio
async def test_run_price_stream_retries_after_a_transient_error(
    monkeypatch: pytest.MonkeyPatch, redis_client: redis.Redis, test_settings: Settings
) -> None:
    monkeypatch.setattr(price_stream, "_INITIAL_BACKOFF_SECONDS", 0.001)
    monkeypatch.setattr(price_stream, "_MAX_BACKOFF_SECONDS", 0.001)
    attempts = 0

    async def fake_stream_tickers(pairs: list[str], ws_url: str, *, on_tick: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated disconnect")
        raise asyncio.CancelledError  # stop the loop on the second attempt

    monkeypatch.setattr(price_stream, "stream_tickers", fake_stream_tickers)

    with pytest.raises(asyncio.CancelledError):
        await price_stream.run_price_stream(test_settings, redis_client)

    assert attempts == 2
