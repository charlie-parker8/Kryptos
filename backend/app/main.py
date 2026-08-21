from typing import Literal

import redis.asyncio as redis
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.db import AsyncSessionLocal

app = FastAPI(title="Kryptos")


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
