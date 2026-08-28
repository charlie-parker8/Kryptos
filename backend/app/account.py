"""Server-side account valuation. Equity is always derived from PostgreSQL (free cash +
open positions) plus the latest known `last` price — never stored as its own authoritative
value (invariant 8). Used by both `GET /portfolio` and the WebSocket `account_update`
message, so the shapes here are the single source of truth for "the account" a client sees.

Unlike the strict pricing in `app.positions` / `app.bankruptcy`, this is tolerant: a
missing or stale price never blocks the snapshot. A position whose price has never been
observed contributes only its collateral to equity (P&L unknown, assumed breakeven) and is
flagged `stale`.
"""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

import redis.asyncio as redis
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import positions_math as pm
from app.config import Settings
from app.market_data.cache import get_ticker_for_display
from app.market_data.kraken import Ticker
from app.models import Position, User
from app.positions import quantize_cash

_RATIO_QUANTUM = Decimal("0.000001")


class PositionValuation(BaseModel):
    id: uuid.UUID
    pair: str
    side: str
    leverage: int
    collateral: Decimal
    size: Decimal
    entry_price: Decimal
    liquidation_price: Decimal
    mark_price: Decimal | None
    unrealized_pnl: Decimal | None
    position_equity: Decimal | None
    margin_ratio: Decimal | None
    stale: bool


class AccountSnapshot(BaseModel):
    free_cash: Decimal
    equity: Decimal
    total_unrealized_pnl: Decimal
    positions: list[PositionValuation]
    as_of: datetime


def value_position(
    position: Position, ticker: Ticker | None, *, stale: bool
) -> PositionValuation:
    """Pure — no I/O. `ticker=None` means no price has ever been observed for the pair (or
    the provider was unreachable): P&L is null and the row is flagged stale regardless of
    the `stale` argument.
    """
    notional = pm.notional(position.collateral, position.leverage)
    if ticker is None:
        return PositionValuation(
            id=position.id,
            pair=position.pair,
            side=position.side,
            leverage=position.leverage,
            collateral=position.collateral,
            size=position.size,
            entry_price=position.entry_price,
            liquidation_price=position.liquidation_price,
            mark_price=None,
            unrealized_pnl=None,
            position_equity=None,
            margin_ratio=None,
            stale=True,
        )
    upnl = pm.unrealized_pnl(
        side=cast("pm.PositionSide", position.side),
        size=position.size,
        entry_price=position.entry_price,
        mark_price=ticker.last,
    )
    equity = pm.position_equity(collateral=position.collateral, unrealized_pnl=upnl)
    return PositionValuation(
        id=position.id,
        pair=position.pair,
        side=position.side,
        leverage=position.leverage,
        collateral=position.collateral,
        size=position.size,
        entry_price=position.entry_price,
        liquidation_price=position.liquidation_price,
        mark_price=ticker.last,
        unrealized_pnl=upnl,
        position_equity=equity,
        margin_ratio=(equity / notional).quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_UP),
        stale=stale,
    )


async def get_account_snapshot(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    user: User,
) -> AccountSnapshot:
    """Value every open position at its last trade price and combine with free cash for
    account equity. A missing/stale price never blocks this (see module docstring)."""
    positions = (
        (
            await db.execute(
                select(Position)
                .where(Position.user_id == user.id, Position.status == "open")
                .order_by(Position.pair)
            )
        )
        .scalars()
        .all()
    )

    valuations: list[PositionValuation] = []
    for position in positions:
        try:
            ticker, stale = await get_ticker_for_display(
                redis_client,
                position.pair,
                base_url=settings.kraken_rest_base_url,
                timeout=settings.kraken_request_timeout_seconds,
                max_age_seconds=settings.price_max_age_seconds,
            )
        except Exception:  # noqa: BLE001 — a provider outage must degrade display, never break it
            valuations.append(value_position(position, None, stale=True))
            continue
        valuations.append(value_position(position, ticker, stale=stale))

    total_upnl = quantize_cash(
        sum(
            (v.unrealized_pnl for v in valuations if v.unrealized_pnl is not None),
            Decimal(0),
        )
    )
    # A position with no observed price contributes its collateral only (P&L unknown).
    open_equity = sum(
        (
            (v.position_equity if v.position_equity is not None else v.collateral)
            for v in valuations
        ),
        Decimal(0),
    )
    return AccountSnapshot(
        free_cash=user.cash_balance,
        equity=user.cash_balance + open_equity,
        total_unrealized_pnl=total_upnl,
        positions=valuations,
        as_of=datetime.now(UTC),
    )
