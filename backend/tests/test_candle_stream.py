import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import redis.asyncio as redis

from app import candle_stream
from app.config import Settings
from app.market_data.candles import get_cached_forming
from app.market_data.kraken import Candle
from app.ws_messages import CandleUpdateMessage

_T0 = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)


def _candle(
    open_time: datetime, *, pair: str = "BTC/USD", interval: int = 1, close: str = "100"
) -> Candle:
    return Candle(
        pair=pair,
        interval=interval,
        open_time=open_time,
        open=Decimal(100),
        high=Decimal(101),
        low=Decimal(99),
        close=Decimal(close),
        volume=Decimal(1),
    )


@pytest.fixture(autouse=True)
def _clean_throttle() -> Iterator[None]:
    candle_stream.reset_forming_throttle()
    yield
    candle_stream.reset_forming_throttle()


@pytest.fixture
def broadcasts(monkeypatch: pytest.MonkeyPatch) -> list[CandleUpdateMessage]:
    captured: list[CandleUpdateMessage] = []

    async def fake_broadcast(message: CandleUpdateMessage) -> None:
        captured.append(message)

    monkeypatch.setattr(
        "app.ws_manager.ws_manager.broadcast_candle_update", fake_broadcast
    )
    return captured


@pytest.mark.asyncio
async def test_handle_candle_caches_and_broadcasts_the_forming_bucket(
    redis_client: redis.Redis,
    test_settings: Settings,
    broadcasts: list[CandleUpdateMessage],
) -> None:
    candle = _candle(_T0)

    await candle_stream.handle_candle(candle, test_settings, redis_client)

    assert await get_cached_forming(redis_client, "BTC/USD", 1) == candle
    assert len(broadcasts) == 1
    assert broadcasts[0].closed is False
    assert broadcasts[0].open_time == int(_T0.timestamp())


@pytest.mark.asyncio
async def test_same_bucket_update_refreshes_the_cache(
    redis_client: redis.Redis,
    test_settings: Settings,
    broadcasts: list[CandleUpdateMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [10_000]
    monkeypatch.setattr(candle_stream, "_now_ms", lambda: clock[0])

    await candle_stream.handle_candle(_candle(_T0, close="100"), test_settings, redis_client)
    clock[0] += 200  # within the coalescing window
    await candle_stream.handle_candle(_candle(_T0, close="105"), test_settings, redis_client)

    cached = await get_cached_forming(redis_client, "BTC/USD", 1)
    assert cached is not None and cached.close == Decimal(105)
    assert len(broadcasts) == 1  # the second update was coalesced away


@pytest.mark.asyncio
async def test_bucket_roll_emits_closed_then_the_new_forming_bar(
    redis_client: redis.Redis,
    test_settings: Settings,
    broadcasts: list[CandleUpdateMessage],
) -> None:
    first = _candle(_T0, close="100")
    second = _candle(_T0 + timedelta(minutes=1), close="110")

    await candle_stream.handle_candle(first, test_settings, redis_client)
    await candle_stream.handle_candle(second, test_settings, redis_client)

    assert [(m.open_time, m.closed) for m in broadcasts] == [
        (int(_T0.timestamp()), False),
        (int(_T0.timestamp()), True),
        (int(second.open_time.timestamp()), False),
    ]
    assert await get_cached_forming(redis_client, "BTC/USD", 1) == second


@pytest.mark.asyncio
async def test_a_late_frame_for_an_already_rolled_bucket_is_ignored(
    redis_client: redis.Redis,
    test_settings: Settings,
    broadcasts: list[CandleUpdateMessage],
) -> None:
    current = _candle(_T0 + timedelta(minutes=1))
    stale = _candle(_T0)

    await candle_stream.handle_candle(current, test_settings, redis_client)
    await candle_stream.handle_candle(stale, test_settings, redis_client)

    assert len(broadcasts) == 1
    assert await get_cached_forming(redis_client, "BTC/USD", 1) == current


@pytest.mark.asyncio
async def test_forming_broadcasts_coalesce_to_one_per_second(
    redis_client: redis.Redis,
    test_settings: Settings,
    broadcasts: list[CandleUpdateMessage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1_000]
    monkeypatch.setattr(candle_stream, "_now_ms", lambda: clock[0])

    await candle_stream.handle_candle(_candle(_T0, close="1"), test_settings, redis_client)
    clock[0] = 1_500
    await candle_stream.handle_candle(_candle(_T0, close="2"), test_settings, redis_client)
    clock[0] = 2_000
    await candle_stream.handle_candle(_candle(_T0, close="3"), test_settings, redis_client)

    assert [m.close for m in broadcasts] == [Decimal(1), Decimal(3)]


@pytest.mark.asyncio
async def test_run_candle_stream_starts_one_stream_per_configured_interval(
    monkeypatch: pytest.MonkeyPatch, redis_client: redis.Redis, test_settings: Settings
) -> None:
    started: list[int] = []

    async def fake_stream_interval(
        _settings: Settings, _redis: redis.Redis, interval: int
    ) -> None:
        started.append(interval)

    monkeypatch.setattr(candle_stream, "_stream_interval", fake_stream_interval)

    await candle_stream.run_candle_stream(test_settings, redis_client)

    assert sorted(started) == sorted(test_settings.supported_candle_intervals)


@pytest.mark.asyncio
async def test_stream_interval_reraises_cancelled_error(
    monkeypatch: pytest.MonkeyPatch, redis_client: redis.Redis, test_settings: Settings
) -> None:
    async def fake_stream_ohlc(*_: object, **__: object) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(candle_stream, "stream_ohlc", fake_stream_ohlc)

    with pytest.raises(asyncio.CancelledError):
        await candle_stream._stream_interval(test_settings, redis_client, 1)


@pytest.mark.asyncio
async def test_stream_interval_retries_after_a_transient_error(
    monkeypatch: pytest.MonkeyPatch, redis_client: redis.Redis, test_settings: Settings
) -> None:
    monkeypatch.setattr(candle_stream, "_INITIAL_BACKOFF_SECONDS", 0.001)
    monkeypatch.setattr(candle_stream, "_MAX_BACKOFF_SECONDS", 0.001)
    attempts = 0

    async def fake_stream_ohlc(*_: object, **__: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated disconnect")
        raise asyncio.CancelledError

    monkeypatch.setattr(candle_stream, "stream_ohlc", fake_stream_ohlc)

    with pytest.raises(asyncio.CancelledError):
        await candle_stream._stream_interval(test_settings, redis_client, 5)

    assert attempts == 2
