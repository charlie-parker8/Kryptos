import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import redis.asyncio as redis
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.price_stream import run_price_stream
from app.redis_client import redis_client
from app.routers.auth import router as auth_router
from app.routers.orders import router as orders_router
from app.routers.portfolio import router as portfolio_router
from app.routers.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(run_price_stream(get_settings(), redis_client))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Kryptos", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(orders_router)
app.include_router(portfolio_router)
app.include_router(ws_router)


class HealthChecks(BaseModel):
    database: Literal["ok", "error"]
    redis: Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: HealthChecks


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    database_status: Literal["ok", "error"] = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — health check must report, never raise, regardless of failure mode
        database_status = "error"

    redis_status: Literal["ok", "error"] = "ok"
    client = redis.from_url(get_settings().redis_url)
    try:
        await client.ping()
    except Exception:  # noqa: BLE001 — health check must report, never raise, regardless of failure mode
        redis_status = "error"
    finally:
        await client.aclose()

    overall: Literal["ok", "degraded"] = (
        "ok" if database_status == "ok" and redis_status == "ok" else "degraded"
    )
    return HealthResponse(
        status=overall,
        checks=HealthChecks(database=database_status, redis=redis_status),
    )
