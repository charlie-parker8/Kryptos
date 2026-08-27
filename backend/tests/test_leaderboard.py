import uuid
from decimal import Decimal

import pytest
import redis.asyncio as redis
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import leaderboard
from app.config import Settings
from app.market_data.fake import FakeMarketData
from app.models import User


def _uid() -> str:
    return f"u{uuid.uuid4().hex[:12]}"


async def _register(client: AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/auth/register",
        json={
            "email": f"{uuid.uuid4()}@example.com",
            "username": _uid(),
            "password": "correct-horse-1",
        },
    )
    assert response.status_code == 201
    return response.json()


async def _make_user(
    session_factory: async_sessionmaker[AsyncSession], *, cash: Decimal
) -> uuid.UUID:
    async with session_factory() as session:
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            username=_uid(),
            password_hash="not-a-real-hash",
            starting_cash_balance=Decimal("100000.00"),
            cash_balance=cash,
        )
        session.add(user)
        await session.commit()
        return user.id


# `rebuild` / `get_board` value every account in the shared test database, so the
# rebuild-based tests below use deliberately huge cash balances to pin their users to the
# top of the global ranking regardless of what other tests left behind.


async def _set_cash(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    cash: Decimal,
) -> None:
    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.cash_balance = cash
        await session.commit()


@pytest.mark.asyncio
async def test_registration_seeds_a_leaderboard_score(
    client: AsyncClient, redis_client: redis.Redis
) -> None:
    user = await _register(client)

    score = await redis_client.zscore(leaderboard.ZSET_KEY, str(user["id"]))
    assert score == pytest.approx(
        float(Decimal(str(user["starting_cash_balance"])) * 100)
    )


@pytest.mark.asyncio
async def test_leaderboard_ranks_by_net_worth_desc(
    client: AsyncClient, redis_client: redis.Redis
) -> None:
    u1 = await _register(client)
    u2 = await _register(client)
    u3 = await _register(client)  # client is now authenticated as u3

    await leaderboard.update_score(
        redis_client, uuid.UUID(str(u1["id"])), Decimal("150000.00")
    )
    await leaderboard.update_score(
        redis_client, uuid.UUID(str(u2["id"])), Decimal("90000.00")
    )
    await leaderboard.update_score(
        redis_client, uuid.UUID(str(u3["id"])), Decimal("120000.00")
    )

    body = (await client.get("/leaderboard")).json()
    entries = body["entries"]

    assert [e["username"] for e in entries] == [
        u1["username"],
        u3["username"],
        u2["username"],
    ]
    assert [e["rank"] for e in entries] == [1, 2, 3]
    assert Decimal(str(entries[0]["net_worth"])) == Decimal("150000.00")
    assert entries[1]["is_you"] is True  # u3 is the viewer
    assert body["you"] is None  # viewer is inside the page


@pytest.mark.asyncio
async def test_leaderboard_returns_your_row_when_outside_the_page(
    client: AsyncClient, redis_client: redis.Redis
) -> None:
    others = [await _register(client) for _ in range(3)]
    viewer = await _register(client)  # client authenticated as viewer

    for i, other in enumerate(others):
        await leaderboard.update_score(
            redis_client, uuid.UUID(str(other["id"])), Decimal(200000 - i)
        )
    await leaderboard.update_score(
        redis_client, uuid.UUID(str(viewer["id"])), Decimal("1000.00")
    )

    body = (await client.get("/leaderboard?limit=2")).json()

    assert len(body["entries"]) == 2
    assert all(e["is_you"] is False for e in body["entries"])
    assert body["you"] is not None
    assert body["you"]["rank"] == 4
    assert body["you"]["is_you"] is True
    assert Decimal(str(body["you"]["net_worth"])) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_empty_leaderboard_is_not_an_error(
    client: AsyncClient, redis_client: redis.Redis
) -> None:
    await _register(client)
    await redis_client.flushdb()  # wipe the seed

    body = (await client.get("/leaderboard")).json()
    assert body["entries"] == []
    assert body["you"] is None


