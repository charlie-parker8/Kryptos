"""The leaderboard read surface — a single ranked-by-equity view served from the Redis
sorted set (see app.leaderboard). The client polls this; there is no WebSocket push for
rankings.
"""

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import leaderboard
from app.db import get_session
from app.deps import get_current_user
from app.leaderboard import LeaderboardResponse
from app.models import User
from app.redis_client import get_redis

router = APIRouter(tags=["leaderboard"])


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
    redis_client: redis.Redis = Depends(get_redis),  # noqa: B008 — FastAPI's own DI idiom
) -> LeaderboardResponse:
    return await leaderboard.get_board(
        db, redis_client, limit=limit, viewer_id=user.id
    )
