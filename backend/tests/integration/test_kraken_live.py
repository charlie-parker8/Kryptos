import asyncio
from datetime import UTC, datetime

import pytest

from app.config import get_settings
from app.market_data.kraken import (
    Candle,
    get_ohlc,
    get_pair_status,
    get_ticker,
    stream_ohlc,
)


@pytest.mark.network
@pytest.mark.asyncio
async def test_get_ticker_returns_a_real_live_price() -> None:
    settings = get_settings()
    ticker = await get_ticker(
        "BTC/USD",
        base_url=settings.kraken_rest_base_url,
        timeout=settings.kraken_request_timeout_seconds,
    )

    assert ticker.pair == "BTC/USD"
    assert ticker.bid > 0
    assert ticker.ask > 0
    assert ticker.bid <= ticker.ask
    assert ticker.last > 0


@pytest.mark.network
@pytest.mark.asyncio
async def test_get_pair_status_returns_a_real_live_status() -> None:
    settings = get_settings()
    status = await get_pair_status(
        "BTC/USD",
        base_url=settings.kraken_rest_base_url,
        timeout=settings.kraken_request_timeout_seconds,
    )

    assert status.pair == "BTC/USD"
    assert status.status
    assert status.tradable == (status.status == "online")


@pytest.mark.network
@pytest.mark.asyncio
async def test_get_ohlc_returns_real_candles_with_a_trailing_forming_bucket() -> None:
    settings = get_settings()
    candles = await get_ohlc(
        "BTC/USD",
        1,
        base_url=settings.kraken_rest_base_url,
        timeout=settings.kraken_request_timeout_seconds,
    )

    assert len(candles) > 1
    assert all(c.pair == "BTC/USD" and c.interval == 1 for c in candles)
    assert candles == sorted(candles, key=lambda c: c.open_time)
    assert all(c.low <= c.high for c in candles)
    # The endpoint's last row is the still-forming bucket — its start is within the last minute.
    assert (datetime.now(UTC) - candles[-1].open_time).total_seconds() < 120


@pytest.mark.network
@pytest.mark.asyncio
async def test_stream_ohlc_delivers_a_parsed_candle() -> None:
    settings = get_settings()
    received: list[Candle] = []

    async def collect(candle: Candle) -> None:
        received.append(candle)

    task = asyncio.create_task(
        stream_ohlc(
            ["BTC/USD"], 1, settings.kraken_ws_url, on_candle=collect, snapshot=True
        )
    )
    try:
        async with asyncio.timeout(20):
            while not received:
                await asyncio.sleep(0.25)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert received[0].pair == "BTC/USD"
    assert received[0].interval == 1
    assert received[0].open > 0
