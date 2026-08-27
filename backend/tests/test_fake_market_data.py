from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market_data.fake import FakeMarketData
from app.market_data.kraken import Candle


@pytest.mark.asyncio
async def test_default_ticker_is_seeded_and_internally_consistent() -> None:
    fake = FakeMarketData()
    ticker = await fake.get_ticker("BTC/USD")
    assert ticker.bid < ticker.ask


@pytest.mark.asyncio
async def test_get_ticker_raises_for_unseeded_pair() -> None:
    fake = FakeMarketData()
    with pytest.raises(KeyError):
        await fake.get_ticker("DOGE/USD")


@pytest.mark.asyncio
async def test_set_price_overrides_seeded_values() -> None:
    fake = FakeMarketData()
    fake.set_price("BTC/USD", bid=Decimal(1), ask=Decimal(2), last=Decimal("1.5"))

    ticker = await fake.get_ticker("BTC/USD")

    assert ticker.bid == Decimal(1)
    assert ticker.ask == Decimal(2)


@pytest.mark.asyncio
async def test_set_stale_backdates_the_quote() -> None:
    fake = FakeMarketData()
    fake.set_stale("BTC/USD", age_seconds=999)

    ticker = await fake.get_ticker("BTC/USD")

    assert datetime.now(UTC) - ticker.as_of >= timedelta(seconds=999)


@pytest.mark.asyncio
async def test_default_status_is_tradable() -> None:
    fake = FakeMarketData()
    status = await fake.get_pair_status("BTC/USD")
    assert status.tradable is True
    assert status.status == "online"


@pytest.mark.asyncio
async def test_set_status_can_mark_a_pair_not_tradable() -> None:
    fake = FakeMarketData()
    fake.set_status("BTC/USD", "cancel_only")

    status = await fake.get_pair_status("BTC/USD")

    assert status.tradable is False
    assert status.status == "cancel_only"


@pytest.mark.asyncio
async def test_get_ohlc_returns_seeded_candles_and_empty_by_default() -> None:
    fake = FakeMarketData()
    assert await fake.get_ohlc("BTC/USD", 1) == []

    candle = Candle(
        pair="BTC/USD",
        interval=5,
        open_time=datetime(2024, 1, 1, tzinfo=UTC),
        open=Decimal(100),
        high=Decimal(101),
        low=Decimal(99),
        close=Decimal(100),
        volume=Decimal(1),
    )
    fake.set_candles("BTC/USD", 5, [candle])

    assert await fake.get_ohlc("BTC/USD", 5) == [candle]
    assert await fake.get_ohlc("BTC/USD", 1) == []  # other intervals untouched


@pytest.mark.asyncio
async def test_instances_do_not_share_state() -> None:
    first = FakeMarketData()
    second = FakeMarketData()

    first.set_status("BTC/USD", "maintenance")

    assert (await first.get_pair_status("BTC/USD")).tradable is False
    assert (await second.get_pair_status("BTC/USD")).tradable is True
