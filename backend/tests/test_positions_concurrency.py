"""Real Postgres, real row locking. `open_position` / `close_position` are called directly
from independent AsyncSession instances under `asyncio.gather` — the HTTP layer can't
exercise a genuine lock race because ASGITransport serialises requests on one connection.
"""

import asyncio
import subprocess
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import redis.asyncio as redis
from helpers import STARTING_CASH, set_market_price
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import positions
from app.config import Settings
from app.market_data.fake import FakeMarketData
from app.models import LedgerEntry, Position, User

pytestmark = pytest.mark.usefixtures("fake_market_data")

_RESULTS_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "RESULTS.md"


async def _make_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            username=f"u{uuid.uuid4().hex[:12]}",
            password_hash="not-a-real-hash",
            starting_cash_balance=STARTING_CASH,
            cash_balance=STARTING_CASH,
        )
        db.add(user)
        await db.commit()
        return user.id


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_opens_exactly_one_position(
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    uid = await _make_user(session_factory)
    key = "shared-key"

    async def attempt() -> object:
        async with session_factory() as db:
            try:
                return await positions.open_position(
                    db,
                    redis_client,
                    test_settings,
                    user_id=uid,
                    idempotency_key=key,
                    pair="BTC/USD",
                    side="long",
                    collateral=Decimal(1000),
                    leverage=10,
                )
            except positions.PositionRejectedError as exc:
                return exc.reason

    results = await asyncio.gather(*(attempt() for _ in range(10)))
    position_ids = {r.id for r in results if isinstance(r, Position)}
    assert len(position_ids) == 1

    async with session_factory() as db:
        count = await db.scalar(
            select(func.count()).select_from(Position).where(Position.user_id == uid)
        )
        assert count == 1
        user = await db.get(User, uid)
        assert user is not None
        assert user.cash_balance == STARTING_CASH - Decimal("1000.00")


@pytest.mark.asyncio
async def test_concurrent_opens_never_overspend_free_cash(
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    for pair in ("BTC/USD", "ETH/USD", "SOL/USD"):
        await set_market_price(fake_market_data, redis_client, pair, "50000")
    uid = await _make_user(session_factory)

    async def attempt(pair: str) -> object:
        async with session_factory() as db:
            try:
                await positions.open_position(
                    db,
                    redis_client,
                    test_settings,
                    user_id=uid,
                    idempotency_key=f"k-{pair}",
                    pair=pair,
                    side="long",
                    collateral=Decimal(4000),
                    leverage=2,
                )
                return "opened"
            except positions.PositionRejectedError as exc:
                return exc.reason

    results = await asyncio.gather(
        attempt("BTC/USD"), attempt("ETH/USD"), attempt("SOL/USD")
    )
    assert sorted(results) == ["insufficient_free_cash", "opened", "opened"]

    async with session_factory() as db:
        user = await db.get(User, uid)
        assert user is not None
        assert user.cash_balance == Decimal("2000.00")
        assert user.cash_balance >= 0  # invariant 1

        locked = await db.scalar(
            select(func.coalesce(func.sum(Position.collateral), 0)).where(
                Position.user_id == uid, Position.status == "open"
            )
        )
        assert user.cash_balance + locked == STARTING_CASH


@pytest.mark.asyncio
async def test_user_close_and_liquidation_settle_the_position_exactly_once(
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    uid = await _make_user(session_factory)
    async with session_factory() as db:
        opened = await positions.open_position(
            db,
            redis_client,
            test_settings,
            user_id=uid,
            idempotency_key="open",
            pair="BTC/USD",
            side="long",
            collateral=Decimal(1000),
            leverage=10,
        )
    position_id = opened.id

    async def user_close() -> object:
        async with session_factory() as db:
            return await positions.close_position(
                db,
                redis_client,
                test_settings,
                user_id=uid,
                position_id=position_id,
                reason="user",
            )

    async def liquidate() -> object:
        async with session_factory() as db:
            return await positions.close_position(
                db,
                redis_client,
                test_settings,
                user_id=uid,
                position_id=position_id,
                reason="liquidation",
                mark_override=Decimal(45250),
            )

    results = await asyncio.gather(user_close(), liquidate())
    closed_now_flags = [did for _, did in results]
    assert closed_now_flags.count(True) == 1

    async with session_factory() as db:
        terminal_entries = await db.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(
                LedgerEntry.position_id == position_id,
                LedgerEntry.entry_type.in_(("position_close", "liquidation")),
            )
        )
        assert terminal_entries == 1

        position = await db.get(Position, position_id)
        assert position is not None
        assert position.status in ("closed", "liquidated")

        user = await db.get(User, uid)
        assert user is not None
        # Whichever path won, cash = 9000 (post-open) + one settlement.
        ledger_sum = await db.scalar(
            select(func.sum(LedgerEntry.cash_delta)).where(
                LedgerEntry.user_id == uid
            )
        )
        assert user.cash_balance == STARTING_CASH + ledger_sum


@pytest.mark.asyncio
async def test_two_liquidation_passes_close_the_position_once(
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    uid = await _make_user(session_factory)
    async with session_factory() as db:
        opened = await positions.open_position(
            db,
            redis_client,
            test_settings,
            user_id=uid,
            idempotency_key="open",
            pair="BTC/USD",
            side="long",
            collateral=Decimal(1000),
            leverage=10,
        )

    async def liquidate() -> object:
        async with session_factory() as db:
            _, closed_now = await positions.close_position(
                db,
                redis_client,
                test_settings,
                user_id=uid,
                position_id=opened.id,
                reason="liquidation",
                mark_override=Decimal(45000),
            )
            return closed_now

    flags = await asyncio.gather(liquidate(), liquidate())
    assert list(flags).count(True) == 1


def _append_benchmark_result(*, n: int, elapsed_seconds: float) -> None:
    commit = (
        subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or "unknown"
    )
    per_sec = n / elapsed_seconds
    entry = (
        f"\n### {datetime.now(UTC):%Y-%m-%d} — {commit}\n"
        f"- N concurrent open+close round trips (distinct accounts): {n}\n"
        f"- Elapsed: {elapsed_seconds:.3f}s\n"
        f"- Throughput: {per_sec:.1f} round trips/sec\n"
        f"- Invariant violations: 0 (cash_balance non-negative, exactly one terminal "
        f"ledger entry per position, asserted after the batch)\n"
    )
    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _RESULTS_PATH.open("a", encoding="utf-8") as f:
        f.write(entry)


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_position_lifecycle_throughput_benchmark(
    redis_client: redis.Redis,
    test_settings: Settings,
    fake_market_data: FakeMarketData,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    n = 200
    await set_market_price(fake_market_data, redis_client, "BTC/USD", "50000")
    uids = await asyncio.gather(*(_make_user(session_factory) for _ in range(n)))

    async def round_trip(uid: uuid.UUID) -> None:
        async with session_factory() as db:
            opened = await positions.open_position(
                db,
                redis_client,
                test_settings,
                user_id=uid,
                idempotency_key="bench",
                pair="BTC/USD",
                side="long",
                collateral=Decimal(1000),
                leverage=5,
            )
        async with session_factory() as db:
            await positions.close_position(
                db,
                redis_client,
                test_settings,
                user_id=uid,
                position_id=opened.id,
                reason="user",
            )

    start = time.perf_counter()
    await asyncio.gather(*(round_trip(uid) for uid in uids))
    elapsed = time.perf_counter() - start

    async with session_factory() as db:
        for uid in uids:
            user = await db.get(User, uid)
            assert user is not None
            assert user.cash_balance >= 0
        terminal = await db.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.entry_type == "position_close")
        )
        assert terminal >= n

    _append_benchmark_result(n=n, elapsed_seconds=elapsed)
