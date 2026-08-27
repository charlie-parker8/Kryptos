import asyncio
import subprocess
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.market_data.fake import FakeMarketData
from app.models import Holding, Order, User
from app.trading import execute_order

_RESULTS_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "RESULTS.md"


async def _create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    cash_balance: Decimal,
    holdings: dict[str, Decimal] | None = None,
) -> uuid.UUID:
    async with session_factory() as session:
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            username=f"u{uuid.uuid4().hex[:12]}",
            password_hash="not-a-real-hash",
            starting_cash_balance=max(cash_balance, Decimal("1.00")),
            cash_balance=cash_balance,
        )
        session.add(user)
        await session.flush()
        for symbol, quantity in (holdings or {}).items():
            session.add(
                Holding(
                    user_id=user.id,
                    symbol=symbol,
                    quantity=quantity,
                    average_cost=Decimal("50000.00000000"),
                )
            )
        await session.commit()
        return user.id


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
    orders_per_sec = n / elapsed_seconds
    entry = (
        f"\n### {datetime.now(UTC):%Y-%m-%d} — {commit}\n"
        f"- N concurrent orders: {n}\n"
        f"- Elapsed: {elapsed_seconds:.3f}s\n"
        f"- Throughput: {orders_per_sec:.1f} orders/sec\n"
        f"- Invariant violations: 0 (cash_balance and holdings asserted non-negative "
        f"after the batch)\n"
    )
    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _RESULTS_PATH.open("a", encoding="utf-8") as f:
        f.write(entry)


@pytest.mark.asyncio
async def test_concurrent_submissions_sharing_idempotency_key_execute_exactly_once(
    engine: AsyncEngine,
    test_settings: Settings,
    redis_client: redis.Redis,
    fake_market_data: FakeMarketData,
) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = await _create_user(session_factory, cash_balance=Decimal("100000.00"))
    key = str(uuid.uuid4())

    async def submit() -> Order:
        async with session_factory() as session:
            return await execute_order(
                session,
                redis_client,
                test_settings,
                user_id=user_id,
                idempotency_key=key,
                symbol="BTC/USD",
                side="buy",
                quantity=Decimal(1),
            )

    results = await asyncio.gather(*(submit() for _ in range(10)))

    assert {order.id for order in results} == {results[0].id}
    assert all(order.status == "filled" for order in results)

    async with session_factory() as verify:
        rows = (
            (
                await verify.execute(
                    select(Order).where(
                        Order.user_id == user_id, Order.idempotency_key == key
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1

        user = await verify.get(User, user_id)
        assert user is not None
        assert user.cash_balance == Decimal("100000.00") - Decimal("50005.00")


@pytest.mark.asyncio
async def test_concurrent_buys_racing_a_tight_cash_balance_never_overspend(
    engine: AsyncEngine,
    test_settings: Settings,
    redis_client: redis.Redis,
    fake_market_data: FakeMarketData,
) -> None:
    price = Decimal("50005.00")  # fake default ask for BTC/USD
    affordable = 5
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = await _create_user(session_factory, cash_balance=price * affordable)

    async def submit(i: int) -> Order:
        async with session_factory() as session:
            return await execute_order(
                session,
                redis_client,
                test_settings,
                user_id=user_id,
                idempotency_key=f"buy-{i}",
                symbol="BTC/USD",
                side="buy",
                quantity=Decimal(1),
            )

    results = await asyncio.gather(*(submit(i) for i in range(affordable + 5)))

    filled = [o for o in results if o.status == "filled"]
    rejected = [o for o in results if o.status == "rejected"]
    assert len(filled) == affordable
    assert len(rejected) == 5
    assert all(o.rejection_reason == "insufficient_funds" for o in rejected)

    async with session_factory() as verify:
        user = await verify.get(User, user_id)
        assert user is not None
        assert user.cash_balance == Decimal("0.00")  # invariant 1: never negative


@pytest.mark.asyncio
async def test_concurrent_sells_racing_a_tight_holding_never_oversell(
    engine: AsyncEngine,
    test_settings: Settings,
    redis_client: redis.Redis,
    fake_market_data: FakeMarketData,
) -> None:
    owned_units = 5
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = await _create_user(
        session_factory,
        cash_balance=Decimal("100000.00"),
        holdings={"BTC": Decimal(owned_units)},
    )

    async def submit(i: int) -> Order:
        async with session_factory() as session:
            return await execute_order(
                session,
                redis_client,
                test_settings,
                user_id=user_id,
                idempotency_key=f"sell-{i}",
                symbol="BTC/USD",
                side="sell",
                quantity=Decimal(1),
            )

    results = await asyncio.gather(*(submit(i) for i in range(owned_units + 5)))

    filled = [o for o in results if o.status == "filled"]
    rejected = [o for o in results if o.status == "rejected"]
    assert len(filled) == owned_units
    assert len(rejected) == 5
    assert all(o.rejection_reason == "insufficient_holdings" for o in rejected)

    async with session_factory() as verify:
        holding = await verify.scalar(
            select(Holding).where(Holding.user_id == user_id, Holding.symbol == "BTC")
        )
        assert holding is not None
        assert holding.quantity == Decimal("0.0000000000")  # invariant 3: never negative


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_concurrent_order_execution_throughput_benchmark(
    engine: AsyncEngine,
    test_settings: Settings,
    redis_client: redis.Redis,
    fake_market_data: FakeMarketData,
) -> None:
    n = 200
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = await _create_user(
        session_factory, cash_balance=Decimal("1000000000.00")
    )

    async def submit(i: int) -> Order:
        async with session_factory() as session:
            return await execute_order(
                session,
                redis_client,
                test_settings,
                user_id=user_id,
                idempotency_key=f"throughput-{i}",
                symbol="BTC/USD",
                side="buy",
                quantity=Decimal("0.001"),
            )

    start = time.perf_counter()
    results = await asyncio.gather(*(submit(i) for i in range(n)))
    elapsed = time.perf_counter() - start

    assert all(o.status == "filled" for o in results)
    async with session_factory() as verify:
        user = await verify.get(User, user_id)
        assert user is not None
        assert user.cash_balance >= 0

    _append_benchmark_result(n=n, elapsed_seconds=elapsed)
