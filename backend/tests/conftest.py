import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import Settings
from app.db import Base

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
