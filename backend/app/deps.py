"""Shared FastAPI dependencies — the session-cookie auth check every protected route (HTTP
routes via get_current_user; the /ws route via load_user_by_session_token directly, since a
websocket route authenticates itself before accept() rather than through the normal
exception-raising Depends() flow) depends on.
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


async def load_user_by_session_token(db: AsyncSession, token: str) -> User | None:
    """The one query mapping a raw session cookie value to its User — shared by
    get_current_user (HTTP) and app.routers.ws (WebSocket, which can't raise
    HTTPException and instead closes the connection itself on a None result).
    """
    token_hash = hash_session_token(token)
    result = await db.execute(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none()


async def get_current_user(
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
) -> User:
    if session_token is None:
        raise _NOT_AUTHENTICATED

    user = await load_user_by_session_token(db, session_token)
    if user is None:
        raise _NOT_AUTHENTICATED
    return user
