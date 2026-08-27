"""Order placement and read endpoints — the one authenticated trading surface this phase
adds. Every POST /orders attempt persists an Order row (filled or rejected) and returns
201; only a market-data provider failure that yields no definitive answer skips
persistence and surfaces as 503 (see app.trading.execute_order).
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import bankruptcy, leaderboard
from app.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import Holding, Order, User
from app.portfolio import get_portfolio_snapshot
from app.rate_limit import rate_limit
from app.redis_client import get_redis
from app.trading import MarketDataUnavailableError, execute_order
from app.ws_manager import ws_manager
from app.ws_messages import PortfolioUpdateMessage

router = APIRouter(tags=["trading"])

_SYMBOL_PATTERN = r"^[A-Z0-9]{1,16}/USD$"

# Per-IP ceiling on order submission — a runaway client loop shouldn't be able to hammer
# the provider/DB. Idempotency (app.trading) already makes honest retries free; this is
# purely an abuse bound, so it's set well above any realistic manual trading rate.
_orders_rate_limit = rate_limit("orders", limit=100, window_seconds=60)


class CreateOrderRequest(BaseModel):
    symbol: str = Field(pattern=_SYMBOL_PATTERN, examples=["BTC/USD"])
    side: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=0)

    @field_validator("quantity")
    @classmethod
    def _validate_quantity_precision(cls, value: Decimal) -> Decimal:
        # Never silently truncate a user's stated trade size — reject instead of rounding.
        if not value.is_finite():
            raise ValueError("quantity must be a finite number")
        exponent = value.as_tuple().exponent
        assert isinstance(exponent, int)
        if exponent < -10:
            raise ValueError("quantity must have at most 10 decimal places")
        return value


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    side: Literal["buy", "sell"]
    status: Literal["pending", "filled", "rejected"]
    quantity: Decimal
    execution_price: Decimal | None
    rejection_reason: str | None
    created_at: datetime
    filled_at: datetime | None


class HoldingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    quantity: Decimal
    average_cost: Decimal


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_orders_rate_limit)],
)
async def create_order(
    payload: CreateOrderRequest,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ],
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
    redis_client: redis.Redis = Depends(get_redis),  # noqa: B008 — FastAPI's own DI idiom
) -> Order:
    settings = get_settings()
    try:
        order = await execute_order(
            db,
            redis_client,
            settings,
            user_id=user.id,
            idempotency_key=idempotency_key,
            symbol=payload.symbol,
            side=payload.side,
            quantity=payload.quantity,
        )
    except MarketDataUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Market data temporarily unavailable; retry with the same Idempotency-Key.",
        ) from exc

    if order.status == "filled":
        # A no-op if this user has no open /ws connections. execute_order itself stays free
        # of this side effect (see app/trading.py) so its direct-call concurrency tests are
        # unaffected.
        snapshot = await get_portfolio_snapshot(db, redis_client, settings, user)
        await ws_manager.send_portfolio_update(
            user.id, PortfolioUpdateMessage(**snapshot.model_dump())
        )
        await leaderboard.update_score(redis_client, user.id, snapshot.net_worth)
        # A fill rarely causes bankruptcy on its own (cash swaps for equal-value asset), but
        # this is the cheap secondary guard; the check bails without locking when net worth
        # is clearly positive.
        await bankruptcy.check_and_broadcast(db, redis_client, settings, user)
    return order


@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(
    before: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
) -> Sequence[Order]:
    stmt = select(Order).where(Order.user_id == user.id)
    if before is not None:
        cursor_created_at = await db.scalar(
            select(Order.created_at).where(
                Order.id == before, Order.user_id == user.id
            )
        )
        if cursor_created_at is not None:
            stmt = stmt.where(
                (Order.created_at < cursor_created_at)
                | ((Order.created_at == cursor_created_at) & (Order.id < before))
            )
    stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit)
    return (await db.execute(stmt)).scalars().all()


@router.get("/holdings", response_model=list[HoldingResponse])
async def list_holdings(
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
) -> Sequence[Holding]:
    # quantity == 0 rows are kept (decision: no delete on full sell) but aren't a current
    # position, so the read-facing list filters them out.
    stmt = (
        select(Holding)
        .where(Holding.user_id == user.id, Holding.quantity > 0)
        .order_by(Holding.symbol)
    )
    return (await db.execute(stmt)).scalars().all()
