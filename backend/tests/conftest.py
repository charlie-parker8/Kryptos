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
from app.db import Base, get_session
from app.main import app

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
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """An HTTP client for `app`, with its DB dependency overridden to use the Postgres
    test database — `app.db.engine` is bound to the dev database at import time, so
    requests would otherwise write through the real app against the wrong database.
    """
    test_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)


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
