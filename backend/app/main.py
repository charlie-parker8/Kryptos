import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.candle_stream import run_candle_stream
from app.config import get_settings
from app.db import AsyncSessionLocal
from app.leaderboard import run_leaderboard_refresh
from app.price_stream import run_price_stream
from app.redis_client import redis_client
from app.routers.auth import router as auth_router
from app.routers.candles import router as candles_router
from app.routers.leaderboard import router as leaderboard_router
from app.routers.portfolio import router as portfolio_router
from app.routers.positions import router as positions_router
from app.routers.ws import router as ws_router

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    tasks = [
        asyncio.create_task(run_price_stream(settings, redis_client)),
        asyncio.create_task(run_leaderboard_refresh(settings, redis_client)),
        asyncio.create_task(run_candle_stream(settings, redis_client)),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task


class SecurityMiddleware(BaseHTTPMiddleware):
    """Response security headers, plus a defense-in-depth Origin check on state-changing
    requests. The session cookie is already `SameSite=Lax` (which blocks cross-site
    cookie-bearing form POSTs); this additionally rejects a cross-origin `fetch` from an
    unlisted site. A request with no `Origin` header (curl, server-to-server, the health
    pinger, k6) is allowed — only a browser sends `Origin`, and cross-site it can't forge it.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method not in _SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin not in get_settings().allowed_origins:
                return JSONResponse(
                    {"detail": "Cross-origin request rejected"},
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


app = FastAPI(title="Kryptos", lifespan=lifespan)

_settings = get_settings()
# Added inner-to-outer: TrustedHost (outermost) → CORS → SecurityMiddleware → routes.
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.allowed_origins,  # exact list, never "*" (credentials mode)
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key"],
    max_age=600,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_settings.allowed_hosts)

app.include_router(auth_router)
app.include_router(positions_router)
app.include_router(portfolio_router)
app.include_router(ws_router)
app.include_router(leaderboard_router)
app.include_router(candles_router)


class HealthChecks(BaseModel):
    database: Literal["ok", "error"]
    redis: Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: HealthChecks


@app.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    database_status: Literal["ok", "error"] = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — health check must report, never raise, regardless of failure mode
        database_status = "error"

    redis_status: Literal["ok", "error"] = "ok"
    try:
        await redis_client.ping()
    except Exception:  # noqa: BLE001 — health check must report, never raise, regardless of failure mode
        redis_status = "error"

    overall: Literal["ok", "degraded"] = (
        "ok" if database_status == "ok" and redis_status == "ok" else "degraded"
    )
    # Postgres is a hard dependency (every route needs it) → 503 so the platform/monitor
    # sees the instance as unhealthy. Redis is soft (invariant 8: losing it costs only
    # freshness) → still 200, but the body reports "degraded".
    if database_status == "error":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status=overall,
        checks=HealthChecks(database=database_status, redis=redis_status),
    )
