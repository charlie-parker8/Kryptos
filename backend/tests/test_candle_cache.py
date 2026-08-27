from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import redis.asyncio as redis

from app.market_data.candles import (
    _split_forming,
    get_cached_forming,
    get_cached_history,
    get_candles,
    set_cached_forming,
    set_cached_history,
)
from app.market_data.kraken import Candle

_PAIR = "BTC/USD"


def _candle(open_time: datetime, *, interval: int = 1, **overrides: object) -> Candle:
    defaults: dict[str, object] = {
        "pair": _PAIR,
        "interval": interval,
        "open_time": open_time,
        "open": Decimal("100.0"),
        "high": Decimal("101.0"),
        "low": Decimal("99.0"),
        "close": Decimal("100.5"),
        "volume": Decimal("1.5"),
        "vwap": Decimal("100.25"),
        "trades": 7,
    }
    defaults.update(overrides)
    return Candle(**defaults)  # type: ignore[arg-type]


def _series(n: int, *, interval: int = 1) -> list[Candle]:
    """`n` candles, oldest first, the last one being the still-forming current bucket."""
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    return [
        _candle(now - timedelta(minutes=interval * (n - 1 - i)), interval=interval)
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_history_round_trips_all_fields(redis_client: redis.Redis) -> None:
    series = _series(3)
    await set_cached_history(
        redis_client, _PAIR, 1, series, ttl_seconds=180, limit=500
    )

    assert await get_cached_history(redis_client, _PAIR, 1) == series


@pytest.mark.asyncio
async def test_history_absent_returns_none(redis_client: redis.Redis) -> None:
    assert await get_cached_history(redis_client, _PAIR, 5) is None


@pytest.mark.asyncio
async def test_history_is_sorted_and_trimmed_to_limit(
    redis_client: redis.Redis,
) -> None:
    series = _series(10)
    await set_cached_history(
        redis_client, _PAIR, 1, list(reversed(series)), ttl_seconds=180, limit=4
    )

    cached = await get_cached_history(redis_client, _PAIR, 1)
    assert cached == series[-4:]


@pytest.mark.asyncio
async def test_forming_round_trips(redis_client: redis.Redis) -> None:
    candle = _candle(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
    await set_cached_forming(redis_client, _PAIR, 1, candle, ttl_seconds=900)

    assert await get_cached_forming(redis_client, _PAIR, 1) == candle


@pytest.mark.asyncio
async def test_get_candles_serves_cache_hit_without_fetching(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    series = _series(500)
    await set_cached_history(
        redis_client, _PAIR, 1, series, ttl_seconds=180, limit=500
    )

    async def boom(*_: object, **__: object) -> list[Candle]:
        raise AssertionError("should not hit Kraken on a warm cache")

    monkeypatch.setattr("app.market_data.candles.get_ohlc", boom)

    result = await get_candles(
        redis_client,
        _PAIR,
        1,
        limit=500,
        base_url="http://unused.invalid",
        timeout=1.0,
        history_ttl_seconds=180,
        forming_ttl_seconds=900,
    )

    assert result == series


@pytest.mark.asyncio
async def test_get_candles_fetches_peels_forming_and_populates_on_miss(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    series = _series(50)  # last entry is the current (forming) bucket

    async def fake_get_ohlc(*_: object, **__: object) -> list[Candle]:
        return series

    monkeypatch.setattr("app.market_data.candles.get_ohlc", fake_get_ohlc)

    result = await get_candles(
        redis_client,
        _PAIR,
        1,
        limit=500,
        base_url="http://unused.invalid",
        timeout=1.0,
        history_ttl_seconds=180,
        forming_ttl_seconds=900,
    )

    # History cache holds only the closed candles; forming cache holds the last one.
    assert await get_cached_history(redis_client, _PAIR, 1) == series[:-1]
    assert await get_cached_forming(redis_client, _PAIR, 1) == series[-1]
    # And the merged result the caller sees is the whole series.
    assert result == series


@pytest.mark.asyncio
async def test_get_candles_merges_a_newer_forming_bucket_onto_history(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = _series(500)
    await set_cached_history(
        redis_client, _PAIR, 1, history, ttl_seconds=180, limit=500
    )
    forming = _candle(
        history[-1].open_time + timedelta(minutes=1), close=Decimal("123.45")
    )
    await set_cached_forming(redis_client, _PAIR, 1, forming, ttl_seconds=900)

    async def boom(*_: object, **__: object) -> list[Candle]:
        raise AssertionError("cache is warm")

    monkeypatch.setattr("app.market_data.candles.get_ohlc", boom)

    result = await get_candles(
        redis_client,
        _PAIR,
        1,
        limit=500,
        base_url="http://unused.invalid",
        timeout=1.0,
        history_ttl_seconds=180,
        forming_ttl_seconds=900,
    )

    assert result[-1] == forming
    assert len(result) == 500  # trimmed to limit after the append


@pytest.mark.asyncio
async def test_get_candles_replaces_last_history_candle_when_forming_shares_its_open_time(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = _series(10)
    await set_cached_history(
        redis_client, _PAIR, 1, history, ttl_seconds=180, limit=500
    )
    forming = _candle(history[-1].open_time, close=Decimal("999.0"))
    await set_cached_forming(redis_client, _PAIR, 1, forming, ttl_seconds=900)

    async def boom(*_: object, **__: object) -> list[Candle]:
        raise AssertionError("cache is warm")

    monkeypatch.setattr("app.market_data.candles.get_ohlc", boom)

    result = await get_candles(
        redis_client,
        _PAIR,
        1,
        limit=10,
        base_url="http://unused.invalid",
        timeout=1.0,
        history_ttl_seconds=180,
        forming_ttl_seconds=900,
    )

    assert len(result) == 10
    assert result[-1].close == Decimal("999.0")


@pytest.mark.asyncio
async def test_get_candles_serves_a_present_cache_without_refetching_to_deepen_it(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `get_candles` is the sole writer of `:history` and always writes a full fetch, so an
    # absent key is the only miss — a present-but-short history is served as-is until its TTL.
    short = _series(20)
    await set_cached_history(
        redis_client, _PAIR, 1, short, ttl_seconds=180, limit=500
    )
    calls = 0

    async def fake_get_ohlc(*_: object, **__: object) -> list[Candle]:
        nonlocal calls
        calls += 1
        return _series(400)

    monkeypatch.setattr("app.market_data.candles.get_ohlc", fake_get_ohlc)

    result = await get_candles(
        redis_client,
        _PAIR,
        1,
        limit=500,
        base_url="http://unused.invalid",
        timeout=1.0,
        history_ttl_seconds=180,
        forming_ttl_seconds=900,
    )

    assert calls == 0
    assert result == short


def test_split_forming_peels_the_trailing_in_progress_bucket() -> None:
    now = datetime(2024, 3, 1, 10, 2, 30, tzinfo=UTC)
    closed = _candle(datetime(2024, 3, 1, 10, 0, tzinfo=UTC))
    forming = _candle(datetime(2024, 3, 1, 10, 2, tzinfo=UTC))

    history, still_forming = _split_forming([closed, forming], 1, now=now)

    assert history == [closed]
    assert still_forming == forming


def test_split_forming_returns_all_when_last_bucket_is_already_closed() -> None:
    now = datetime(2024, 3, 1, 10, 5, 0, tzinfo=UTC)
    candles = [
        _candle(datetime(2024, 3, 1, 10, 0, tzinfo=UTC)),
        _candle(datetime(2024, 3, 1, 10, 1, tzinfo=UTC)),
    ]

    history, still_forming = _split_forming(candles, 1, now=now)

    assert history == candles
    assert still_forming is None
