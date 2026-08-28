"""Leveraged-position endpoints — open, close, list. The one authenticated trading surface.

An open persists a Position row and returns 201 on success; a business rejection returns a
4xx and persists nothing (the idempotency key stays unconsumed); only a market-data
provider failure with no definitive answer returns 503. A close is idempotent — closing an
already-terminal position returns it unchanged.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import bankruptcy, leaderboard
from app.account import get_account_snapshot
from app.config import Settings, get_settings
from app.db import get_session
from app.deps import get_current_user
from app.market_data.pricing import StalePriceError
from app.models import Position, User
from app.positions import (
    MarketDataUnavailableError,
    PositionNotFoundError,
    PositionRejectedError,
    close_position,
    open_position,
)
from app.rate_limit import rate_limit
from app.redis_client import get_redis
from app.ws_manager import ws_manager
from app.ws_messages import AccountUpdateMessage, PositionUpdateMessage

router = APIRouter(tags=["trading"])

_PAIR_PATTERN = r"^[A-Z0-9]{1,16}/USD$"

# Per-IP ceiling on open/close. Idempotency already makes honest retries free; this is an
# abuse bound, set well above any realistic manual trading rate.
_positions_rate_limit = rate_limit("positions", limit=100, window_seconds=60)

_HTTP_422 = 422  # Starlette renamed its constant; the code is stable

_REJECTION_STATUS: dict[str, int] = {
    "leverage_not_allowed": _HTTP_422,
    "below_min_collateral": _HTTP_422,
    "position_exists": status.HTTP_409_CONFLICT,
    "insufficient_free_cash": status.HTTP_402_PAYMENT_REQUIRED,
    "stale_price": status.HTTP_409_CONFLICT,
    "pair_not_tradable": status.HTTP_409_CONFLICT,
}

_REJECTION_DETAIL: dict[str, str] = {
    "leverage_not_allowed": "That leverage isn't available.",
    "below_min_collateral": "Collateral is below the minimum.",
    "position_exists": "You already have an open position on that pair.",
    "insufficient_free_cash": "Not enough free cash for that collateral.",
    "stale_price": "The price is stale right now; try again in a moment.",
    "pair_not_tradable": "That pair isn't tradable right now.",
}


class OpenPositionRequest(BaseModel):
    pair: str = Field(pattern=_PAIR_PATTERN, examples=["BTC/USD"])
    side: Literal["long", "short"]
    collateral: Decimal = Field(gt=0)
    leverage: int = Field(gt=0)

    @field_validator("collateral")
    @classmethod
    def _validate_collateral_precision(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("collateral must be a finite number")
        exponent = value.as_tuple().exponent
        assert isinstance(exponent, int)
        if exponent < -2:
            raise ValueError("collateral must have at most 2 decimal places")
        return value


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pair: str
    side: Literal["long", "short"]
    status: Literal["open", "closed", "liquidated"]
    leverage: int
    collateral: Decimal
    size: Decimal
    entry_price: Decimal
    liquidation_price: Decimal
    open_fee: Decimal
    close_price: Decimal | None
    close_fee: Decimal | None
    realized_pnl: Decimal | None
    close_reason: str | None
    opened_at: datetime
    closed_at: datetime | None


@router.post(
    "/positions",
    response_model=PositionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_positions_rate_limit)],
)
async def open_position_endpoint(
    payload: OpenPositionRequest,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ],
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
    redis_client: redis.Redis = Depends(get_redis),  # noqa: B008 — FastAPI's own DI idiom
) -> Position:
    settings = get_settings()
    try:
        position = await open_position(
            db,
            redis_client,
            settings,
            user_id=user.id,
            idempotency_key=idempotency_key,
            pair=payload.pair,
            side=payload.side,
            collateral=payload.collateral,
            leverage=payload.leverage,
        )
    except PositionRejectedError as exc:
        raise HTTPException(
            _REJECTION_STATUS[exc.reason], _REJECTION_DETAIL[exc.reason]
        ) from None
    except MarketDataUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Market data temporarily unavailable; retry with the same Idempotency-Key.",
        ) from exc

    if position.status == "open":
        await _broadcast_account(db, redis_client, settings, user)
    return position


@router.post(
    "/positions/{position_id}/close",
    response_model=PositionResponse,
    dependencies=[Depends(_positions_rate_limit)],
)
async def close_position_endpoint(
    position_id: Annotated[uuid.UUID, Path()],
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
    redis_client: redis.Redis = Depends(get_redis),  # noqa: B008 — FastAPI's own DI idiom
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", max_length=255)
    ] = None,
) -> Position:
    settings = get_settings()
    try:
        position, closed_now = await close_position(
            db,
            redis_client,
            settings,
            user_id=user.id,
            position_id=position_id,
            reason="user",
        )
    except PositionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such position") from None
    except StalePriceError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The price is stale right now; try closing again in a moment.",
        ) from None
    except MarketDataUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Market data temporarily unavailable; retry.",
        ) from exc

    if closed_now:
        await ws_manager.send_position_update(
            user.id,
            PositionUpdateMessage(
                position_id=position.id,
                pair=position.pair,
                side=position.side,  # type: ignore[arg-type]
                status=position.status,  # type: ignore[arg-type]
                close_price=position.close_price,  # type: ignore[arg-type]
                realized_pnl=position.realized_pnl,  # type: ignore[arg-type]
                reason="user",
                at=position.closed_at,  # type: ignore[arg-type]
            ),
        )
        await _broadcast_account(db, redis_client, settings, user)
        await bankruptcy.check_and_broadcast(db, redis_client, settings, user)
    return position


@router.get("/positions", response_model=list[PositionResponse])
async def list_positions(
    status_filter: Annotated[
        Literal["open", "closed", "all"], Query(alias="status")
    ] = "all",
    before: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
) -> Sequence[Position]:
    stmt = select(Position).where(Position.user_id == user.id)
    if status_filter == "open":
        stmt = stmt.where(Position.status == "open")
    elif status_filter == "closed":
        stmt = stmt.where(Position.status != "open")
    if before is not None:
        cursor_opened_at = await db.scalar(
            select(Position.opened_at).where(
                Position.id == before, Position.user_id == user.id
            )
        )
        if cursor_opened_at is not None:
            stmt = stmt.where(
                (Position.opened_at < cursor_opened_at)
                | ((Position.opened_at == cursor_opened_at) & (Position.id < before))
            )
    stmt = stmt.order_by(Position.opened_at.desc(), Position.id.desc()).limit(limit)
    return (await db.execute(stmt)).scalars().all()


async def _broadcast_account(
    db: AsyncSession, redis_client: redis.Redis, settings: Settings, user: User
) -> None:
    snapshot = await get_account_snapshot(db, redis_client, settings, user)
    await ws_manager.send_account_update(
        user.id, AccountUpdateMessage(**snapshot.model_dump())
    )
    await leaderboard.update_score(redis_client, user.id, snapshot.equity)
