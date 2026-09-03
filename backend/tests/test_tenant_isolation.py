"""Cross-account regression guard for the app-level tenant isolation audited in
docs/tenant-isolation.md. There is no database RLS backstop, so these probe the request
paths directly: a second account must never see or touch the first account's rows.
"""

from decimal import Decimal

import pytest
import redis.asyncio as redis
from helpers import open_position, register, set_market_price
from httpx import AsyncClient

from app.market_data.fake import FakeMarketData

pytestmark = pytest.mark.usefixtures("fake_market_data")


@pytest.mark.asyncio
async def test_cannot_close_another_users_position(
    client: AsyncClient,
    redis_client: redis.Redis,
    fake_market_data: FakeMarketData,
) -> None:
    # Account A opens a position.
    await register(client)
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    opened = await open_position(
        client, pair="BTC/USD", side="long", collateral="1000"
    )
    other_position_id = opened.json()["id"]

    # Account B (same client, new session) tries to close it.
    await register(client)
    resp = await client.post(f"/positions/{other_position_id}/close")
    assert resp.status_code == 404  # not found *for this caller*, never 200


@pytest.mark.asyncio
async def test_positions_list_is_scoped_to_the_caller(
    client: AsyncClient,
    redis_client: redis.Redis,
    fake_market_data: FakeMarketData,
) -> None:
    await register(client)
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    await open_position(client, pair="BTC/USD", side="long", collateral="1000")

    await register(client)  # account B
    rows = (await client.get("/positions?status=all")).json()
    assert rows == []


@pytest.mark.asyncio
async def test_portfolio_snapshot_never_leaks_another_account(
    client: AsyncClient,
    redis_client: redis.Redis,
    fake_market_data: FakeMarketData,
) -> None:
    await register(client)
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    await open_position(client, pair="BTC/USD", side="long", collateral="1000")

    await register(client)  # account B
    snapshot = (await client.get("/portfolio")).json()
    assert snapshot["positions"] == []
    assert Decimal(str(snapshot["free_cash"])) == Decimal("10000.00")
