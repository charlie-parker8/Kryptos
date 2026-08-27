import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import redis.asyncio as redis
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import bankruptcy, price_stream
from app.config import Settings
from app.market_data.cache import set_cached_ticker
from app.market_data.fake import FakeMarketData
from app.market_data.kraken import Ticker
from app.models import Holding, LedgerEntry, Order, User
from app.ws_manager import ws_manager

_START = Decimal("100000.00")


class _RecordingWS:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def _register(client: AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/auth/register",
        json={
            "email": f"{uuid.uuid4()}@example.com",
            "username": f"u{uuid.uuid4().hex[:12]}",
            "password": "correct-horse-1",
        },
    )
    assert response.status_code == 201
    return response.json()


async def _go_all_in_then_crash_price(
    client: AsyncClient,
    redis_client: redis.Redis,
    fake_market_data: FakeMarketData,
    *,
    stale: bool = False,
) -> uuid.UUID:
    """Register a user, spend the entire balance on 1 BTC at $100k, then move the cached
    price to ~$0 so net worth rounds to $0. Returns the user id.
    """
    user = await _register(client)
    fake_market_data.set_price(
        "BTC/USD", bid=_START, ask=_START, last=_START
    )
    fill = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "1"},
        headers=_headers(),
    )
    assert fill.json()["status"] == "filled"

    as_of = datetime.now(UTC)
    if stale:
        as_of -= timedelta(seconds=60)
    crash = Ticker(
        pair="BTC/USD",
        bid=Decimal("0.001"),
        ask=Decimal("0.001"),
        last=Decimal("0.001"),
        as_of=as_of,
    )
    await set_cached_ticker(redis_client, crash, ttl_seconds=120)
    return uuid.UUID(str(user["id"]))


@pytest.mark.asyncio
async def test_solvent_account_is_never_reset(
    client: AsyncClient,
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await _register(client)
    uid = uuid.UUID(str(user["id"]))

    async with session_factory() as db:
        result = await bankruptcy.maybe_reset_bankrupt_account(
            db, redis_client, test_settings, user_id=uid
        )
    assert result is None

    async with session_factory() as db:
        refreshed = await db.get(User, uid)
        assert refreshed is not None
        assert refreshed.cash_balance == _START


@pytest.mark.asyncio
async def test_bankrupt_account_is_reset_and_history_preserved(
    client: AsyncClient,
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _go_all_in_then_crash_price(
        client, redis_client, fake_market_data
    )

    async with session_factory() as db:
        reset = await bankruptcy.maybe_reset_bankrupt_account(
            db, redis_client, test_settings, user_id=uid
        )

    assert reset is not None
    assert reset.cleared_symbols == ["BTC"]
    assert reset.starting_cash_balance == _START

    async with session_factory() as db:
        user = await db.get(User, uid)
        assert user is not None
        assert user.cash_balance == _START  # invariant 12: starting cash restored

        holdings = (
            (await db.execute(select(Holding).where(Holding.user_id == uid)))
            .scalars()
            .all()
        )
        assert all(h.quantity == 0 for h in holdings)  # active holdings cleared

        orders = (
            (await db.execute(select(Order).where(Order.user_id == uid)))
            .scalars()
            .all()
        )
        assert len(orders) == 1  # the buy is preserved

        ledger = (
            (
                await db.execute(
                    select(LedgerEntry)
                    .where(LedgerEntry.user_id == uid)
                    .order_by(LedgerEntry.created_at)
                )
            )
            .scalars()
            .all()
        )
        assert [entry.entry_type for entry in ledger] == [
            "order_buy",
            "bankruptcy_reset",
        ]
        reset_entry = ledger[-1]
        assert reset_entry.cash_balance_after == _START
        assert reset_entry.cash_delta == _START  # 0 -> 100000
        assert reset_entry.order_id is None


@pytest.mark.asyncio
async def test_stale_price_blocks_the_reset_then_fresh_price_allows_it(
    client: AsyncClient,
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _go_all_in_then_crash_price(
        client, redis_client, fake_market_data, stale=True
    )

    async with session_factory() as db:
        blocked = await bankruptcy.maybe_reset_bankrupt_account(
            db, redis_client, test_settings, user_id=uid
        )
    assert blocked is None  # invariant 10: a stale price must not drive a reset

    async with session_factory() as db:
        still_bankrupt = await db.get(User, uid)
        assert still_bankrupt is not None
        assert still_bankrupt.cash_balance == Decimal("0.00")

    # Same crash price, now fresh.
    fresh = Ticker(
        pair="BTC/USD",
        bid=Decimal("0.001"),
        ask=Decimal("0.001"),
        last=Decimal("0.001"),
        as_of=datetime.now(UTC),
    )
    await set_cached_ticker(redis_client, fresh, ttl_seconds=120)

    async with session_factory() as db:
        allowed = await bankruptcy.maybe_reset_bankrupt_account(
            db, redis_client, test_settings, user_id=uid
        )
    assert allowed is not None


@pytest.mark.asyncio
async def test_overlapping_checks_reset_exactly_once(
    client: AsyncClient,
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _go_all_in_then_crash_price(
        client, redis_client, fake_market_data
    )

    async def check() -> object:
        async with session_factory() as db:
            return await bankruptcy.maybe_reset_bankrupt_account(
                db, redis_client, test_settings, user_id=uid
            )

    results = await asyncio.gather(check(), check())
    assert sum(1 for r in results if r is not None) == 1

    async with session_factory() as db:
        resets = (
            (
                await db.execute(
                    select(LedgerEntry).where(
                        LedgerEntry.user_id == uid,
                        LedgerEntry.entry_type == "bankruptcy_reset",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(resets) == 1
        user = await db.get(User, uid)
        assert user is not None
        assert user.cash_balance == _START  # invariant 1: never negative


@pytest.mark.asyncio
async def test_price_tick_resets_a_connected_bankrupt_holder_and_notifies(
    client: AsyncClient,
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await _register(client)
    uid = uuid.UUID(str(user["id"]))
    fake_market_data.set_price("BTC/USD", bid=_START, ask=_START, last=_START)
    fill = await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "1"},
        headers=_headers(),
    )
    assert fill.json()["status"] == "filled"

    fake_ws = _RecordingWS()
    ws_manager.connect(uid, fake_ws)  # type: ignore[arg-type]
    try:
        crash_tick = Ticker(
            pair="BTC/USD",
            bid=Decimal("0.001"),
            ask=Decimal("0.001"),
            last=Decimal("0.001"),
            as_of=datetime.now(UTC),
        )
        await price_stream.handle_tick(
            crash_tick, test_settings, redis_client, session_factory
        )
    finally:
        ws_manager.disconnect(uid, fake_ws)  # type: ignore[arg-type]

    types = [m["type"] for m in fake_ws.sent]
    assert "price_tick" in types
    assert "bankruptcy_reset" in types

    final_portfolio = [
        m for m in fake_ws.sent if m["type"] == "portfolio_update"
    ][-1]
    assert Decimal(str(final_portfolio["cash_balance"])) == _START

    async with session_factory() as db:
        refreshed = await db.get(User, uid)
        assert refreshed is not None
        assert refreshed.cash_balance == _START
