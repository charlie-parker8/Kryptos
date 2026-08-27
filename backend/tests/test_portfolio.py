import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import redis.asyncio as redis
from httpx import AsyncClient

from app.config import get_settings
from app.market_data.cache import set_cached_ticker
from app.market_data.fake import FakeMarketData
from app.market_data.kraken import Ticker
from app.models import Holding
from app.portfolio import value_holding


def _holding(*, symbol: str = "BTC", quantity: str, average_cost: str) -> Holding:
    return Holding(
        symbol=symbol, quantity=Decimal(quantity), average_cost=Decimal(average_cost)
    )


def _ticker(*, last: str, pair: str = "BTC/USD") -> Ticker:
    return Ticker(
        pair=pair,
        bid=Decimal(last),
        ask=Decimal(last),
        last=Decimal(last),
        as_of=datetime.now(UTC),
    )


def test_value_holding_uses_last_price_not_bid_ask() -> None:
    holding = _holding(quantity="0.5", average_cost="40000.00000000")
    ticker = Ticker(
        pair="BTC/USD",
        bid=Decimal(49900),
        ask=Decimal(50100),
        last=Decimal(50000),
        as_of=datetime.now(UTC),
    )

    result = value_holding(holding, ticker, stale=False)

    assert result.current_price == Decimal(50000)
    assert result.market_value == Decimal("25000.00")
    assert result.stale is False


def test_value_holding_rounds_market_value_half_up_to_cents() -> None:
    holding = _holding(quantity="0.333", average_cost="1")
    ticker = _ticker(last="100.005")

    result = value_holding(holding, ticker, stale=False)

    # 100.005 * 0.333 = 33.301665 -> half-up at the cent
    assert result.market_value == Decimal("33.30")


def test_value_holding_flags_stale_but_still_returns_last_known_price() -> None:
    holding = _holding(quantity="1", average_cost="50000")
    ticker = _ticker(last="51000")

    result = value_holding(holding, ticker, stale=True)

    assert result.stale is True
    assert result.current_price == Decimal(51000)
    assert result.market_value == Decimal("51000.00")


def test_value_holding_with_no_ticker_returns_null_price_and_forces_stale() -> None:
    holding = _holding(quantity="1", average_cost="50000")

    result = value_holding(holding, None, stale=False)

    assert result.current_price is None
    assert result.market_value is None
    assert result.stale is True


def _headers(key: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": key or str(uuid.uuid4())}


async def _register(client: AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/auth/register",
        json={
            "email": f"{uuid.uuid4()}@example.com",
            "username": f"u{uuid.uuid4().hex[:12]}",
            "password": "correct-horse-1",
        },
    )
    return response.json()


@pytest.mark.asyncio
async def test_portfolio_with_no_holdings_equals_cash_balance(
    client: AsyncClient,
) -> None:
    user = await _register(client)

    response = await client.get("/portfolio")

    assert response.status_code == 200
    body = response.json()
    assert Decimal(str(body["cash_balance"])) == Decimal(str(user["cash_balance"]))
    assert body["holdings"] == []
    assert Decimal(str(body["net_worth"])) == Decimal(str(user["cash_balance"]))


@pytest.mark.asyncio
async def test_portfolio_reflects_a_filled_buy(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    user = await _register(client)
    starting_cash = Decimal(str(user["cash_balance"]))
    fake_market_data.set_price(
        "BTC/USD", bid=Decimal(50000), ask=Decimal(50000), last=Decimal(50000)
    )
    await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"},
        headers=_headers(),
    )

    response = await client.get("/portfolio")

    assert response.status_code == 200
    body = response.json()
    assert len(body["holdings"]) == 1
    holding = body["holdings"][0]
    assert holding["symbol"] == "BTC"
    assert Decimal(str(holding["quantity"])) == Decimal("0.1")
    assert Decimal(str(holding["current_price"])) == Decimal(50000)
    assert Decimal(str(holding["market_value"])) == Decimal("5000.00")
    assert holding["stale"] is False
    assert Decimal(str(body["cash_balance"])) == starting_cash - Decimal("5000.00")
    assert Decimal(str(body["net_worth"])) == starting_cash


@pytest.mark.asyncio
async def test_portfolio_flags_stale_price_instead_of_blocking(
    client: AsyncClient, fake_market_data: FakeMarketData, redis_client: redis.Redis
) -> None:
    await _register(client)
    fake_market_data.set_price(
        "BTC/USD", bid=Decimal(50000), ask=Decimal(50000), last=Decimal(50000)
    )
    await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"},
        headers=_headers(),
    )

    # The buy above just cached a *fresh* ticker, so overwrite it with a back-dated one —
    # otherwise this test would need to sleep out a real TTL to observe staleness.
    max_age = get_settings().price_max_age_seconds
    stale_ticker = Ticker(
        pair="BTC/USD",
        bid=Decimal(50000),
        ask=Decimal(50000),
        last=Decimal(50000),
        as_of=datetime.now(UTC) - timedelta(seconds=max_age + 5),
    )
    await set_cached_ticker(redis_client, stale_ticker, ttl_seconds=max_age + 5)

    response = await client.get("/portfolio")

    assert response.status_code == 200
    holding = response.json()["holdings"][0]
    assert holding["stale"] is True
    assert Decimal(str(holding["current_price"])) == Decimal(50000)
