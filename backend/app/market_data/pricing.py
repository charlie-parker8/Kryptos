"""Mark-price selection and quote-freshness validation.

Pure functions, no I/O — kept separate from the Kraken adapter (app.market_data.kraken)
and the price cache (app.market_data.cache) so position execution's invariant checks can be
unit-tested without a network or a database.

The leveraged-position model uses a single price everywhere — Kraken's `last` — for entry,
mark (unrealized P&L), exit and liquidation. There is no bid/ask spread cost.
"""

from datetime import UTC, datetime
from decimal import Decimal

from app.market_data.kraken import Ticker


class StalePriceError(RuntimeError):
    """The freshest known quote for a pair is older than the configured max age (invariant 10)."""


def mark_price(ticker: Ticker) -> Decimal:
    """The one price the position model runs on. `last` — the price the pair actually
    traded at — not `bid`/`ask`, which only mattered for the old spot spread-crossing model.
    """
    return ticker.last


def ensure_fresh(
    ticker: Ticker, *, max_age_seconds: int, now: datetime | None = None
) -> None:
    """Enforce invariant 10: raise rather than let a cash-mutating action (open, close,
    liquidation, bankruptcy re-valuation) use a quote older than `max_age_seconds`. `now`
    is injectable for deterministic tests.
    """
    now = now if now is not None else datetime.now(UTC)
    age_seconds = (now - ticker.as_of).total_seconds()
    if age_seconds > max_age_seconds:
        raise StalePriceError(
            f"quote for {ticker.pair} is {age_seconds:.1f}s old, "
            f"exceeds max age {max_age_seconds}s"
        )
