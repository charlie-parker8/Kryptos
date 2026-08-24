"""Shared FastAPI dependencies — currently just the session-cookie auth check every
protected route (auth's own /me today, orders/portfolio/leaderboard later) depends on.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User, UserSession
from app.security import hash_session_token

SESSION_COOKIE_NAME = "kryptos_session"

_NOT_AUTHENTICATED = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")


async def get_current_user(
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
) -> User:
    if session_token is None:
        raise _NOT_AUTHENTICATED

    token_hash = hash_session_token(session_token)
    result = await db.execute(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise _NOT_AUTHENTICATED
    return user
