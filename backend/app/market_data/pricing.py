"""Executable-price selection and quote-freshness validation.

Pure functions, no I/O — kept separate from the Kraken adapter (app.market_data.kraken)
and the price cache (app.market_data.cache) so order execution's invariant checks can be
unit-tested without a network or a database.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.market_data.kraken import Ticker

OrderSide = Literal["buy", "sell"]


class StalePriceError(RuntimeError):
    """The freshest known quote for a pair is older than the configured max age (invariant 10)."""


def executable_price(ticker: Ticker, side: OrderSide) -> Decimal:
    """The price invariant 6 requires an order fill at: buys cross the ask, sells cross the
    bid. Never `last` — it reflects whichever side happened to trade last, not what a new
    order of the opposite side would need to pay/receive right now.
    """
    return ticker.ask if side == "buy" else ticker.bid


def ensure_fresh(
    ticker: Ticker, *, max_age_seconds: int, now: datetime | None = None
) -> None:
    """Enforce invariant 10: raise rather than let a cash/holdings-mutating action use a
    quote older than `max_age_seconds`. `now` is injectable for deterministic tests.
    """
    now = now if now is not None else datetime.now(UTC)
    age_seconds = (now - ticker.as_of).total_seconds()
    if age_seconds > max_age_seconds:
        raise StalePriceError(
            f"quote for {ticker.pair} is {age_seconds:.1f}s old, "
            f"exceeds max age {max_age_seconds}s"
        )