@pytest.mark.asyncio
async def test_rebuild_repopulates_the_zset_purely_from_postgres(
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    id_a = await _make_user(session_factory, cash=Decimal("9990000.00"))
    id_b = await _make_user(session_factory, cash=Decimal("9980000.00"))
    await redis_client.flushdb()  # nothing left in Redis

    async with session_factory() as db:
        count = await leaderboard.rebuild(db, redis_client, test_settings)
        board = await leaderboard.get_board(
            db, redis_client, limit=5, viewer_id=id_a
        )

    assert count >= 2
    # The two huge balances pin these accounts to the top regardless of other test data.
    assert board.entries[0].net_worth == Decimal("9990000.00")
    assert board.entries[0].is_you is True
    assert board.entries[1].net_worth == Decimal("9980000.00")
    assert board.entries[1].username != ""
    _ = id_b


@pytest.mark.asyncio
async def test_move_reflects_rank_change_across_rebuilds(
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    id_a = await _make_user(session_factory, cash=Decimal("5000000.00"))
    id_b = await _make_user(session_factory, cash=Decimal("4000000.00"))
    await redis_client.flushdb()

    async with session_factory() as db:
        await leaderboard.rebuild(db, redis_client, test_settings)  # a #1, b #2

    await _set_cash(session_factory, id_a, Decimal("1.00"))  # a plummets

    async with session_factory() as db:
        # This rebuild snapshots the current ranks (a #1, b #2) into prev_ranks, then
        # rewrites scores so b is now #1.
        await leaderboard.rebuild(db, redis_client, test_settings)
        board = await leaderboard.get_board(
            db, redis_client, limit=20, viewer_id=id_b
        )

    # Other tests' accounts share the table, so b's absolute rank isn't 1 — but it climbed
    # exactly one position because `a` fell past it.
    b_entry = next(e for e in board.entries if e.is_you)
    assert b_entry.move == 1


@pytest.mark.asyncio
async def test_rebuild_snapshots_previous_ranks(
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _make_user(session_factory, cash=Decimal("100000.00"))
    await redis_client.flushdb()

    async with session_factory() as db:
        await leaderboard.rebuild(db, redis_client, test_settings)
        members = await redis_client.zrevrange(leaderboard.ZSET_KEY, 0, -1)
        assert not await redis_client.hgetall(leaderboard.PREV_RANKS_KEY)  # first pass
        await leaderboard.rebuild(db, redis_client, test_settings)

    prev = await redis_client.hgetall(leaderboard.PREV_RANKS_KEY)
    assert len(prev) == len(members)


@pytest.mark.asyncio
async def test_update_score_swallows_redis_errors(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_args: object, **_kwargs: object) -> None:
        raise redis.ConnectionError("redis is down")

    monkeypatch.setattr(redis_client, "zadd", boom)

    # Must not raise — the leaderboard is non-authoritative.
    await leaderboard.update_score(redis_client, uuid.uuid4(), Decimal("100000.00"))


@pytest.mark.asyncio
async def test_registration_survives_a_redis_outage(
    client: AsyncClient, redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_args: object, **_kwargs: object) -> None:
        raise redis.ConnectionError("redis is down")

    monkeypatch.setattr(redis_client, "zadd", boom)

    response = await client.post(
        "/auth/register",
        json={
            "email": f"{uuid.uuid4()}@example.com",
            "username": _uid(),
            "password": "correct-horse-1",
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_a_filled_buy_refreshes_the_leaderboard_score(
    client: AsyncClient,
    redis_client: redis.Redis,
    fake_market_data: FakeMarketData,
) -> None:
    user = await _register(client)
    fake_market_data.set_price(
        "BTC/USD", bid=Decimal(50000), ask=Decimal(50000), last=Decimal(50000)
    )

    await redis_client.zadd(leaderboard.ZSET_KEY, {str(user["id"]): 1})  # stale value

    await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    score = await redis_client.zscore(leaderboard.ZSET_KEY, str(user["id"]))
    # net worth after a buy is ~unchanged from the $100k start (cash -> asset of equal value)
    assert score == pytest.approx(100000 * 100, rel=1e-4)
