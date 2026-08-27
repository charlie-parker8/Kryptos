"""Bankruptcy reset — CLAUDE.md invariant 12.

Net worth at or below $0 resets the account to its (per-row) starting cash and clears every
active holding, atomically, recording one `bankruptcy_reset` ledger entry. Order and prior
ledger history is left untouched.

With invariants 1-3 in force (cash never negative, no overselling, no shorting/leverage),
net worth = cash + Σ market_value is always >= $0 and reaches exactly $0 only in
pathological cases, so in practice this is a correctness safety net. It is still enforced on
every net-worth-moving path: the per-tick portfolio push (the primary trigger — price
movement is what gets an all-in account there), an order fill, and a /ws (re)connect.

Invariant 10: the reset *decision* must not act on a stale price. Unlike portfolio display,
this re-values holdings with strict, fresh pricing under lock and defers the reset when any
held pair's price is stale or unfetchable.
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import redis.asyncio as redis
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import leaderboard
from app.config import Settings
from app.market_data.cache import get_latest_ticker
from app.market_data.kraken import KrakenError
from app.market_data.pricing import StalePriceError
from app.models import Holding, LedgerEntry, User
from app.portfolio import get_portfolio_snapshot
from app.trading import quantize_cash
from app.ws_manager import ws_manager
from app.ws_messages import BankruptcyResetMessage, PortfolioUpdateMessage

logger = logging.getLogger(__name__)


class BankruptcyReset(BaseModel):
    starting_cash_balance: Decimal
    cleared_symbols: list[str]
    reset_at: datetime


async def maybe_reset_bankrupt_account(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    *,
    user_id: uuid.UUID,
) -> BankruptcyReset | None:
    """Reset `user_id` if its net worth is <= $0, else return None. Idempotent under
    contention: a second overlapping call re-checks against the restored balance (holding
    the user-row lock) and bails.
    """
    # Lock-free gate — the overwhelmingly common path. Tolerant valuation (a stale/missing
    # price never blocks display); if net worth is clearly positive there's nothing to do
    # and no row locks were taken.
    gate_user = await db.get(User, user_id)
    if gate_user is None:
        return None
    gate = await get_portfolio_snapshot(db, redis_client, settings, gate_user)
    if gate.net_worth > 0:
        return None

    # Plausibly bankrupt: same lock order as app.trading.execute_order (user row, then
    # holding rows ordered by symbol) so the two can't deadlock or race a double-spend.
    # `populate_existing` forces the locked rows to overwrite whatever the lock-free gate
    # just loaded into this session's identity map — without it a concurrent reset that
    # already committed would be invisible here and we'd reset a second time.
    user = (
        await db.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    holdings = list(
        (
            await db.execute(
                select(Holding)
                .where(Holding.user_id == user_id, Holding.quantity > 0)
                .order_by(Holding.symbol)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )

    # Strict, fresh re-valuation (invariant 10) — any stale/unfetchable price defers the reset.
    try:
        total_value = Decimal(0)
        for holding in holdings:
            ticker = await get_latest_ticker(
                redis_client,
                f"{holding.symbol}/USD",
                base_url=settings.kraken_rest_base_url,
                timeout=settings.kraken_request_timeout_seconds,
                max_age_seconds=settings.price_max_age_seconds,
            )
            total_value += quantize_cash(ticker.last * holding.quantity)
    except (StalePriceError, KrakenError, httpx.HTTPError):
        await db.rollback()
        return None

    if user.cash_balance + total_value > 0:
        await db.rollback()
        return None

    cleared = [holding.symbol for holding in holdings]
    for holding in holdings:
        holding.quantity = Decimal(0)
        holding.average_cost = Decimal(0)

    reset_at = datetime.now(UTC)
    db.add(
        LedgerEntry(
            user_id=user_id,
            order_id=None,
            entry_type="bankruptcy_reset",
            cash_delta=user.starting_cash_balance - user.cash_balance,
            cash_balance_after=user.starting_cash_balance,
            symbol=None,
            quantity_delta=None,
        )
    )
    user.cash_balance = user.starting_cash_balance
    await db.commit()
    logger.info("bankruptcy reset for user %s; cleared holdings %s", user_id, cleared)
    return BankruptcyReset(
        starting_cash_balance=user.starting_cash_balance,
        cleared_symbols=cleared,
        reset_at=reset_at,
    )


async def check_and_broadcast(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    user: User,
) -> BankruptcyReset | None:
    """Run the check for `user`; on a reset, push a `bankruptcy_reset` message plus a fresh
    `portfolio_update` to their /ws connections and refresh their leaderboard score.
    """
    reset = await maybe_reset_bankrupt_account(
        db, redis_client, settings, user_id=user.id
    )
    if reset is None:
        return None

    await db.refresh(user)
    snapshot = await get_portfolio_snapshot(db, redis_client, settings, user)
    await ws_manager.send_bankruptcy_reset(
        user.id,
        BankruptcyResetMessage(
            starting_cash_balance=reset.starting_cash_balance,
            cleared_symbols=reset.cleared_symbols,
            reset_at=reset.reset_at,
        ),
    )
    await ws_manager.send_portfolio_update(
        user.id, PortfolioUpdateMessage(**snapshot.model_dump())
    )
    await leaderboard.update_score(redis_client, user.id, snapshot.net_worth)
    return reset
