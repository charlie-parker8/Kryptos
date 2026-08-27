from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.db import Base, get_session, get_session_factory
from app.main import app
from app.market_data.fake import FakeMarketData
from app.market_data.kraken import Candle, PairStatus, Ticker
from app.redis_client import get_redis

TEST_DATABASE_URL = "postgresql+asyncpg://kryptos:kryptos@localhost:5432/kryptos_test"


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(
        database_url=TEST_DATABASE_URL, redis_url="redis://localhost:6379/1"
    )


@pytest_asyncio.fixture(scope="session")
async def engine(test_settings: Settings) -> AsyncEngine:
    eng = create_async_engine(test_settings.database_url, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine):
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(
    engine: AsyncEngine, redis_client: redis.Redis
) -> AsyncIterator[AsyncClient]:
    """An HTTP client for `app`, with its DB and Redis dependencies overridden to use the
    test database/logical DB — `app.db.engine` and `app.redis_client.redis_client` are
    both bound at import time to whichever dev URL is in the environment, so requests
    would otherwise write through the real app against the wrong database/cache.

    Also overrides get_session_factory (used by the /ws route and, indirectly via its
    default, app.price_stream) to the same test session factory — otherwise those two
    deliberately bypass Depends(get_session) for connection-pinning reasons (see
    app/db.py's get_session_factory docstring) and would silently hit the real dev
    database instead of this test's.
    """
    test_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with test_session_factory() as session:
            yield session

    async def override_get_redis() -> redis.Redis:
        return redis_client

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_session_factory] = lambda: test_session_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_session_factory, None)


@pytest_asyncio.fixture
async def session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """The same test session factory the `client`/`ws_client` fixtures wire into the app,
    exposed directly for tests that call app.price_stream.handle_tick or similar internals
    outside the HTTP/WS layer.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def redis_client(test_settings: Settings) -> AsyncIterator[redis.Redis]:
    """A real Redis client against the dedicated test DB index (separate from dev's db 0),
    flushed before and after each test so cache state never leaks between tests.
    """
    client = redis.from_url(test_settings.redis_url)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.fixture
def fake_market_data(monkeypatch: pytest.MonkeyPatch) -> FakeMarketData:
    """Patches the two live-provider entry points app.trading.execute_order actually calls
    (app.market_data.cache.get_ticker on a cache miss, app.trading.get_pair_status —
    pair-status is never cached this phase) with a FakeMarketData instance, following the
    same patch-by-import-site convention as test_market_data_cache.py. FakeMarketData's own
    get_ticker/get_pair_status take only (self, pair) — no base_url/timeout/client — so
    these adapters absorb the extra kwargs the real functions accept.
    """
    fake = FakeMarketData()

    async def fake_get_ticker(pair: str, **_: object) -> Ticker:
        return await fake.get_ticker(pair)

    async def fake_get_pair_status(pair: str, **_: object) -> PairStatus:
        return await fake.get_pair_status(pair)

    async def fake_get_ohlc(
        pair: str, interval: int, **_: object
    ) -> list[Candle]:
        return await fake.get_ohlc(pair, interval)

    monkeypatch.setattr("app.market_data.cache.get_ticker", fake_get_ticker)
    monkeypatch.setattr("app.trading.get_pair_status", fake_get_pair_status)
    monkeypatch.setattr("app.market_data.candles.get_ohlc", fake_get_ohlc)
    return fake
