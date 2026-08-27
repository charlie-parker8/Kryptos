import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.market_data.fake import FakeMarketData
from app.market_data.kraken import Candle, KrakenError


async def _register(client: AsyncClient) -> None:
    await client.post(
        "/auth/register",
        json={
            "email": f"{uuid.uuid4()}@example.com",
            "username": f"u{uuid.uuid4().hex[:12]}",
            "password": "correct-horse-1",
        },
    )


def _candles(n: int, *, interval: int = 1) -> list[Candle]:
    base = datetime(2024, 1, 1, tzinfo=UTC)  # far past → all buckets already closed
    return [
        Candle(
            pair="BTC/USD",
            interval=interval,
            open_time=base + timedelta(minutes=interval * i),
            open=Decimal(100 + i),
            high=Decimal(105 + i),
            low=Decimal(95 + i),
            close=Decimal(101 + i),
            volume=Decimal(1),
        )
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_returns_candles_for_a_supported_pair_and_interval(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await _register(client)
    fake_market_data.set_candles("BTC/USD", 1, _candles(5))

    response = await client.get("/candles", params={"pair": "BTC/USD", "interval": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["pair"] == "BTC/USD"
    assert body["interval"] == 1
    assert len(body["candles"]) == 5
    first = body["candles"][0]
    assert set(first) == {"open_time", "open", "high", "low", "close", "volume"}
    assert Decimal(str(first["open"])) == Decimal(100)
    assert first["open_time"] < body["candles"][1]["open_time"]


@pytest.mark.asyncio
async def test_rejects_an_unsupported_pair(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await _register(client)

    response = await client.get("/candles", params={"pair": "DOGE/USD", "interval": 1})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_rejects_an_unsupported_interval(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await _register(client)

    response = await client.get("/candles", params={"pair": "BTC/USD", "interval": 7})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/candles", params={"pair": "BTC/USD", "interval": 1})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_maps_a_provider_failure_to_503(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register(client)

    async def boom(*_: object, **__: object) -> list[Candle]:
        raise KrakenError("kraken exploded")

    monkeypatch.setattr("app.market_data.candles.get_ohlc", boom)

    response = await client.get("/candles", params={"pair": "BTC/USD", "interval": 5})

    assert response.status_code == 503
