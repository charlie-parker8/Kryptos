import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market_data.fake import FakeMarketData
from app.market_data.kraken import KrakenError, Ticker
from app.models import Holding


def _unique_email() -> str:
    return f"{uuid.uuid4()}@example.com"


async def _register(client: AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/auth/register",
        json={"email": _unique_email(), "password": "correct-horse-1"},
    )
    return response.json()


def _headers(key: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": key or str(uuid.uuid4())}


@pytest.mark.asyncio
async def test_buy_at_exact_cash_balance_succeeds_and_zeroes_cash(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    user = await _register(client)
    cash_balance = Decimal(str(user["cash_balance"]))
    fake_market_data.set_price(
        "BTC/USD", bid=cash_balance, ask=cash_balance, last=cash_balance
    )

    response = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "1"},
        headers=_headers(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "filled"
    assert Decimal(str(body["execution_price"])) == cash_balance

    me = await client.get("/auth/me")
    assert Decimal(str(me.json()["cash_balance"])) == Decimal("0.00")
    holdings = (await client.get("/holdings")).json()
    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "BTC"
    assert Decimal(str(holdings[0]["quantity"])) == Decimal(1)


@pytest.mark.asyncio
async def test_sell_all_units_zeroes_holding_row_but_keeps_it(
    client: AsyncClient, db_session: AsyncSession, fake_market_data: FakeMarketData
) -> None:
    user = await _register(client)
    fake_market_data.set_price(
        "BTC/USD", bid=Decimal(50000), ask=Decimal(50000), last=Decimal(50000)
    )
    await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.5"},
        headers=_headers(),
    )

    sell = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "sell", "quantity": "0.5"},
        headers=_headers(),
    )
    assert sell.status_code == 201
    assert sell.json()["status"] == "filled"

    assert (await client.get("/holdings")).json() == []

    row = await db_session.scalar(
        select(Holding).where(
            Holding.user_id == uuid.UUID(str(user["id"])), Holding.symbol == "BTC"
        )
    )
    assert row is not None
    assert row.quantity == Decimal("0.0000000000")


@pytest.mark.asyncio
async def test_idempotent_replay_returns_identical_order_without_double_charge(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    user = await _register(client)
    starting_cash = Decimal(str(user["cash_balance"]))
    key = str(uuid.uuid4())
    payload = {"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"}

    first = await client.post("/orders", json=payload, headers=_headers(key))
    second = await client.post("/orders", json=payload, headers=_headers(key))

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    me = await client.get("/auth/me")
    expected_cash = starting_cash - Decimal("5000.50")  # 50005.00 (default fake ask) * 0.1
    assert Decimal(str(me.json()["cash_balance"])) == expected_cash


@pytest.mark.asyncio
async def test_buy_rejected_for_insufficient_funds(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    user = await _register(client)
    cash_balance = Decimal(str(user["cash_balance"]))
    fake_market_data.set_price(
        "BTC/USD", bid=cash_balance, ask=cash_balance, last=cash_balance
    )

    response = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "2"},
        headers=_headers(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "insufficient_funds"

    me = await client.get("/auth/me")
    assert Decimal(str(me.json()["cash_balance"])) == cash_balance


@pytest.mark.asyncio
async def test_sell_rejected_for_insufficient_holdings(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await _register(client)

    response = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "sell", "quantity": "1"},
        headers=_headers(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "insufficient_holdings"


@pytest.mark.asyncio
async def test_stale_price_rejects_order(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await _register(client)
    fake_market_data.set_stale("BTC/USD", age_seconds=999)

    response = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"},
        headers=_headers(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "stale_price"


@pytest.mark.asyncio
async def test_not_tradable_pair_rejects_order(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await _register(client)
    fake_market_data.set_status("BTC/USD", "cancel_only")

    response = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"},
        headers=_headers(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "pair_not_tradable"


@pytest.mark.asyncio
async def test_quantity_with_more_than_ten_decimal_places_returns_422_and_does_not_consume_key(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await _register(client)
    key = str(uuid.uuid4())

    invalid = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.12345678901"},
        headers=_headers(key),
    )
    assert invalid.status_code == 422

    valid = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"},
        headers=_headers(key),
    )
    assert valid.status_code == 201
    assert valid.json()["status"] == "filled"


@pytest.mark.asyncio
async def test_invalid_symbol_returns_422(client: AsyncClient) -> None:
    await _register(client)
    for symbol in ("BTC-USD", "BTC/EUR"):
        response = await client.post(
            "/orders",
            json={"symbol": symbol, "side": "buy", "quantity": "0.1"},
            headers=_headers(),
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_idempotency_key_header_returns_422(client: AsyncClient) -> None:
    await _register(client)
    response = await client.post(
        "/orders", json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_market_data_unavailable_returns_503_and_does_not_persist_order(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_market_data: FakeMarketData,
) -> None:
    await _register(client)
    key = str(uuid.uuid4())

    async def raise_kraken_error(pair: str, **_: object) -> Ticker:
        raise KrakenError("boom")

    monkeypatch.setattr("app.market_data.cache.get_ticker", raise_kraken_error)

    response = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"},
        headers=_headers(key),
    )
    assert response.status_code == 503
    assert (await client.get("/orders")).json() == []

    async def fake_get_ticker(pair: str, **_: object) -> Ticker:
        return await fake_market_data.get_ticker(pair)

    monkeypatch.setattr("app.market_data.cache.get_ticker", fake_get_ticker)

    retry = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"},
        headers=_headers(key),
    )
    assert retry.status_code == 201
    assert retry.json()["status"] == "filled"


@pytest.mark.asyncio
async def test_list_orders_before_cursor_pagination(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await _register(client)
    for _ in range(3):
        await client.post(
            "/orders",
            json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.01"},
            headers=_headers(),
        )

    first_page = await client.get("/orders", params={"limit": 2})
    assert first_page.status_code == 200
    items = first_page.json()
    assert len(items) == 2

    second_page = await client.get(
        "/orders", params={"limit": 2, "before": items[-1]["id"]}
    )
    assert second_page.status_code == 200
    remaining = second_page.json()
    assert len(remaining) == 1
    assert remaining[0]["id"] not in {item["id"] for item in items}
