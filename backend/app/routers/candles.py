"""OHLC candle history for the Trade-page chart. A Redis read-through cache
(app.market_data.candles) in front of Kraken's REST OHLC endpoint — Postgres stores no
market data (invariant 8). The still-forming candle streams over `/ws` (app.candle_stream);
this endpoint serves the initial seed and the client's periodic reconciliation refetches.
"""

from decimal import Decimal

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.config import get_settings
from app.deps import get_current_user
from app.market_data import candles as candle_cache
from app.market_data.kraken import KrakenError
from app.models import User
from app.rate_limit import rate_limit
from app.redis_client import get_redis

router = APIRouter(tags=["market-data"])

# A cache miss hits Kraken; SWR on the client already dedupes polls. Purely an abuse bound.
_candles_rate_limit = rate_limit("candles", limit=60, window_seconds=60)


class CandlePoint(BaseModel):
    open_time: int  # unix seconds — bucket start (lightweight-charts `time`)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class CandlesResponse(BaseModel):
    pair: str
    interval: int  # minutes
    candles: list[CandlePoint]  # ascending by open_time; last entry may be still forming


@router.get(
    "/candles",
    response_model=CandlesResponse,
    dependencies=[Depends(_candles_rate_limit)],
)
async def get_candle_history(
    pair: str = Query(...),
    interval: int = Query(...),
    limit: int = Query(default=500, ge=1, le=1000),
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
    redis_client: redis.Redis = Depends(get_redis),  # noqa: B008 — FastAPI's own DI idiom
) -> CandlesResponse:
    settings = get_settings()
    if pair not in settings.supported_pairs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported pair: {pair}")
    if interval not in settings.supported_candle_intervals:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unsupported interval: {interval}"
        )
    try:
        rows = await candle_cache.get_candles(
            redis_client,
            pair,
            interval,
            limit=min(limit, settings.candle_history_limit),
            base_url=settings.kraken_rest_base_url,
            timeout=settings.kraken_request_timeout_seconds,
            history_ttl_seconds=settings.candle_history_ttl_seconds,
            forming_ttl_seconds=settings.candle_forming_ttl_seconds,
        )
    except (KrakenError, httpx.HTTPError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Market data temporarily unavailable",
        ) from exc
    return CandlesResponse(
        pair=pair,
        interval=interval,
        candles=[
            CandlePoint(
                open_time=int(c.open_time.timestamp()),
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
            for c in rows
        ],
    )
