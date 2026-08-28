import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import redis.asyncio as redis
from helpers import open_position, register, set_market_price
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import price_stream
from app.config import Settings
from app.market_data.cache import get_cached_ticker
from app.market_data.fake import FakeMarketData
from app.market_data.kraken import Ticker
from app.models import Position
from app.ws_manager import ws_manager


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


class _RecordingWS:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_a_tick_crossing_the_liquidation_price_liquidates_a_disconnected_holder(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register(client)
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    opened = (
        await open_position(
            client, pair="BTC/USD", side="long", collateral="1000", leverage=10
        )
    ).json()
    assert Decimal(opened["liquidation_price"]) == Decimal("45250.00000000")

    # No /ws connection for this user — liquidation must still happen.
    await price_stream.handle_tick(
        _ticker("BTC/USD", "45000"), test_settings, redis_client, session_factory
    )

    async with session_factory() as db:
        position = (
            await db.execute(
                select(Position).where(
                    Position.user_id == uuid.UUID(str(user["id"]))
                )
            )
        ).scalar_one()
        assert position.status == "liquidated"
        assert position.close_reason == "liquidation"
    assert await redis_client.smembers("positions:open:BTC/USD") == set()


@pytest.mark.asyncio
async def test_a_tick_that_does_not_cross_leaves_the_position_open(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register(client)
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    await open_position(
        client, pair="BTC/USD", side="long", collateral="1000", leverage=10
    )

    await price_stream.handle_tick(
        _ticker("BTC/USD", "46000"), test_settings, redis_client, session_factory
    )

    async with session_factory() as db:
        position = (
            await db.execute(
                select(Position).where(
                    Position.user_id == uuid.UUID(str(user["id"]))
                )
            )
        ).scalar_one()
        assert position.status == "open"


@pytest.mark.asyncio
async def test_liquidation_notifies_a_connected_holder(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register(client)
    uid = uuid.UUID(str(user["id"]))
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    await open_position(
        client, pair="BTC/USD", side="short", collateral="1000", leverage=10
    )

    fake_ws = _RecordingWS()
    ws_manager.connect(uid, fake_ws)  # type: ignore[arg-type]
    try:
        # Short liq price = 54750; a tick above it liquidates.
        await price_stream.handle_tick(
            _ticker("BTC/USD", "55000"), test_settings, redis_client, session_factory
        )
    finally:
        ws_manager.disconnect(uid, fake_ws)  # type: ignore[arg-type]

    types = [m["type"] for m in fake_ws.sent]
    assert "position_update" in types
    assert "account_update" in types
    liq = next(m for m in fake_ws.sent if m["type"] == "position_update")
    assert liq["status"] == "liquidated"
    assert liq["reason"] == "liquidation"
