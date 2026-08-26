"""The read-only portfolio valuation surface — a client's first-paint snapshot before the
WebSocket's `portfolio_update` messages (see app.routers.ws) take over with live updates.
"""

import redis.asyncio as redis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.portfolio import PortfolioSnapshot, get_portfolio_snapshot
from app.redis_client import get_redis

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio", response_model=PortfolioSnapshot)
async def get_portfolio(
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
    redis_client: redis.Redis = Depends(get_redis),  # noqa: B008 — FastAPI's own DI idiom
) -> PortfolioSnapshot:
    return await get_portfolio_snapshot(db, redis_client, get_settings(), user)
