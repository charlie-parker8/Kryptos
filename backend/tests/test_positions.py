"""HTTP-level open / close / list. A business rejection is a 4xx that persists nothing; a
provider outage is a 503 that persists nothing and leaves the idempotency key unconsumed.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import redis.asyncio as redis
from helpers import (
    STARTING_CASH,
    close_position,
    open_position,
    register,
    set_market_price,
)
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.market_data.cache import set_cached_ticker
from app.market_data.fake import FakeMarketData
from app.market_data.kraken import Ticker
from app.models import LedgerEntry, Position

pytestmark = pytest.mark.usefixtures("fake_market_data")


@pytest.mark.asyncio
async def test_open_long_debits_collateral_and_stores_derived_fields(
    client: AsyncClient,
) -> None:
    await register(client)
    response = await open_position(
        client, pair="BTC/USD", side="long", collateral="1000", leverage=10
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "open"
    assert body["side"] == "long"
    assert Decimal(body["entry_price"]) == Decimal("50000.00000000")
    assert Decimal(body["size"]) == Decimal("0.2000000000")
    assert Decimal(body["liquidation_price"]) == Decimal("45250.00000000")

    me = (await client.get("/auth/me")).json()
    assert Decimal(me["cash_balance"]) == STARTING_CASH - Decimal("1000.00")

    portfolio = (await client.get("/portfolio")).json()
    assert Decimal(portfolio["free_cash"]) == Decimal("9000.00")
    assert len(portfolio["positions"]) == 1


@pytest.mark.asyncio
async def test_open_short_liquidation_price_is_above_entry(
    client: AsyncClient,
) -> None:
    await register(client)
    body = (
        await open_position(client, side="short", collateral="1000", leverage=10)
    ).json()
    assert Decimal(body["liquidation_price"]) == Decimal("54750.00000000")


@pytest.mark.asyncio
async def test_exact_free_cash_open_is_allowed(client: AsyncClient) -> None:
    await register(client)
    response = await open_position(client, collateral="10000", leverage=2)
    assert response.status_code == 201
    me = (await client.get("/auth/me")).json()
    assert Decimal(me["cash_balance"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_open_more_collateral_than_free_cash_is_rejected(
    client: AsyncClient,
) -> None:
    await register(client)
    response = await open_position(client, collateral="10000.01", leverage=2)
    assert response.status_code == 402


@pytest.mark.asyncio
async def test_open_below_min_collateral_is_rejected(client: AsyncClient) -> None:
    await register(client)
    response = await open_position(client, collateral="5", leverage=2)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_open_with_a_leverage_outside_the_presets_is_rejected(
    client: AsyncClient,
) -> None:
    await register(client)
    response = await open_position(client, collateral="1000", leverage=3)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_second_open_on_the_same_pair_is_rejected(client: AsyncClient) -> None:
    await register(client)
    assert (await open_position(client, pair="BTC/USD")).status_code == 201
    clash = await open_position(client, pair="BTC/USD", side="short")
    assert clash.status_code == 409


@pytest.mark.asyncio
async def test_a_long_and_a_short_on_different_pairs_coexist(
    client: AsyncClient,
) -> None:
    await register(client)
    assert (
        await open_position(client, pair="BTC/USD", side="long", collateral="1000")
    ).status_code == 201
    assert (
        await open_position(client, pair="ETH/USD", side="short", collateral="1000")
    ).status_code == 201


@pytest.mark.asyncio
async def test_stale_price_blocks_the_open(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await register(client)
    fake_market_data.set_stale("BTC/USD", age_seconds=60)
    response = await open_position(client)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_a_paused_pair_blocks_the_open(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await register(client)
    fake_market_data.set_status("BTC/USD", "maintenance")
    response = await open_position(client)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_provider_outage_is_503_and_persists_nothing(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register(client)

    async def boom(*_: object, **__: object) -> object:
        raise httpx.ConnectError("kraken unreachable")

    monkeypatch.setattr("app.market_data.cache.get_ticker", boom)

    key = str(uuid.uuid4())
    first = await open_position(client, key=key)
    assert first.status_code == 503

    async with session_factory() as db:
        rows = (
            await db.execute(
                select(Position).where(
                    Position.user_id == uuid.UUID(str(user["id"]))
                )
            )
        ).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_open_is_idempotent_on_replay(client: AsyncClient) -> None:
    await register(client)
    key = str(uuid.uuid4())
    first = await open_position(client, key=key)
    second = await open_position(client, key=key, collateral="9999")  # ignored on replay
    assert first.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    me = (await client.get("/auth/me")).json()
    assert Decimal(me["cash_balance"]) == STARTING_CASH - Decimal("1000.00")


@pytest.mark.asyncio
async def test_close_settles_pnl_and_returns_cash(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    redis_client: redis.Redis,
) -> None:
    await register(client)
    opened = (await open_position(client, side="long", collateral="1000")).json()

    # Price rises 2% -> long P&L = 0.2 * (51000 - 50000) = +$200.
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "51000")
    closed = await close_position(client, opened["id"])
    assert closed.status_code == 200
    body = closed.json()
    assert body["status"] == "closed"
    assert body["close_reason"] == "user"
    assert Decimal(body["realized_pnl"]) == Decimal("200.00")

    me = (await client.get("/auth/me")).json()
    assert Decimal(me["cash_balance"]) == STARTING_CASH + Decimal("200.00")


@pytest.mark.asyncio
async def test_close_is_idempotent(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await register(client)
    opened = (await open_position(client)).json()
    first = await close_position(client, opened["id"])
    second = await close_position(client, opened["id"])
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["realized_pnl"] == second.json()["realized_pnl"]

    me = (await client.get("/auth/me")).json()
    # collateral + pnl returned exactly once (price unchanged -> pnl 0)
    assert Decimal(me["cash_balance"]) == STARTING_CASH


@pytest.mark.asyncio
async def test_close_a_missing_position_is_404(client: AsyncClient) -> None:
    await register(client)
    response = await close_position(client, str(uuid.uuid4()))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_close_with_a_stale_price_is_409(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    redis_client: redis.Redis,
) -> None:
    await register(client)
    opened = (await open_position(client)).json()
    # Poison the price cache with a back-dated quote — invariant 10 blocks a user close.
    await set_cached_ticker(
        redis_client,
        Ticker(
            pair="BTC/USD",
            bid=Decimal(50000),
            ask=Decimal(50000),
            last=Decimal(50000),
            as_of=datetime.now(UTC) - timedelta(seconds=60),
        ),
        ttl_seconds=120,
    )
    response = await close_position(client, opened["id"])
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_ledger_records_open_then_close(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register(client)
    opened = (await open_position(client)).json()
    await close_position(client, opened["id"])

    async with session_factory() as db:
        entries = (
            await db.execute(
                select(LedgerEntry)
                .where(LedgerEntry.user_id == uuid.UUID(str(user["id"])))
                .order_by(LedgerEntry.created_at)
            )
        ).scalars().all()
    assert [e.entry_type for e in entries] == ["position_open", "position_close"]


@pytest.mark.asyncio
async def test_list_positions_filters_by_status(
    client: AsyncClient, fake_market_data: FakeMarketData
) -> None:
    await register(client)
    a = (await open_position(client, pair="BTC/USD")).json()
    await open_position(client, pair="ETH/USD")
    await close_position(client, a["id"])

    all_rows = (await client.get("/positions?status=all")).json()
    open_rows = (await client.get("/positions?status=open")).json()
    closed_rows = (await client.get("/positions?status=closed")).json()
    assert len(all_rows) == 2
    assert {r["pair"] for r in open_rows} == {"ETH/USD"}
    assert {r["pair"] for r in closed_rows} == {"BTC/USD"}


@pytest.mark.asyncio
async def test_position_index_tracks_open_positions(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    redis_client: redis.Redis,
) -> None:
    await register(client)
    opened = (await open_position(client, pair="BTC/USD")).json()
    members = await redis_client.smembers("positions:open:BTC/USD")
    assert {m.decode() for m in members} == {opened["id"]}

    await close_position(client, opened["id"])
    assert await redis_client.smembers("positions:open:BTC/USD") == set()
