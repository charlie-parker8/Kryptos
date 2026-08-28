import ssl
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def build_db_ssl_context() -> ssl.SSLContext:
    """Verifying TLS context for asyncpg against the Supabase pooler.

    Equivalent to asyncpg's own `ssl=True` (full CA-chain + hostname verification
    against the system trust store) with one exception: Python 3.13 added
    ssl.VERIFY_X509_STRICT to the default verify flags, and Supabase's CA chain
    fails it with "CA cert does not include key usage extension". We clear only
    that RFC-5280 strictness flag; CERT_REQUIRED and check_hostname stay on, so
    the certificate and hostname are still fully validated.
    """
    context = ssl.create_default_context()
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


# Shared by the app engine and Alembic (alembic/env.py) so both connect identically —
# a verifying TLS context for the Supabase pooler, nothing for local docker-compose
# Postgres.
CONNECT_ARGS: dict[str, Any] = (
    {"ssl": build_db_ssl_context()} if get_settings().database_ssl else {}
)

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
