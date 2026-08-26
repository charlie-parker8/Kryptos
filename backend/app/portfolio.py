"""Server-side portfolio valuation — net worth is always derived from PostgreSQL's cash/holdings
plus the latest known market prices, never stored as its own authoritative value (invariant 8).
Used by both the `GET /portfolio` REST endpoint and the WebSocket `portfolio_update` message, so
the shapes here are the single source of truth for what a client sees as "their portfolio."
"""

from datetime import UTC, datetime
from decimal import Decimal

import redis.asyncio as redis
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.market_data.cache import get_ticker_for_display
from app.market_data.kraken import Ticker
from app.models import Holding, User
from app.trading import quantize_cash


class HoldingValuation(BaseModel):
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    current_price: Decimal | None
    market_value: Decimal | None
    stale: bool


class PortfolioSnapshot(BaseModel):
    cash_balance: Decimal
    holdings: list[HoldingValuation]
    net_worth: Decimal
    as_of: datetime


def value_holding(holding: Holding, ticker: Ticker | None, *, stale: bool) -> HoldingValuation:
    """Pure — no I/O. `ticker=None` means no price has ever been observed for this pair
    (or the provider was unreachable); the holding is still shown, just with a null
    price/value, always flagged stale in that case regardless of the `stale` argument.
    """
    if ticker is None:
        return HoldingValuation(
            symbol=holding.symbol,
            quantity=holding.quantity,
            average_cost=holding.average_cost,
            current_price=None,
            market_value=None,
            stale=True,
        )
    return HoldingValuation(
        symbol=holding.symbol,
        quantity=holding.quantity,
        average_cost=holding.average_cost,
        current_price=ticker.last,
        market_value=quantize_cash(ticker.last * holding.quantity),
        stale=stale,
    )


async def get_portfolio_snapshot(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    user: User,
) -> PortfolioSnapshot:
    """Value every open holding at its last trade price (never bid/ask — those are
    execution-only, see `pricing.executable_price`) and sum with cash for net worth. A price
    that's missing or stale never blocks this (unlike order execution): see `value_holding`.
    """
    holdings = (
        (
            await db.execute(
                select(Holding)
                .where(Holding.user_id == user.id, Holding.quantity > 0)
                .order_by(Holding.symbol)
            )
        )
        .scalars()
        .all()
    )

    valuations: list[HoldingValuation] = []
    for holding in holdings:
        pair = f"{holding.symbol}/USD"
        try:
            ticker, stale = await get_ticker_for_display(
                redis_client,
                pair,
                base_url=settings.kraken_rest_base_url,
                timeout=settings.kraken_request_timeout_seconds,
                max_age_seconds=settings.price_max_age_seconds,
            )
        except Exception:  # noqa: BLE001 — a provider outage must degrade display, never break it
            valuations.append(value_holding(holding, None, stale=True))
            continue
        valuations.append(value_holding(holding, ticker, stale=stale))

    total_market_value = sum(
        (v.market_value for v in valuations if v.market_value is not None), Decimal(0)
    )
    return PortfolioSnapshot(
        cash_balance=user.cash_balance,
        holdings=valuations,
        net_worth=user.cash_balance + total_market_value,
        as_of=datetime.now(UTC),
    )
