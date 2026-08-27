from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


# Shared by the app engine and Alembic (alembic/env.py). `ssl=True` gives asyncpg a
# verifying TLS context against the system CA bundle — needed for the Supabase pooler,
# off for local docker-compose Postgres.
CONNECT_ARGS: dict[str, Any] = {"ssl": True} if get_settings().database_ssl else {}

engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,  # a pooler (Supavisor) or PaaS may drop idle connections
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,  # ≤10 total — stays well under Supabase's free pooler client cap
    future=True,
    connect_args=CONNECT_ARGS,
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
