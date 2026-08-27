"""The one authenticated WebSocket endpoint (per CLAUDE.md: in-process fan-out, no client-server
protocol beyond connect/disconnect — server-push only). Pushes `price_tick` (broadcast to every
connection, from app.price_stream) and `portfolio_update` (to one user's own connections, sent
once on connect here and again from app.routers.orders after a fill) — see app.ws_messages for
the schemas and app.ws_manager for the connection registry.
"""

import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import bankruptcy
from app.config import get_settings
from app.db import get_session_factory
from app.deps import SESSION_COOKIE_NAME, load_user_by_session_token
from app.portfolio import get_portfolio_snapshot
from app.redis_client import get_redis
from app.ws_manager import ws_manager
from app.ws_messages import PortfolioUpdateMessage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def portfolio_ws(
    websocket: WebSocket,
    session_factory: async_sessionmaker[AsyncSession] = Depends(  # noqa: B008
        get_session_factory
    ),
    redis_client: Redis = Depends(get_redis),  # noqa: B008 — FastAPI's own DI idiom
) -> None:
    # Auth happens before accept() — a WebSocket route can't raise HTTPException the way an
    # HTTP route can, so an invalid/missing cookie is rejected by closing instead. A
    # short-lived session (not Depends(get_session)) is opened just for this one lookup:
    # Depends(get_session) ties a session's lifetime to the route's, and this route can stay
    # open for as long as a browser tab does — pinning a pool connection for that whole time
    # for no reason.
    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    user = None
    if token is not None:
        async with session_factory() as db:
            user = await load_user_by_session_token(db, token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    ws_manager.connect(user.id, websocket)
    try:
        async with session_factory() as db:
            snapshot = await get_portfolio_snapshot(
                db, redis_client, get_settings(), user
            )
            await websocket.send_json(
                PortfolioUpdateMessage(**snapshot.model_dump()).model_dump(mode="json")
            )
            # Catch an account that went bankrupt while it was disconnected. Runs after the
            # first snapshot so the client sees its real state, then the reset moment.
            if snapshot.net_worth <= 0:
                await bankruptcy.check_and_broadcast(
                    db, redis_client, get_settings(), user
                )
        while True:
            # No client->server protocol this phase; this only waits for a disconnect.
            # receive() returns the raw ASGI message rather than raising — Starlette only
            # raises WebSocketDisconnect from receive_text()/receive_json(), and calling
            # receive() again *after* a disconnect message raises RuntimeError instead of
            # returning another disconnect message.
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(user.id, websocket)
