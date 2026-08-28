"""Bankruptcy reset — CLAUDE.md invariant 12.

When account equity (free cash + Σ open-position collateral + unrealized P&L) falls to or
below `settings.bankruptcy_equity_floor`, the account is reset: every open position is
closed at its fresh mark, free cash is restored to the per-row starting balance, and one
`bankruptcy_reset` ledger entry is written — atomically. Position and prior ledger history
are left untouched.

With isolated margin and a working liquidation engine, a clean liquidation leaves
~`mmr * notional` behind, so equity crosses the floor mainly on a gap move (price jumps
past a liquidation price between ticks). This is still checked on every equity-moving path:
the per-tick account push, a liquidation, an open/close, and a /ws (re)connect.

Invariant 10: the reset *decision* must not act on a stale price. Unlike the account
snapshot, this re-values positions with strict, fresh pricing under lock and defers the
reset when any held pair's price is stale or unfetchable.
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import httpx
import redis.asyncio as redis
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import leaderboard, position_index
from app import positions_math as pm
from app.account import get_account_snapshot
from app.config import Settings
from app.market_data.cache import get_latest_ticker
from app.market_data.kraken import KrakenError
from app.market_data.pricing import StalePriceError
from app.models import LedgerEntry, Position, User
from app.positions import quantize_cash, settle_position
from app.ws_manager import ws_manager
from app.ws_messages import (
    AccountUpdateMessage,
    BankruptcyResetMessage,
    PositionUpdateMessage,
)

logger = logging.getLogger(__name__)


class ClosedPositionInfo(BaseModel):
    position_id: uuid.UUID
    pair: str
    side: str
    close_price: Decimal
    realized_pnl: Decimal


class BankruptcyReset(BaseModel):
    starting_cash_balance: Decimal
    closed: list[ClosedPositionInfo]
    reset_at: datetime


async def maybe_reset_bankrupt_account(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    *,
    user_id: uuid.UUID,
) -> BankruptcyReset | None:
    """Reset `user_id` if its equity is at or below the floor, else return None. Idempotent
    under contention: a second overlapping call re-checks against the restored balance
    (holding the user-row lock) and bails.
    """
    floor = settings.bankruptcy_equity_floor

    gate_user = await db.get(User, user_id)
    if gate_user is None:
        return None
    gate = await get_account_snapshot(db, redis_client, settings, gate_user)
    if gate.equity > floor:
        return None

    # Plausibly bankrupt: lock the user row, then every open position (ordered by pair) —
    # the same lock order app.positions.close_position uses, so the two can't deadlock.
    # `populate_existing` overwrites whatever the lock-free gate loaded into the identity
    # map, so a concurrent reset/close that already committed is visible here.
    user = (
        await db.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    positions = list(
        (
            await db.execute(
                select(Position)
                .where(Position.user_id == user_id, Position.status == "open")
                .order_by(Position.pair)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )

    # Strict, fresh re-valuation (invariant 10) — any stale/unfetchable price defers.
    try:
        marks: dict[uuid.UUID, Decimal] = {}
        open_equity = Decimal(0)
        for position in positions:
            ticker = await get_latest_ticker(
                redis_client,
                position.pair,
                base_url=settings.kraken_rest_base_url,
                timeout=settings.kraken_request_timeout_seconds,
                max_age_seconds=settings.price_max_age_seconds,
            )
            marks[position.id] = ticker.last
            upnl = pm.unrealized_pnl(
                side=cast("pm.PositionSide", position.side),
                size=position.size,
                entry_price=position.entry_price,
                mark_price=ticker.last,
            )
            open_equity += position.collateral + upnl
    except (StalePriceError, KrakenError, httpx.HTTPError):
        await db.rollback()
        return None

    if user.cash_balance + open_equity > floor:
        await db.rollback()
        return None

    free_cash_before = user.cash_balance
    closed: list[ClosedPositionInfo] = []
    for position in positions:
        settlement = settle_position(
            position,
            user,
            close_price=marks[position.id],
            reason="bankruptcy",
            taker_fee_bps=settings.taker_fee_bps,
        )
        closed.append(
            ClosedPositionInfo(
                position_id=position.id,
                pair=position.pair,
                side=position.side,
                close_price=settlement.close_price,
                realized_pnl=settlement.realized_pnl,
            )
        )

    reset_at = datetime.now(UTC)
    db.add(
        LedgerEntry(
            user_id=user_id,
            position_id=None,
            entry_type="bankruptcy_reset",
            cash_delta=quantize_cash(user.starting_cash_balance - free_cash_before),
            cash_balance_after=user.starting_cash_balance,
            symbol=None,
            quantity_delta=None,
        )
    )
    user.cash_balance = user.starting_cash_balance
    await db.commit()

    for info in closed:
        await position_index.remove_open_position(
            redis_client, info.pair, info.position_id
        )
    logger.info(
        "bankruptcy reset for user %s; closed positions %s",
        user_id,
        [info.pair for info in closed],
    )
    return BankruptcyReset(
        starting_cash_balance=user.starting_cash_balance,
        closed=closed,
        reset_at=reset_at,
    )


async def check_and_broadcast(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    user: User,
) -> BankruptcyReset | None:
    """Run the check for `user`; on a reset, push a `position_update` per closed position,
    a `bankruptcy_reset`, and a fresh `account_update` to their /ws connections, and refresh
    their leaderboard score.
    """
    reset = await maybe_reset_bankrupt_account(
        db, redis_client, settings, user_id=user.id
    )
    if reset is None:
        return None

    await db.refresh(user)
    for info in reset.closed:
        await ws_manager.send_position_update(
            user.id,
            PositionUpdateMessage(
                position_id=info.position_id,
                pair=info.pair,
                side=info.side,  # type: ignore[arg-type]
                status="closed",
                close_price=info.close_price,
                realized_pnl=info.realized_pnl,
                reason="bankruptcy",
                at=reset.reset_at,
            ),
        )
    await ws_manager.send_bankruptcy_reset(
        user.id,
        BankruptcyResetMessage(
            starting_cash_balance=reset.starting_cash_balance,
            closed_positions=[info.pair for info in reset.closed],
            reset_at=reset.reset_at,
        ),
    )
    snapshot = await get_account_snapshot(db, redis_client, settings, user)
    await ws_manager.send_account_update(
        user.id, AccountUpdateMessage(**snapshot.model_dump())
    )
    await leaderboard.update_score(redis_client, user.id, snapshot.equity)
    return reset
