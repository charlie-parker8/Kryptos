from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    get_settings().database_url, pool_pre_ping=True, future=True
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """For long-lived callers (the /ws route, the background price stream) that must never
    pin one Depends(get_session)-scoped session for their whole lifetime — they open and
    close short-lived sessions from this factory only when they actually need the DB.
    A plain FastAPI dependency (not a generator) so tests can override it the same way as
    get_redis, pointing it at the test engine's session factory instead of the real one.
    """
    return AsyncSessionLocal
