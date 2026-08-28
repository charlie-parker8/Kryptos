import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import redis.asyncio as redis
from helpers import STARTING_CASH, open_position, register, set_market_price
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import bankruptcy, price_stream
from app.config import Settings
from app.market_data.cache import set_cached_ticker
from app.market_data.fake import FakeMarketData
from app.market_data.kraken import Ticker
from app.models import LedgerEntry, Position, User
from app.ws_manager import ws_manager

pytestmark = pytest.mark.usefixtures("fake_market_data")


class _RecordingWS:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)


async def _open_max_long_then_crash(
    client: AsyncClient,
    redis_client: redis.Redis,
    fake_market_data: FakeMarketData,
    *,
    crash_to: str = "24000",
    stale: bool = False,
) -> uuid.UUID:
    """Register, put the whole $10k into a 2x BTC long at $50k, then move the cached price
    to `crash_to` so the position's loss exceeds its collateral. Returns the user id.
    """
    user = await register(client)
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    opened = await open_position(
        client, pair="BTC/USD", side="long", collateral="10000", leverage=2
    )
    assert opened.status_code == 201, opened.text

    age = 60.0 if stale else 0.0
    await set_market_price(
        fake_market_data, redis_client, "BTC/USD", crash_to, age_seconds=age
    )
    return uuid.UUID(str(user["id"]))


@pytest.mark.asyncio
async def test_solvent_account_is_never_reset(
    client: AsyncClient,
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await register(client)
    uid = uuid.UUID(str(user["id"]))

    async with session_factory() as db:
        result = await bankruptcy.maybe_reset_bankrupt_account(
            db, redis_client, test_settings, user_id=uid
        )
    assert result is None

    async with session_factory() as db:
        refreshed = await db.get(User, uid)
        assert refreshed is not None
        assert refreshed.cash_balance == STARTING_CASH


@pytest.mark.asyncio
async def test_wiped_out_account_is_reset_and_history_preserved(
    client: AsyncClient,
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _open_max_long_then_crash(client, redis_client, fake_market_data)

    async with session_factory() as db:
        reset = await bankruptcy.maybe_reset_bankrupt_account(
            db, redis_client, test_settings, user_id=uid
        )

    assert reset is not None
    assert [c.pair for c in reset.closed] == ["BTC/USD"]
    assert reset.starting_cash_balance == STARTING_CASH

    async with session_factory() as db:
        user = await db.get(User, uid)
        assert user is not None
        assert user.cash_balance == STARTING_CASH

        positions = (
            (await db.execute(select(Position).where(Position.user_id == uid)))
            .scalars()
            .all()
        )
        assert len(positions) == 1  # the position is preserved, just closed
        assert positions[0].status == "closed"
        assert positions[0].close_reason == "bankruptcy"

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
        assert [e.entry_type for e in ledger] == [
            "position_open",
            "bankruptcy_reset",
        ]
        assert ledger[-1].cash_balance_after == STARTING_CASH
        assert ledger[-1].position_id is None


@pytest.mark.asyncio
async def test_stale_price_blocks_the_reset_then_fresh_price_allows_it(
    client: AsyncClient,
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _open_max_long_then_crash(
        client, redis_client, fake_market_data, stale=True
    )

    async with session_factory() as db:
        blocked = await bankruptcy.maybe_reset_bankrupt_account(
            db, redis_client, test_settings, user_id=uid
        )
    assert blocked is None  # invariant 10

    await set_cached_ticker(
        redis_client,
        Ticker(
            pair="BTC/USD",
            bid=Decimal(24000),
            ask=Decimal(24000),
            last=Decimal(24000),
            as_of=datetime.now(UTC),
        ),
        ttl_seconds=120,
    )

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
    uid = await _open_max_long_then_crash(client, redis_client, fake_market_data)

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
        assert user.cash_balance == STARTING_CASH


@pytest.mark.asyncio
async def test_a_gap_down_tick_liquidates_and_then_resets_the_holder(
    client: AsyncClient,
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uid = await _open_max_long_then_crash(client, redis_client, fake_market_data)

    fake_ws = _RecordingWS()
    ws_manager.connect(uid, fake_ws)  # type: ignore[arg-type]
    try:
        crash_tick = Ticker(
            pair="BTC/USD",
            bid=Decimal(24000),
            ask=Decimal(24000),
            last=Decimal(24000),
            as_of=datetime.now(UTC),
        )
        await price_stream.handle_tick(
            crash_tick, test_settings, redis_client, session_factory
        )
    finally:
        ws_manager.disconnect(uid, fake_ws)  # type: ignore[arg-type]

    types = [m["type"] for m in fake_ws.sent]
    assert "price_tick" in types
    assert "position_update" in types
    assert "bankruptcy_reset" in types

    async with session_factory() as db:
        user = await db.get(User, uid)
        assert user is not None
        assert user.cash_balance == STARTING_CASH
        position = (
            await db.execute(select(Position).where(Position.user_id == uid))
        ).scalar_one()
        # The tick liquidated it; the reset then reclassified nothing (already terminal).
        assert position.status == "liquidated"
        assert position.close_reason == "liquidation"
